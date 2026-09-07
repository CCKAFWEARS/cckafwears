import base64
import logging
import os
import smtplib
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import request, session

logger = logging.getLogger(__name__)


def _smtp_config():
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = "".join(os.environ.get("SMTP_PASSWORD", "").split())
    sender = os.environ.get("MAIL_FROM", username).strip()
    return host, port, username, password, sender


def send_email(to_addresses, subject, text_body, html_body=None):
    """Send an email through SMTP. Returns True on success and logs a safe failure reason."""
    if isinstance(to_addresses, str):
        to_addresses = [x.strip() for x in to_addresses.split(",") if x.strip()]
    to_addresses = list(to_addresses or [])
    host, port, username, password, sender = _smtp_config()

    if not to_addresses:
        logger.error("Email not sent: no recipient address was supplied")
        return False
    if not username or not password or not sender:
        logger.error("Email not sent: SMTP environment variables are incomplete")
        return False

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(to_addresses)
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(message)
        logger.info("Email sent successfully: subject=%r recipients=%s", subject, ",".join(to_addresses))
        return True
    except smtplib.SMTPAuthenticationError:
        logger.exception("Email not sent: SMTP authentication failed")
        return False
    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError, OSError):
        logger.exception("Email not sent: could not connect to SMTP server %s:%s", host, port)
        return False
    except smtplib.SMTPException:
        logger.exception("Email not sent: SMTP server rejected the message")
        return False
    except Exception:
        logger.exception("Email not sent: unexpected email error")
        return False


def _sms_config():
    return (
        os.environ.get("SMS_ACCOUNT_SID", "").strip(),
        os.environ.get("SMS_AUTH_TOKEN", "").strip(),
        os.environ.get("SMS_FROM_NUMBER", "").strip(),
    )


def _normalize_phone(phone):
    phone = (phone or "").strip().replace(" ", "").replace("-", "")
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    elif phone.startswith("0"):
        phone = "+233" + phone[1:]
    return phone


def send_sms(to_number, body):
    account_sid, auth_token, from_number = _sms_config()
    if not account_sid or not auth_token or not from_number:
        logger.error("SMS not sent: SMS_ACCOUNT_SID, SMS_AUTH_TOKEN and SMS_FROM_NUMBER are required")
        return False

    to_number = _normalize_phone(to_number)
    if not to_number.startswith("+") or len(to_number) < 10:
        logger.error("SMS not sent: invalid destination phone number")
        return False

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = urlencode({"From": from_number, "To": to_number, "Body": body}).encode("utf-8")
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
    req = Request(url, data=payload, method="POST", headers={"Authorization": f"Basic {credentials}"})

    try:
        with urlopen(req, timeout=20) as response:
            if 200 <= response.status < 300:
                return True
            logger.error("SMS provider returned HTTP %s", response.status)
            return False
    except HTTPError as exc:
        logger.error("SMS provider rejected the message: HTTP %s", exc.code)
        return False
    except URLError as exc:
        logger.error("SMS connection failed: %s", exc.reason)
        return False
    except Exception:
        logger.exception("Unexpected SMS sending error")
        return False


def send_verification_code(customer, code):
    """Send the customer verification OTP by SMS instead of email."""
    phone = request.form.get("phone", "").strip() or session.get("verification_phone", "")
    phone = _normalize_phone(phone)
    if not phone:
        logger.error("Verification SMS not sent: no phone number was supplied")
        return False
    session["verification_phone"] = phone
    return send_sms(phone, f"CCKAFWEARS verification code: {code}. It expires in 10 minutes. Do not share this code.")


def send_password_reset_code(customer, code):
    subject = "Reset your CCKAFWEARS password"
    text = (
        f"Hi {customer.name},\n\n"
        f"Your CCKAFWEARS password reset code is: {code}\n\n"
        "This code expires in 10 minutes. If you did not request a password reset, ignore this message.\n\n"
        "CCKAFWEARS"
    )
    return send_email(customer.email, subject, text)


def send_order_confirmation(order):
    if not order.customer_email:
        return False
    lines = "\n".join(
        f"- {item.product_name} x {item.quantity}: GHS {item.line_total:.2f}"
        for item in order.items
    )
    text = (
        f"Hi {order.customer_name},\n\n"
        f"Thank you for your CCKAFWEARS order {order.order_code}.\n\n"
        f"{lines}\n\n"
        f"Items subtotal: GHS {order.items_subtotal:.2f}\n"
        f"Delivery: GHS {order.delivery_fee:.2f}\n"
        f"Total: GHS {order.total_amount:.2f}\n"
        f"Payment method: {order.payment_method.replace('_', ' ').title()}\n\n"
        "We have received your order and will update you as payment and delivery progress.\n\n"
        "CCKAFWEARS"
    )
    return send_email(order.customer_email, f"CCKAFWEARS order confirmation — {order.order_code}", text)


def send_admin_order_notification(order):
    recipients = os.environ.get("ORDER_NOTIFICATION_EMAILS", "").strip()
    if not recipients:
        return False
    lines = "\n".join(
        f"- {item.product_name} x {item.quantity}: GHS {item.line_total:.2f}"
        for item in order.items
    )
    text = (
        f"New CCKAFWEARS order: {order.order_code}\n\n"
        f"Customer: {order.customer_name}\n"
        f"Email: {order.customer_email or 'Not provided'}\n"
        f"Phone: {order.customer_phone}\n"
        f"Address: {order.delivery_address}\n"
        f"Payment: {order.payment_method.replace('_', ' ').title()}\n\n"
        f"{lines}\n\n"
        f"Subtotal: GHS {order.items_subtotal:.2f}\n"
        f"Delivery: GHS {order.delivery_fee:.2f}\n"
        f"Total: GHS {order.total_amount:.2f}\n"
        f"Status: {order.status_label}\n"
    )
    return send_email(recipients, f"New CCKAFWEARS order — {order.order_code}", text)

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def _smtp_config():
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME", "").strip()
    # Gmail App Passwords are sometimes copied with spaces between groups.
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
        logger.exception("Email not sent: SMTP authentication failed. Check the Gmail App Password and SMTP username.")
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


def send_verification_code(customer, code):
    subject = "Verify your CCKAFWEARS account"
    text = (
        f"Hi {customer.name},\n\n"
        f"Your CCKAFWEARS verification code is: {code}\n\n"
        "This code expires in 10 minutes. If you did not create this account, you can ignore this email.\n\n"
        "CCKAFWEARS"
    )
    html = f"""
    <div style=\"font-family:Arial,sans-serif;max-width:560px;margin:auto\">
      <h2>CCKAFWEARS</h2>
      <p>Hi {customer.name},</p>
      <p>Use the verification code below to activate your customer account:</p>
      <div style=\"font-size:32px;font-weight:700;letter-spacing:8px;margin:24px 0\">{code}</div>
      <p>This code expires in 10 minutes.</p>
    </div>
    """
    return send_email(customer.email, subject, text, html)


def send_password_reset_code(customer, code):
    subject = "Reset your CCKAFWEARS password"
    text = (
        f"Hi {customer.name},\n\n"
        f"Your CCKAFWEARS password reset code is: {code}\n\n"
        "This code expires in 10 minutes. If you did not request a password reset, ignore this email.\n\n"
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
    recipients = os.environ.get("ORDER_NOTIFICATION_EMAILS", "cliffordanun@gmail.com")
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

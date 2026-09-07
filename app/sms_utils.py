import base64
import logging
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)


def _sms_config():
    return {
        "account_sid": os.environ.get("SMS_ACCOUNT_SID", "").strip(),
        "auth_token": os.environ.get("SMS_AUTH_TOKEN", "").strip(),
        "from_number": os.environ.get("SMS_FROM_NUMBER", "").strip(),
    }


def normalize_phone(phone):
    phone = (phone or "").strip().replace(" ", "").replace("-", "")
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    elif phone.startswith("0"):
        phone = "+233" + phone[1:]
    return phone


def send_sms(to_number, body):
    config = _sms_config()
    if not all(config.values()):
        logger.error("SMS is not configured: missing SMS_ACCOUNT_SID, SMS_AUTH_TOKEN, or SMS_FROM_NUMBER")
        return False

    to_number = normalize_phone(to_number)
    if not to_number.startswith("+") or len(to_number) < 10:
        logger.error("SMS rejected: invalid destination number format")
        return False

    url = f"https://api.twilio.com/2010-04-01/Accounts/{config['account_sid']}/Messages.json"
    payload = urlencode({"From": config["from_number"], "To": to_number, "Body": body}).encode("utf-8")
    credentials = base64.b64encode(f"{config['account_sid']}:{config['auth_token']}".encode("utf-8")).decode("ascii")
    request = Request(url, data=payload, method="POST", headers={"Authorization": f"Basic {credentials}"})

    try:
        with urlopen(request, timeout=20) as response:
            if 200 <= response.status < 300:
                return True
            logger.error("SMS provider returned HTTP %s", response.status)
            return False
    except HTTPError as exc:
        logger.error("SMS provider rejected request: HTTP %s", exc.code)
        return False
    except URLError as exc:
        logger.error("SMS connection failed: %s", exc.reason)
        return False
    except Exception:
        logger.exception("Unexpected SMS sending error")
        return False


def send_verification_code(customer, code):
    body = f"CCKAFWEARS verification code: {code}. It expires in 10 minutes. Do not share this code."
    return send_sms(customer.phone, body)

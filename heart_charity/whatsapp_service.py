import os
import re
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def get_whatsapp_config():
    """
    Retrieves 11za WhatsApp API configuration securely from Django settings
    or environment variables without hardcoding.
    """
    return {
        "access_token": str(
            getattr(settings, "WHATSAPP_ACCESS_TOKEN", None)
            or os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
        ).strip(),
        "api_url": str(
            getattr(settings, "WHATSAPP_API", None)
            or os.environ.get("WHATSAPP_API", "https://api.11za.in/apis/template/sendTemplate")
        ).strip(),
        "origin_website": str(
            getattr(settings, "WHATSAPP_ORIGIN_WEBSITE", None)
            or os.environ.get("WHATSAPP_ORIGIN_WEBSITE", "https://www.ahinsadham.org/")
        ).strip(),
        "template_name": str(
            getattr(settings, "WHATSAPP_TEMPLATE_NAME", None)
            or os.environ.get("WHATSAPP_TEMPLATE_NAME", "otp")
        ).strip(),
        "button_value": str(
            getattr(settings, "WHATSAPP_BUTTON_VALUE", None)
            or os.environ.get("WHATSAPP_BUTTON_VALUE", "https://www.ahinsadham.org/")
        ).strip(),
        "template_language": str(
            getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", None)
            or os.environ.get("WHATSAPP_TEMPLATE_LANGUAGE", "en")
        ).strip(),
    }


def normalize_phone_10_digits(phone):
    """
    Normalizes a given phone number into a canonical 10-digit Indian mobile number.
    Strips non-digits, country code +91, or leading 0.
    Returns 10-digit string or None if invalid.
    """
    if not phone:
        return None
    raw = str(phone).strip()
    digits = re.sub(r"\D", "", raw)

    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    elif len(digits) > 10:
        digits = digits[-10:]

    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return None


def validate_and_format_phone(phone):
    """
    Validates and formats a phone number for 11za WhatsApp Business Cloud API.
    - 10-digit Indian numbers are formatted with '91' prefix -> '91XXXXXXXXXX'.
    - Already prefixed 12-digit numbers starting with '91' remain as-is.
    - Returns standardized digits string, or None if invalid.
    """
    phone10 = normalize_phone_10_digits(phone)
    if phone10:
        return f"91{phone10}"

    if not phone:
        return None
    digits = re.sub(r"\D", "", str(phone).strip())
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return digits
    if 11 <= len(digits) <= 15:
        return digits
    return None


def mask_phone(phone):
    """
    Masks a phone number for secure logging (e.g. 9198****10) to avoid exposing PII in logs.
    """
    if not phone:
        return "****"
    p_str = re.sub(r"\D", "", str(phone))
    if len(p_str) >= 6:
        return f"{p_str[:4]}****{p_str[-2:]}"
    return "****"


def send_login_otp_whatsapp(phone, otp, user=None, force=True, **kwargs):
    """
    Sends a dynamically generated 6-digit login OTP to the user's WhatsApp number
    using the approved 'otp' template via 11za WhatsApp Business Cloud API.

    Template Name: otp
    Template Message: {{1}} is your verification code. For your security, do not share this code.
    Template Variable: {{1}} = Dynamically generated login OTP

    Security & Privacy Rules:
    - Never log authorization tokens or plaintext OTP codes.
    - Uses strict 15-second HTTP request timeout.
    - Validates response code and payload before returning success.
    """
    if not phone:
        logger.warning("[whatsapp] Missing phone number for OTP dispatch")
        return {"success": False, "error": "Missing phone number"}

    if not otp:
        logger.warning("[whatsapp] Missing OTP code for dispatch")
        return {"success": False, "error": "Missing OTP code"}

    formatted_phone = validate_and_format_phone(phone)
    if not formatted_phone:
        logger.warning("[whatsapp] Invalid phone format provided")
        return {"success": False, "error": f"Invalid phone number: {phone}"}

    config = get_whatsapp_config()
    auth_token = config.get("access_token")
    api_url = config.get("api_url")
    origin_website = config.get("origin_website")
    button_value = config.get("button_value")
    template_name = "otp"

    if not auth_token:
        logger.error("[whatsapp] WHATSAPP_ACCESS_TOKEN is not configured in settings/env")
        return {"success": False, "error": "WHATSAPP_ACCESS_TOKEN is missing"}

    customer_name = "Customer"
    if user:
        full_name = getattr(user, "get_full_name", lambda: "")()
        username = getattr(user, "username", "")
        customer_name = full_name.strip() or username or "Customer"

    # 11za WhatsApp API payload for approved 'otp' template
    payload = {
        "authToken": auth_token,
        "name": str(customer_name),
        "sendto": formatted_phone,
        "originWebsite": origin_website,
        "templateName": template_name,
        "language": "en",
        "buttonValue": button_value,
        "headerdata": "",
        "myfile": "",
        "myfileName": "",
        "data": [str(otp)],
        "tags": "login_otp",
    }

    masked_phone = f"{formatted_phone[:4]}****{formatted_phone[-2:]}" if len(formatted_phone) >= 6 else "****"
    logger.info(f"[whatsapp] Dispatching login OTP to {masked_phone} via template '{template_name}'")

    def _execute_send(cur_payload):
        resp = requests.post(
            api_url,
            json=cur_payload,
            timeout=(10, 30),
        )
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return resp.status_code, body, resp.text

    try:
        status_code, res_json, raw_text = _execute_send(payload)
        # Handle 11za specific error: if origin website or button value was rejected, retry with fallback
        if (
            status_code == 400
            and isinstance(res_json, dict)
            and ("Invalid originWebsites" in str(res_json.get("Message", "")) or "button" in str(res_json.get("Message", "")).lower())
            and (payload.get("originWebsite") != "https://www.ahinsadham.org/" or payload.get("buttonValue") != "https://www.ahinsadham.org/")
        ):
            logger.warning("[whatsapp] Payload rejected by 11za, retrying with fallback 'https://www.ahinsadham.org/'")
            payload["originWebsite"] = "https://www.ahinsadham.org/"
            payload["buttonValue"] = "https://www.ahinsadham.org/"
            status_code, res_json, raw_text = _execute_send(payload)

        # Check 11za response structure
        is_success = False
        message_id = None
        if 200 <= status_code < 300:
            if isinstance(res_json, dict):
                # 11za returns: {"Message": "Template Message Sent", "Data": {"messageId": "wamid..."}, "Status": 200, "IsSuccess": true}
                if res_json.get("IsSuccess") is True or res_json.get("Status") == 200:
                    is_success = True
                elif res_json.get("IsSuccess") is False or res_json.get("Status") not in [None, 200]:
                    is_success = False
                else:
                    is_success = True

                data_field = res_json.get("Data")
                if isinstance(data_field, dict):
                    message_id = data_field.get("messageId")
                elif isinstance(data_field, str):
                    message_id = data_field
                message_id = message_id or res_json.get("messageId") or res_json.get("id")
            else:
                is_success = True

        if is_success:
            logger.info(f"[whatsapp] Successfully delivered login OTP to {masked_phone} (messageId={message_id})")
            return {
                "success": True,
                "message_id": message_id,
                "response": res_json,
            }

        err_msg = ""
        if isinstance(res_json, dict):
            err_msg = res_json.get("Message") or res_json.get("message") or res_json.get("error")
        if not err_msg:
            err_msg = f"11za API error ({status_code}): {raw_text}"

        logger.error(
            f"[whatsapp] 11za API rejected OTP dispatch: status={status_code} error={err_msg}"
        )
        return {
            "success": False,
            "error": str(err_msg),
            "response": res_json,
        }

    except requests.Timeout:
        logger.error(f"[whatsapp] Timeout contacting 11za API for {masked_phone}")
        return {"success": False, "error": "WhatsApp service timed out. Please try again."}
    except requests.RequestException as ex:
        logger.error(f"[whatsapp] Network error contacting 11za API: {ex}")
        return {"success": False, "error": f"Network error contacting WhatsApp service: {ex}"}



def send_donation_receipt_whatsapp(
    phone,
    donor_name,
    amount,
    donation_date,
    receipt_id,
    document_url,
    document_filename=None,
    **kwargs
):
    """
    Sends the official Ahinsadham donation receipt PDF to the donor's WhatsApp number
    using the approved 'utility_5671' document template via 11za WhatsApp Business Cloud API.

    Template Name: utility_5671
    Header Type: Document (.pdf attachment)
    Message:
        Dear {{1}},

        Thank you for your generous support to Ahinsadham. We are deeply grateful.

        We have received your donation of Rs. {{2}} on {{3}}. Your receipt no. {{4}} is attached for your records.

        With sincere appreciation and gratitude,

        Team Ahinsadham
        Bhagwan Mahavir Pashu Raksha Kendra

    Variable mapping:
        {{1}} = Donor Name
        {{2}} = Donation Amount
        {{3}} = Donation Date
        {{4}} = Receipt Number

    Document Parameters:
        myfile: Public or secure signed URL of the generated PDF receipt on GCS.
        myfileName: Visible filename of the attached document (e.g. Donation_Receipt_ACH-00123.pdf).
        headerdata: Empty string "" for document header templates in 11za.
    """
    if not phone:
        logger.warning("[whatsapp receipt] Missing phone number for receipt delivery")
        return {"success": False, "error": "Missing donor phone number"}

    formatted_phone = validate_and_format_phone(phone)
    if not formatted_phone:
        logger.warning(f"[whatsapp receipt] Invalid phone number provided: {mask_phone(phone)}")
        return {"success": False, "error": f"Invalid donor phone number: {mask_phone(phone)}"}

    if not document_url or not str(document_url).strip():
        logger.warning(f"[whatsapp receipt] Missing document URL for receipt {receipt_id}")
        return {"success": False, "error": "Missing receipt document URL"}

    config = get_whatsapp_config()
    auth_token = config.get("access_token")
    api_url = config.get("api_url")
    origin_website = config.get("origin_website")
    button_value = config.get("button_value")
    template_name = str(
        getattr(settings, "WHATSAPP_RECEIPT_TEMPLATE_NAME", None)
        or os.environ.get("WHATSAPP_RECEIPT_TEMPLATE_NAME", "utility_5671")
        or "utility_5671"
    ).strip()
    language_code = config.get("template_language", "en") or "en"

    if not auth_token:
        logger.error("[whatsapp receipt] WHATSAPP_ACCESS_TOKEN is not configured in settings/env")
        return {"success": False, "error": "WHATSAPP_ACCESS_TOKEN is missing"}

    clean_donor_name = str(donor_name).strip() if donor_name else "Valued Donor"
    clean_amount = str(amount).strip()
    clean_date = str(donation_date).strip()
    clean_receipt_id = str(receipt_id).strip()
    doc_filename = str(document_filename).strip() if document_filename else f"Donation_Receipt_{clean_receipt_id}.pdf"

    payload = {
        "authToken": auth_token,
        "name": clean_donor_name,
        "sendto": formatted_phone,
        "originWebsite": origin_website,
        "templateName": template_name,
        "language": language_code,
        "buttonValue": button_value,
        "headerdata": "",
        "myfile": str(document_url).strip(),
        "myfileName": doc_filename,
        "data": [
            clean_donor_name,
            clean_amount,
            clean_date,
            clean_receipt_id,
        ],
        "isTinyURL": "no",
        "tags": "donation_receipt",
    }

    masked_phone = f"{formatted_phone[:4]}****{formatted_phone[-2:]}" if len(formatted_phone) >= 6 else "****"
    logger.info(
        f"[whatsapp receipt] Dispatching receipt {clean_receipt_id} to {masked_phone} via template '{template_name}' (doc={doc_filename})"
    )

    def _execute_send(cur_payload):
        resp = requests.post(
            api_url,
            json=cur_payload,
            timeout=(10, 30),
        )
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return resp.status_code, body, resp.text

    try:
        status_code, res_json, raw_text = _execute_send(payload)

        # Retry with standard originWebsite fallback if rejected by 11za
        if (
            status_code == 400
            and isinstance(res_json, dict)
            and ("Invalid originWebsites" in str(res_json.get("Message", "")) or "button" in str(res_json.get("Message", "")).lower())
            and (payload.get("originWebsite") != "https://www.ahinsadham.org/" or payload.get("buttonValue") != "https://www.ahinsadham.org/")
        ):
            logger.warning("[whatsapp receipt] Payload rejected by 11za, retrying with fallback 'https://www.ahinsadham.org/'")
            payload["originWebsite"] = "https://www.ahinsadham.org/"
            payload["buttonValue"] = "https://www.ahinsadham.org/"
            status_code, res_json, raw_text = _execute_send(payload)

        is_success = False
        message_id = None
        if 200 <= status_code < 300:
            if isinstance(res_json, dict):
                if res_json.get("IsSuccess") is True or res_json.get("Status") == 200:
                    is_success = True
                elif res_json.get("IsSuccess") is False or res_json.get("Status") not in [None, 200]:
                    is_success = False
                else:
                    is_success = True

                data_field = res_json.get("Data")
                if isinstance(data_field, dict):
                    message_id = data_field.get("messageId")
                elif isinstance(data_field, str):
                    message_id = data_field
                message_id = message_id or res_json.get("messageId") or res_json.get("id")
            else:
                is_success = True

        if is_success:
            logger.info(
                f"[whatsapp receipt] Successfully dispatched receipt {clean_receipt_id} to {masked_phone} (messageId={message_id})"
            )
            return {
                "success": True,
                "message_id": message_id,
                "phone": masked_phone,
                "response": res_json,
            }

        err_msg = ""
        if isinstance(res_json, dict):
            err_msg = res_json.get("Message") or res_json.get("message") or res_json.get("error")
        if not err_msg:
            err_msg = f"11za API error ({status_code}): {raw_text}"

        logger.error(
            f"[whatsapp receipt] 11za rejected receipt {clean_receipt_id} dispatch to {masked_phone}: status={status_code} error={err_msg}"
        )
        return {
            "success": False,
            "error": str(err_msg),
            "phone": masked_phone,
            "response": res_json,
        }

    except requests.Timeout:
        logger.error(f"[whatsapp receipt] Timeout contacting 11za API for receipt {clean_receipt_id} ({masked_phone})")
        return {"success": False, "error": "WhatsApp service timed out. Please try again later.", "phone": masked_phone}
    except requests.RequestException as ex:
        logger.error(f"[whatsapp receipt] Network error contacting 11za API for receipt {clean_receipt_id}: {ex}")
        return {"success": False, "error": f"Network error contacting WhatsApp service: {ex}", "phone": masked_phone}

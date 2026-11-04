"""
Receipt Service for Ahinsadham CRM
Handles:
1. Dynamic PDF receipt generation reusing existing templates (donation_receipt.html / donation_owner_receipt_pdf.html).
2. Google Cloud Storage upload with unique filenames (donation_receipts/Donation_Receipt_<receipt_id>.pdf).
3. Secure accessible / signed document URL resolution.
4. WhatsApp document template delivery via 11za (Template: utility_5671).
5. Duplicate message protection, delivery logging, and controlled retry support.
"""

import os
import re
import logging
from io import BytesIO
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from xhtml2pdf import pisa

from .whatsapp_service import (
    validate_and_format_phone,
    send_donation_receipt_whatsapp,
    mask_phone,
)

logger = logging.getLogger(__name__)


def resolve_receipt_image_paths():
    """
    Locates static receipt assets on disk so xhtml2pdf can reliably embed them.
    Checks STATIC_ROOT, heart_charity/static, and staticfiles directories.
    """
    base_dir = getattr(settings, 'BASE_DIR', '')
    search_dirs = [
        getattr(settings, 'STATIC_ROOT', None),
        os.path.join(base_dir, 'heart_charity', 'static'),
        os.path.join(base_dir, 'staticfiles'),
    ]

    image_files = {
        'logo_url': 'images/alogo.png',
        'signature_url': 'images/signature.png',
        'facebook_icon': 'images/facebook.png',
        'instagram_icon': 'images/instagram.png',
        'youtube_icon': 'images/youtube.png',
        'globe_icon': 'images/globe.png',
    }

    resolved = {}
    for key, rel_path in image_files.items():
        found_path = None
        for s_dir in search_dirs:
            if not s_dir:
                continue
            candidate = os.path.join(s_dir, rel_path.replace('/', os.sep))
            if os.path.isfile(candidate):
                found_path = candidate
                break
        if found_path:
            resolved[key] = found_path
        else:
            # Fallback to STATIC_URL
            static_url = getattr(settings, 'STATIC_URL', '/static/')
            resolved[key] = f"{static_url.rstrip('/')}/{rel_path}"

    return resolved


def make_receipt_link_callback():
    """
    Constructs a link_callback for xhtml2pdf to resolve relative /static/ and /media/ URIs
    into local filesystem paths safely.
    """
    base_dir = getattr(settings, 'BASE_DIR', '')
    static_dirs = [
        getattr(settings, 'STATIC_ROOT', None),
        os.path.join(base_dir, 'heart_charity', 'static'),
        os.path.join(base_dir, 'staticfiles'),
    ]
    media_root = getattr(settings, 'MEDIA_ROOT', None)
    static_url = getattr(settings, 'STATIC_URL', '/static/')
    media_url = getattr(settings, 'MEDIA_URL', '/media/')

    def link_callback(uri, rel):
        if not uri:
            return ""

        # Convert backslashes
        uri_norm = uri.replace('\\', '/')

        if uri_norm.startswith(static_url):
            rel_part = uri_norm[len(static_url):].lstrip('/')
            for s_dir in static_dirs:
                if not s_dir:
                    continue
                candidate = os.path.join(s_dir, rel_part.replace('/', os.sep))
                if os.path.isfile(candidate):
                    return candidate
            return uri

        if media_root and uri_norm.startswith(media_url):
            rel_part = uri_norm[len(media_url):].lstrip('/')
            candidate = os.path.join(media_root, rel_part.replace('/', os.sep))
            if os.path.isfile(candidate):
                return candidate
            return uri

        if os.path.isfile(uri):
            return uri

        return uri

    return link_callback


def generate_receipt_pdf_bytes(record):
    """
    Renders the exact official receipt PDF bytes in-memory using existing templates:
    - Donation -> donation_receipt.html
    - DonationPaymentBox -> donation_owner_receipt_pdf.html
    """
    images = resolve_receipt_image_paths()
    link_cb = make_receipt_link_callback()

    # Determine whether record is a Donation or DonationPaymentBox
    is_danpeti = hasattr(record, 'donation_box')

    if is_danpeti:
        donor = getattr(record, 'owner', None)
        context = {
            'payment': record,
            'donor': donor,
            'owner': getattr(record, 'owner', None),
            'preview': False,
            'logo_url': images.get('logo_url'),
            'signature_url': images.get('signature_url'),
            'facebook_icon': images.get('facebook_icon'),
            'instagram_icon': images.get('instagram_icon'),
            'youtube_icon': images.get('youtube_icon'),
            'globe_icon': images.get('globe_icon'),
        }
        template_name = 'donation_owner_receipt_pdf.html'
    else:
        context = {
            'donation': record,
            'preview': False,
            'logo_url': images.get('logo_url'),
            'signature_url': images.get('signature_url'),
            'facebook_icon': images.get('facebook_icon'),
            'instagram_icon': images.get('instagram_icon'),
            'youtube_icon': images.get('youtube_icon'),
            'globe_icon': images.get('globe_icon'),
        }
        template_name = 'donation_receipt.html'

    html = render_to_string(template_name, context)

    buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=buffer, link_callback=link_cb)

    if pisa_status.err:
        logger.error(
            "[receipt service] xhtml2pdf error generating receipt for %s ID %s: %s",
            record.__class__.__name__, record.id, pisa_status.err
        )
        raise RuntimeError(f"xhtml2pdf receipt generation failed with error code: {pisa_status.err}")

    pdf_bytes = buffer.getvalue()
    if not pdf_bytes:
        raise RuntimeError(f"xhtml2pdf generated empty PDF buffer for {record.__class__.__name__} ID {record.id}")

    logger.info(
        "[receipt service] Successfully generated PDF for %s ID %s (%d bytes)",
        record.__class__.__name__, record.id, len(pdf_bytes)
    )
    return pdf_bytes


def get_accessible_gcs_url(gcs_filename, expiration_hours=72):
    """
    Generates a secure, time-limited signed URL or accessible URL for the uploaded receipt PDF.
    Valid for long enough (e.g. 72 hours / 3 days) for 11za WhatsApp API to download and deliver the PDF.
    Does not make the bucket public.
    """
    try:
        storage = getattr(default_storage, '_wrapped', default_storage)
        bucket = getattr(storage, 'bucket', None)

        if bucket:
            blob = bucket.blob(gcs_filename)
            params = {
                "expiration": timedelta(hours=expiration_hours),
                "version": "v4",
            }
            if getattr(storage, 'iam_sign_blob', False):
                try:
                    sa_email, token = storage._get_iam_sign_blob_params()
                    params["service_account_email"] = sa_email
                    params["access_token"] = token
                except Exception as iam_err:
                    logger.debug("[gcs] IAM sign blob params not available: %s", iam_err)

            try:
                signed_url = blob.generate_signed_url(**params)
                if signed_url:
                    return signed_url
            except Exception as sign_err:
                logger.debug("[gcs] blob.generate_signed_url failed: %s", sign_err)

            if hasattr(blob, 'public_url') and blob.public_url:
                return blob.public_url
    except Exception as ex:
        logger.warning("[gcs] Could not generate GCS signed URL: %s", ex)

    # Standard fallback via default_storage.url
    try:
        return default_storage.url(gcs_filename)
    except Exception as ex:
        logger.error("[gcs] Failed to resolve URL for %s: %s", gcs_filename, ex)
        bucket_name = getattr(settings, 'GS_BUCKET_NAME', 'ahinsadham-bucket')
        return f"https://storage.googleapis.com/{bucket_name}/{gcs_filename}"


def get_or_upload_receipt_pdf(record):
    """
    Ensures the generated PDF receipt exists on Google Cloud Storage in 'donation_receipts/'.
    Requirements:
    - Unique filename per receipt.
    - Does not overwrite previously generated receipts.
    - Returns (gcs_path, document_url).
    """
    receipt_id = getattr(record, 'receipt_id', None) or f"{record.__class__.__name__}_{record.id}"
    safe_receipt_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(receipt_id))
    gcs_filename = f"donation_receipts/Donation_Receipt_{safe_receipt_id}.pdf"

    already_exists = False
    try:
        already_exists = default_storage.exists(gcs_filename)
    except Exception as ex:
        logger.warning("[receipt service] Could not check exists for %s: %s", gcs_filename, ex)

    if not already_exists:
        pdf_bytes = generate_receipt_pdf_bytes(record)
        default_storage.save(gcs_filename, ContentFile(pdf_bytes))
        logger.info(
            "[receipt service] Saved new receipt PDF to storage: %s (%d bytes)",
            gcs_filename, len(pdf_bytes)
        )
    else:
        logger.info("[receipt service] Reusing existing stored receipt PDF: %s", gcs_filename)

    document_url = get_accessible_gcs_url(gcs_filename)
    return gcs_filename, document_url


def get_donation_type(record):
    """
    Identifies the donation type:
    - 'DANPETI': Box / Daanpeti collection (DonationPaymentBox).
    - 'ACH': Online Razorpay / ACH donation (receipt_id starts with 'ACH' or Razorpay transaction).
    - 'OTHER': CRM Other Donation with manual staff verification.
    """
    if hasattr(record, 'donation_box'):
        return 'DANPETI'
    receipt_id = str(getattr(record, 'receipt_id', '') or '')
    if receipt_id.startswith('ACH'):
        return 'ACH'
    tx_id = str(getattr(record, 'transaction_id', '') or '')
    if tx_id.startswith(('pay_', 'order_')) and not getattr(record, 'check_no', None):
        return 'ACH'
    return 'OTHER'


def extract_donor_details(record):
    """
    Extracts the four WhatsApp template variables and donor contact number:
    {{1}} = Donor Name
    {{2}} = Donation Amount
    {{3}} = Donation Date
    {{4}} = Receipt Number
    phone = WhatsApp / Contact Number
    error_message = Error string if donor identification or status check fails

    Applies the specific donor identification rules for each of the three donation types:
    1. OTHER:
       - Match both PAN Number and Donor Name against DonorVolunteer.
       - Disallows matching on Name alone or PAN alone.
       - Do not select an arbitrary record if multiple records match.
       - Fetches registered mobile from the verified matching DonorVolunteer record.
    2. ACH:
       - No PAN + Name verification required.
       - Identifies associated DonorVolunteer from the ACH relationship.
       - Validates successful payment status.
       - Fetches registered mobile from associated DonorVolunteer.
    3. DANPETI:
       - No PAN + Name verification required.
       - Identifies the actual individual donor and prioritizes individual donor's mobile number.
       - Never guesses a mobile number.
    """
    dtype = get_donation_type(record)
    error_message = None

    if dtype == 'DANPETI':
        # DonationPaymentBox
        first = getattr(record, 'first_name', '') or ''
        last = getattr(record, 'last_name', '') or ''
        donor_name = f"{first} {last}".strip()
        owner = getattr(record, 'owner', None)
        donor_type = getattr(record, 'donor_type', '')

        # Prioritize individual donor's mobile number
        phone = getattr(record, 'mobile_number', None)

        if not phone and donor_type == 'Danpeti Owner' and owner:
            phone = getattr(owner, 'whatsapp_number', None) or getattr(owner, 'contact_number', None)
            if not donor_name:
                donor_name = f"{getattr(owner, 'first_name', '') or ''} {getattr(owner, 'last_name', '') or ''}".strip() or "Danpeti Owner"

        if not donor_name and owner:
            donor_name = f"{getattr(owner, 'first_name', '') or ''} {getattr(owner, 'last_name', '') or ''}".strip()
        if not donor_name:
            donor_name = "Valued Donor"

        if not phone:
            error_message = f"Danpeti donation ID {record.id} does not have a registered mobile number for the donor"

        amount_val = getattr(record, 'amount', 0)
        dt_val = getattr(record, 'date_time', None) or getattr(record, 'created_at', None) or timezone.now()
        receipt_id = getattr(record, 'receipt_id', None) or str(record.id)

    elif dtype == 'ACH':
        # ACH Donation via online payment gateway
        donor = getattr(record, 'donor', None)
        donor_name = getattr(record, 'display_name', '') or ''
        if not donor_name and donor:
            donor_name = f"{getattr(donor, 'first_name', '') or ''} {getattr(donor, 'last_name', '') or ''}".strip()
        if not donor_name:
            donor_name = "Valued Donor"

        # Check ACH payment status (must be successful/completed, not pending or failed)
        payment_status = getattr(record, 'payment_status', None)
        status_name = str(getattr(payment_status, 'lookup_name', '') or '').strip().lower()
        if status_name in ['failed', 'rejected', 'pending', 'cancelled']:
            error_message = f"ACH Donation {record.id} has non-successful payment status: '{status_name}'"

        phone = None
        if donor:
            phone = getattr(donor, 'whatsapp_number', None) or getattr(donor, 'contact_number', None)

        if not phone and not error_message:
            error_message = f"Associated DonorVolunteer record (ID {getattr(donor, 'id', None)}) for ACH donation has no registered mobile number"

        amount_val = getattr(record, 'donation_amount_paid', None)
        if amount_val is None:
            amount_val = getattr(record, 'donation_amount_declared', 0)

        dt_val = getattr(record, 'donation_date', None) or getattr(record, 'created_at', None) or timezone.now()
        receipt_id = getattr(record, 'receipt_id', None) or str(record.id)

    else:
        # Other Donation (CRM Module with verification)
        donor = getattr(record, 'donor', None)
        if not donor:
            error_message = f"Other Donation {record.id} has no linked DonorVolunteer record"
            donor_name = getattr(record, 'display_name', '') or "Valued Donor"
            phone = None
        else:
            from .models import DonorVolunteer
            donor_obj = DonorVolunteer.objects.filter(id=donor.id, is_deleted=False).first() or donor

            pan = (getattr(donor_obj, 'pan_number', None) or "").strip().upper()
            donor_first = (getattr(donor_obj, 'first_name', None) or "").strip()
            donor_middle = (getattr(donor_obj, 'middle_name', None) or "").strip()
            donor_last = (getattr(donor_obj, 'last_name', None) or "").strip()

            db_name_fl = f"{donor_first} {donor_last}".strip()
            db_name_full = " ".join([p for p in [donor_first, donor_middle, donor_last] if p]).strip()

            raw_display_name = (getattr(record, 'display_name', None) or "").strip()

            # Clean display_name if it was populated from the dropdown display label format "Name - PAN"
            clean_display_name = raw_display_name
            if pan:
                clean_display_name = re.sub(rf"\s*-\s*{re.escape(pan)}\s*$", "", clean_display_name, flags=re.IGNORECASE).strip()

            # If record.display_name had the raw dropdown suffix, sanitize and update record in DB
            if raw_display_name != clean_display_name and clean_display_name and getattr(record, 'id', None) and hasattr(record, 'save'):
                try:
                    record.display_name = clean_display_name
                    record.save(update_fields=['display_name'])
                except Exception:
                    pass

            target_name = clean_display_name or db_name_full or db_name_fl

            if not pan:
                error_message = f"Donor identification failed for Other Donation {record.id}: DonorVolunteer ID {donor_obj.id} has no registered PAN Number (PAN + Name match required)"
                phone = None
                donor_name = target_name or "Valued Donor"
            elif not target_name:
                error_message = f"Donor identification failed for Other Donation {record.id}: Missing Donor Name (PAN + Name match required)"
                phone = None
                donor_name = "Valued Donor"
            else:
                def _norm(s):
                    return " ".join((s or "").strip().split()).lower()

                norm_target = _norm(target_name)
                norm_db_fl = _norm(db_name_fl)
                norm_db_full = _norm(db_name_full)

                pan_matches = DonorVolunteer.objects.filter(pan_number__iexact=pan, is_deleted=False)
                verified_matches = []
                for dv in pan_matches:
                    dv_first = (dv.first_name or "").strip()
                    dv_middle = (dv.middle_name or "").strip()
                    dv_last = (dv.last_name or "").strip()
                    dv_fl = _norm(f"{dv_first} {dv_last}")
                    dv_full = _norm(" ".join([p for p in [dv_first, dv_middle, dv_last] if p]))

                    if norm_target == dv_fl or norm_target == dv_full:
                        verified_matches.append(dv)
                    elif dv.id == donor_obj.id and (norm_target == norm_db_fl or norm_target == norm_db_full):
                        verified_matches.append(dv)

                if len(verified_matches) == 0:
                    error_message = f"Donor verification failed for Other Donation {record.id}: Name and PAN do not match (No DonorVolunteer record matches both PAN '{pan}' and Name '{target_name}')"
                    phone = None
                    donor_name = target_name
                elif len(verified_matches) > 1:
                    # Ambiguous match! If the linked donor is in verified_matches, use the exact record
                    if any(dv.id == donor_obj.id for dv in verified_matches):
                        verified_donor = donor_obj
                        donor_name = target_name or db_name_fl
                        phone = getattr(verified_donor, 'whatsapp_number', None) or getattr(verified_donor, 'contact_number', None)
                    else:
                        error_message = f"Ambiguous donor verification for Other Donation {record.id}: Multiple records match PAN '{pan}' and Name '{target_name}'. Cannot select an arbitrary record."
                        phone = None
                        donor_name = target_name
                else:
                    verified_donor = verified_matches[0]
                    donor_name = target_name or f"{verified_donor.first_name or ''} {verified_donor.last_name or ''}".strip()
                    phone = getattr(verified_donor, 'whatsapp_number', None) or getattr(verified_donor, 'contact_number', None)

        amount_val = getattr(record, 'donation_amount_paid', None)
        if amount_val is None:
            amount_val = getattr(record, 'donation_amount_declared', 0)

        dt_val = getattr(record, 'donation_date', None) or getattr(record, 'created_at', None) or timezone.now()
        receipt_id = getattr(record, 'receipt_id', None) or str(record.id)

    # Format amount
    try:
        flt_amount = float(amount_val or 0)
        if flt_amount.is_integer():
            amount_str = str(int(flt_amount))
        else:
            amount_str = f"{flt_amount:.2f}"
    except (TypeError, ValueError):
        amount_str = str(amount_val or "0")

    # Format date
    try:
        if hasattr(dt_val, 'strftime'):
            date_str = dt_val.strftime("%d-%b-%Y")
        else:
            date_str = str(dt_val)
    except Exception:
        date_str = str(dt_val)

    return donor_name, amount_str, date_str, receipt_id, phone, error_message


def _safe_get_receipt_log(receipt_id):
    """
    Safely retrieves the DonationWhatsAppReceipt log without failing if table is unmigrated.
    """
    try:
        from .models import DonationWhatsAppReceipt
        return DonationWhatsAppReceipt.objects.filter(receipt_id=str(receipt_id)).first()
    except Exception as ex:
        logger.debug("[receipt service] Could not query DonationWhatsAppReceipt: %s", ex)
        return None


def _safe_record_receipt_log(receipt_id, record=None, **fields):
    """
    Safely creates or updates the DonationWhatsAppReceipt record.
    """
    try:
        from .models import DonationWhatsAppReceipt, Donation, DonationPaymentBox
        defaults = dict(fields)
        if record:
            if isinstance(record, Donation):
                defaults['donation'] = record
            elif isinstance(record, DonationPaymentBox):
                defaults['donation_payment_box'] = record

        log_obj, _ = DonationWhatsAppReceipt.objects.update_or_create(
            receipt_id=str(receipt_id),
            defaults=defaults
        )
        return log_obj
    except Exception as ex:
        logger.warning("[receipt service] Could not write DonationWhatsAppReceipt: %s", ex)
        return None


def deliver_donation_receipt_whatsapp(record, force_resend=False):
    """
    Main orchestration entry point:
    Triggered only when a donation/payment is successfully completed and verified with receipt_id.

    Execution Steps:
    1. Verify record eligibility (verified=True and receipt_id present).
    2. Extract donor details & mobile number.
    3. Check duplicate protection (do not resend if already SENT unless force_resend=True).
    4. Generate PDF receipt and upload to Google Cloud Storage (or reuse existing).
    5. Dispatch WhatsApp document message via 11za (template: utility_5671).
    6. Record delivery status and audit log.
    7. Failure is non-blocking to caller (never undoes donation or payment).
    """
    if not record:
        logger.warning("[receipt service] deliver_donation_receipt_whatsapp called with None record")
        return {"success": False, "error": "No donation record provided"}

    # 1. Eligibility Check: must be verified and have receipt_id
    receipt_id = getattr(record, 'receipt_id', None)
    is_verified = getattr(record, 'verified', False)

    if not is_verified or not receipt_id:
        logger.info(
            "[receipt service] Skipping WhatsApp receipt for %s ID %s: verified=%s, receipt_id=%s",
            record.__class__.__name__, record.id, is_verified, receipt_id
        )
        return {
            "success": False,
            "error": "Donation is not yet verified or receipt number has not been generated",
            "skipped": True,
        }

    # 2. Extract Donor Details
    donor_name, amount_str, date_str, receipt_id, raw_phone, error_message = extract_donor_details(record)

    if error_message:
        logger.warning(
            "[receipt service] Cannot dispatch WhatsApp receipt %s: %s",
            receipt_id, error_message
        )
        _safe_record_receipt_log(
            receipt_id=receipt_id,
            record=record,
            recipient_phone=str(raw_phone or ""),
            donor_name=donor_name,
            amount=amount_str,
            donation_date=date_str,
            status='FAILED',
            error_message=error_message,
        )
        return {
            "success": False,
            "error": error_message,
            "receipt_id": receipt_id,
        }

    # 3. Check Phone Number
    formatted_phone = validate_and_format_phone(raw_phone)
    if not formatted_phone:
        logger.warning(
            "[receipt service] Cannot dispatch WhatsApp receipt %s: Missing or invalid mobile number (%s)",
            receipt_id, mask_phone(raw_phone)
        )
        _safe_record_receipt_log(
            receipt_id=receipt_id,
            record=record,
            recipient_phone=str(raw_phone or ""),
            donor_name=donor_name,
            amount=amount_str,
            donation_date=date_str,
            status='FAILED',
            error_message="Missing or invalid donor mobile number",
        )
        return {
            "success": False,
            "error": f"Donor mobile number is missing or invalid: {mask_phone(raw_phone)}",
            "receipt_id": receipt_id,
        }

    # 4. Duplicate Protection Check
    existing_log = _safe_get_receipt_log(receipt_id)
    if existing_log and existing_log.status == 'SENT' and not force_resend:
        logger.info(
            "[receipt service] WhatsApp receipt for %s was already delivered to %s (messageId=%s). Skipping duplicate dispatch.",
            receipt_id, mask_phone(existing_log.recipient_phone), existing_log.message_id
        )
        return {
            "success": True,
            "already_sent": True,
            "receipt_id": receipt_id,
            "phone": mask_phone(existing_log.recipient_phone),
            "message_id": existing_log.message_id,
            "status": "ALREADY_SENT",
            "message": f"WhatsApp receipt already delivered previously to {mask_phone(existing_log.recipient_phone)}.",
        }

    # 5. Generate PDF and Upload to Google Cloud Storage
    try:
        gcs_path, document_url = get_or_upload_receipt_pdf(record)
    except Exception as pdf_err:
        err_msg = f"Failed to generate or upload receipt PDF: {pdf_err}"
        logger.error("[receipt service] %s", err_msg, exc_info=True)
        _safe_record_receipt_log(
            receipt_id=receipt_id,
            record=record,
            recipient_phone=formatted_phone,
            donor_name=donor_name,
            amount=amount_str,
            donation_date=date_str,
            status='FAILED',
            error_message=err_msg,
        )
        return {
            "success": False,
            "error": err_msg,
            "receipt_id": receipt_id,
        }

    # Create/update log in PENDING status before API call
    retry_count = (existing_log.retry_count + 1) if existing_log else 0
    _safe_record_receipt_log(
        receipt_id=receipt_id,
        record=record,
        recipient_phone=formatted_phone,
        donor_name=donor_name,
        amount=amount_str,
        donation_date=date_str,
        gcs_path=gcs_path,
        document_url=document_url,
        status='PENDING',
        retry_count=retry_count,
    )

    # 6. Dispatch via 11za WhatsApp API
    safe_doc_id = re.sub(r'[^a-zA-Z0-9_-]', '_', str(receipt_id))
    document_filename = f"Donation_Receipt_{safe_doc_id}.pdf"
    api_result = send_donation_receipt_whatsapp(
        phone=formatted_phone,
        donor_name=donor_name,
        amount=amount_str,
        donation_date=date_str,
        receipt_id=receipt_id,
        document_url=document_url,
        document_filename=document_filename,
    )

    # 7. Record Delivery Result
    if api_result.get("success"):
        message_id = api_result.get("message_id")
        _safe_record_receipt_log(
            receipt_id=receipt_id,
            record=record,
            recipient_phone=formatted_phone,
            donor_name=donor_name,
            amount=amount_str,
            donation_date=date_str,
            gcs_path=gcs_path,
            document_url=document_url,
            status='SENT',
            message_id=message_id,
            error_message=None,
            response_payload=api_result.get("response"),
            sent_at=timezone.now(),
            retry_count=retry_count,
        )
        logger.info(
            "[receipt service] Automatic WhatsApp receipt %s successfully sent to %s (messageId=%s)",
            receipt_id, mask_phone(formatted_phone), message_id
        )
        return {
            "success": True,
            "already_sent": False,
            "receipt_id": receipt_id,
            "phone": mask_phone(formatted_phone),
            "message_id": message_id,
            "document_url": document_url,
            "status": "SENT",
            "message": f"WhatsApp receipt successfully delivered to donor ({mask_phone(formatted_phone)})!",
        }
    else:
        err_msg = api_result.get("error") or "Unknown 11za API failure"
        _safe_record_receipt_log(
            receipt_id=receipt_id,
            record=record,
            recipient_phone=formatted_phone,
            donor_name=donor_name,
            amount=amount_str,
            donation_date=date_str,
            gcs_path=gcs_path,
            document_url=document_url,
            status='FAILED',
            error_message=err_msg,
            response_payload=api_result.get("response"),
            retry_count=retry_count,
        )
        logger.error(
            "[receipt service] WhatsApp receipt %s failed delivery to %s: %s",
            receipt_id, mask_phone(formatted_phone), err_msg
        )
        return {
            "success": False,
            "error": err_msg,
            "receipt_id": receipt_id,
            "phone": formatted_phone,
            "status": "FAILED",
        }


def retry_failed_whatsapp_receipt(receipt_id):
    """
    Retries sending a previously failed WhatsApp receipt without generating a duplicate receipt.
    Looks up the donation record by receipt_id and forces re-dispatch.
    """
    from .models import Donation, DonationPaymentBox

    # Look up in Donation first
    record = Donation.objects.filter(receipt_id=receipt_id).first()
    if not record:
        record = DonationPaymentBox.objects.filter(receipt_id=receipt_id).first()

    if not record:
        return {"success": False, "error": f"No donation record found with receipt ID '{receipt_id}'"}

    return deliver_donation_receipt_whatsapp(record, force_resend=True)

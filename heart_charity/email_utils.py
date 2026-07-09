import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

# Setup logger for recording errors
logger = logging.getLogger(__name__)

def send_donation_success_email(donation, recipient_email=None):
    """
    Sends a professional HTML thank-you email to the donor with donation and transaction details.
    This function handles errors gracefully and logs them so it doesn't affect user experience.
    """
    donor = getattr(donation, 'donor', None)
    if not recipient_email:
        recipient_email = getattr(donor, 'email', None)

    if not recipient_email:
        logger.info(f"Skipping donation success email for Donation ID {donation.id}: No donor or email address associated.")
        return False

    recipient_email = recipient_email.strip().lower()
    subject = "Thank you for your generous donation to Ahinsadham"
    
    # Context variables for rendering the template
    if donor:
        donor_name = ' '.join(filter(None, [donor.first_name, donor.middle_name, donor.last_name])).strip() or "Valued Donor"
    else:
        donor_name = "Valued Donor"
    donation_amount = donation.donation_amount_paid
    transaction_id = donation.transaction_id or "-"
    receipt_id = donation.receipt_id or "-"
    donation_date = donation.donation_date.strftime('%d-%b-%Y') if donation.donation_date else "-"

    context = {
        'donor_name': donor_name,
        'donation_amount': str(donation_amount),
        'transaction_id': transaction_id,
        'receipt_id': receipt_id,
        'donation_date': donation_date,
    }

    try:
        # Render professional HTML template
        html_content = render_to_string("emails/donation_success_email.html", context)
        # Create text fallback by stripping HTML tags
        text_content = strip_tags(html_content)

        # Construct EmailMultiAlternatives message
        email_msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.EMAIL_HOST_USER,
            to=[recipient_email],
        )
        email_msg.attach_alternative(html_content, "text/html")
        
        # Optionally render and attach the PDF receipt directly if required
        try:
            from xhtml2pdf import pisa
            from io import BytesIO
            
            # Generate same receipt PDF using donation_receipt.html
            logo_url = settings.STATIC_URL + "images/alogo.png"
            signature_url = settings.STATIC_URL + "images/signature.png"
            facebook_icon = settings.STATIC_URL + "images/facebook.png"
            instagram_icon = settings.STATIC_URL + "images/instagram.png"
            youtube_icon = settings.STATIC_URL + "images/youtube.png"
            globe_icon = settings.STATIC_URL + "images/globe.png"

            pdf_html = render_to_string(
                "donation_receipt.html",
                {
                    "donation": donation,
                    "logo_url": logo_url,
                    "signature_url": signature_url,
                    "facebook_icon": facebook_icon,
                    "instagram_icon": instagram_icon,
                    "youtube_icon": youtube_icon,
                    "globe_icon": globe_icon,
                    "preview": False,
                }
            )
            
            pdf_buffer = BytesIO()
            pisa_status = pisa.CreatePDF(pdf_html, dest=pdf_buffer)
            if not pisa_status.err:
                pdf_data = pdf_buffer.getvalue()
                email_msg.attach(f"donation_receipt_{receipt_id}.pdf", pdf_data, "application/pdf")
        except Exception as pdf_err:
            logger.warning(f"Could not attach PDF receipt to donation email for ID {donation.id}: {pdf_err}")

        # Send email
        email_msg.send(fail_silently=False)
        logger.info(f"Donation success email successfully sent to {recipient_email} for Donation ID {donation.id}.")
        return True
    except Exception as e:
        logger.error(f"Failed to send donation success email to {recipient_email} for Donation ID {donation.id}: {e}", exc_info=True)
        return False

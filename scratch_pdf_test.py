import os
import sys
import django

# Set up Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ngo.settings")
django.setup()

from django.template.loader import render_to_string
from xhtml2pdf import pisa
from heart_charity.models import Donation, DonationPaymentBox, DonorVolunteer

def generate_test_pdf():
    # Fetch a dummy or actual donation to render
    donation = Donation.objects.first()
    if not donation:
        print("No donation found in the database. Please add one or mock it.")
        return

    context = {
        "donation": donation,
        "logo_url": "staticfiles/images/alogo.png",
        "signature_url": "staticfiles/images/signature.png",
        "facebook_icon": "staticfiles/images/facebook.png",
        "instagram_icon": "staticfiles/images/instagram.png",
        "youtube_icon": "staticfiles/images/youtube.png",
        "globe_icon": "staticfiles/images/globe.png",
        "preview": False,
    }
    
    html = render_to_string("donation_receipt.html", context)
    print("HTML START:\n", html[:400])
    with open("test_donation_receipt.pdf", "wb") as f:
        pisa_status = pisa.CreatePDF(html, dest=f)
    print("Donation PDF status:", pisa_status.err)

    # Print dimensions of test_donation_receipt.pdf
    from pypdf import PdfReader
    reader = PdfReader("test_donation_receipt.pdf")
    page = reader.pages[0]
    box = page.mediabox
    print(f"Page dimensions: width={box.width} pt ({box.width * 0.352778:.1f} mm), height={box.height} pt ({box.height * 0.352778:.1f} mm)")

    # Fetch a payment
    payment = DonationPaymentBox.objects.first()
    if payment:
        donor = payment.owner
        context_owner = {
            "payment": payment,
            "donor": donor,
            "logo_url": "staticfiles/images/alogo.png",
            "signature_url": "staticfiles/images/signature.png",
            "facebook_icon": "staticfiles/images/facebook.png",
            "instagram_icon": "staticfiles/images/instagram.png",
            "youtube_icon": "staticfiles/images/youtube.png",
            "globe_icon": "staticfiles/images/globe.png",
            "pdf": True,
        }
        html_owner = render_to_string("donation_owner_receipt_pdf.html", context_owner)
        with open("test_danpeti_receipt.pdf", "wb") as f:
            pisa_status_owner = pisa.CreatePDF(html_owner, dest=f)
        print("Danpeti PDF status:", pisa_status_owner.err)

if __name__ == "__main__":
    generate_test_pdf()

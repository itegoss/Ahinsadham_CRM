from django.db import transaction
from django.utils import timezone
from .models import ReceiptSequence

def generate_receipt_id():
    prefix = "RCPT"
    year = timezone.now().year

    with transaction.atomic():
        seq, created = ReceiptSequence.objects.select_for_update().get_or_create(
            year=year
        )
        seq.last_number += 1
        seq.save()

        return f"{prefix}-{year}-{seq.last_number:04d}"

def generate_ach_receipt_id():
    import re
    from .models import Donation
    with transaction.atomic():
        # Find the last Donation with receipt_id starting with 'ACH-'
        last_donation = Donation.objects.filter(
            receipt_id__istartswith="ACH-"
        ).order_by('-id').first()
        
        next_num = 1
        if last_donation and last_donation.receipt_id:
            # Try to extract the number
            match = re.search(r'ACH-(\d+)', last_donation.receipt_id, re.IGNORECASE)
            if match:
                try:
                    next_num = int(match.group(1)) + 1
                except ValueError:
                    pass
        return f"ACH-{next_num:04d}"

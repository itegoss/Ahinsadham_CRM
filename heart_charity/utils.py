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

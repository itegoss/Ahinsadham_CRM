from datetime import timezone
from django.utils import timezone
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db import models
from .models import Donation, DonationPaymentBox, DonationPaymentBox_Hist, Donation_Hist,UserRole,UserRole_Hist


@receiver(post_save, sender=DonationPaymentBox)
def create_history(sender, instance, created, **kwargs):

    DonationPaymentBox_Hist.objects.create(
        payment=instance,
        
        owner=instance.owner,
        donation_box=instance.donation_box,
        address=instance.address,
        
        opened_by=instance.opened_by,
        received_by=instance.received_by,
        amount=instance.amount,
        payment_method=instance.payment_method,
        
        date_time=instance.date_time,
        i_witness=instance.i_witness,
        
        created_by=instance.created_by,
        updated_by=instance.updated_by,
        
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        is_deleted=instance.is_deleted,
        deleted_at=instance.deleted_at,

        action="INSERT" if created else "UPDATE"
    )



from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Donation)
def create_donation_history(sender, instance, created, **kwargs):

    action = "INSERT" if created else "UPDATE"

    Donation_Hist.objects.create(
        donation=instance,
        donor=instance.donor,
        donation_date=instance.donation_date,
        donation_category=instance.donation_category,
        donation_sub_category=instance.donation_sub_category,
        payment_method=instance.payment_method,
        payment_status=instance.payment_status,

        transaction_id=instance.transaction_id,
        receipt_id=instance.receipt_id,

        place_of_donation=instance.place_of_donation,
        check_no=instance.check_no,
        donation_received_by=instance.donation_received_by,
        reference_name=instance.reference_name,
        description=instance.description,

        donation_amount_declared=instance.donation_amount_declared,
        donation_amount_paid=instance.donation_amount_paid,

        created_by=instance.created_by,
        updated_by=instance.updated_by,

        created_at=instance.created_at,
        updated_at=instance.updated_at,

        is_deleted=instance.is_deleted,
        deleted_at=instance.deleted_at,

        action=action
    )


@receiver(pre_save, sender=Donation)
def donation_soft_delete_history(sender, instance, **kwargs):
    if not instance.pk:
        return  # only for updates

    old = Donation.objects.get(pk=instance.pk)

    if old.is_deleted is False and instance.is_deleted is True:
        Donation_Hist.objects.create(
            donation=instance,
            donor=old.donor,
            donation_date=old.donation_date,
            donation_category=old.donation_category,
            donation_sub_category=old.donation_sub_category,
            payment_method=old.payment_method,
            payment_status=old.payment_status,

            transaction_id=old.transaction_id,
            receipt_id=old.receipt_id,

            place_of_donation=old.place_of_donation,
            check_no=old.check_no,
            donation_received_by=old.donation_received_by,
            reference_name=old.reference_name,
            description=old.description,

            donation_amount_declared=old.donation_amount_declared,
            donation_amount_paid=old.donation_amount_paid,

            created_by=old.created_by,
            updated_by=old.updated_by,

            created_at=old.created_at,
            updated_at=old.updated_at,

            is_deleted=True,
            deleted_at=timezone.now(),

            action="DELETE"
        )

@receiver(post_save, sender=UserRole)
def userrole_history_create(sender, instance, created, **kwargs):
    action = "INSERT" if created else "UPDATE"

    UserRole_Hist.objects.create(
        user_role=instance,
        user=instance.user,
        role=instance.role,

        is_deleted=instance.is_deleted,
        deleted_at=instance.deleted_at,

        created_by=instance.created_by,
        created_date=instance.created_date,
        updated_by=instance.updated_by,
        updated_date=instance.updated_date,

        action=action
    )
@receiver(pre_save, sender=UserRole)
def userrole_soft_delete(sender, instance, **kwargs):
    if not instance.pk:
        return

    old = UserRole.objects.get(pk=instance.pk)

    # When soft delete happens
    if old.is_deleted is False and instance.is_deleted is True:
        UserRole_Hist.objects.create(
            user_role=instance,
            user=old.user,
            role=old.role,

            is_deleted=True,
            deleted_at=timezone.now(),

            created_by=old.created_by,
            created_date=old.created_date,
            updated_by=old.updated_by,
            updated_date=timezone.now(),

            action="DELETE"
        )




from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Donation,  DonationPaymentBox
from .utils import generate_receipt_id


# @receiver(pre_save, sender=Donation)
# def donation_receipt(sender, instance, **kwargs):
#     if not instance.receipt_id:
#         instance.receipt_id = generate_receipt_id()
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now

from .models import Donation
from .utils import generate_receipt_id


@receiver(post_save, sender=Donation)
def generate_receipt_on_verification(sender, instance, created, **kwargs):
    """
    Generate receipt ONLY when:
    - record already exists (not created)
    - verified = True
    - receipt_id is empty
    """

    # ❌ Skip initial creation
    if created:
        return

    # ✅ Generate receipt ONLY once
    if instance.verified and not instance.receipt_id:
        instance.receipt_id = generate_receipt_id()
        instance.verified_at = instance.verified_at or now()

        # prevent infinite loop using update_fields
        instance.save(update_fields=["receipt_id", "verified_at"])


# @receiver(pre_save, sender=DonationPaymentBox)
# def danpeti_receipt(sender, instance, **kwargs):
#     if not instance.receipt_id:
#         instance.receipt_id = generate_receipt_id()



from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now

from .models import DonationPaymentBox
from .utils import generate_receipt_id


@receiver(post_save, sender=DonationPaymentBox)
def generate_danpeti_receipt(sender, instance, created, **kwargs):
    """
    Generate receipt ONLY after verification
    """

    # ❌ Skip initial creation
    if created:
        return

    # ✅ Generate receipt ONLY once, AFTER verification
    if instance.verified and not instance.receipt_id:
        instance.receipt_id = generate_receipt_id()
        instance.verified_at = instance.verified_at or now()

        # prevent recursive save
        instance.save(update_fields=["receipt_id", "verified_at"])

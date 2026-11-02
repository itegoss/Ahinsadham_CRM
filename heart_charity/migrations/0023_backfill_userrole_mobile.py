import re
from django.db import migrations


def backfill_mobile_numbers(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserRole = apps.get_model('heart_charity', 'UserRole')

    # 1. Known staff mappings
    known_mappings = {
        'sangalevarsha04': '7798354386',
        'admin': '7208542366',
        'hirensangoi1': '9702440660',
    }

    for username, mobile in known_mappings.items():
        try:
            user = User.objects.filter(username=username).first()
            if user:
                user_role, _ = UserRole.objects.get_or_create(user=user)
                if not user_role.mobile_number:
                    user_role.mobile_number = mobile
                    user_role.save(update_fields=['mobile_number'])
        except Exception:
            pass

    # 2. Backfill from OwnerDetail
    try:
        OwnerDetail = apps.get_model('heart_charity', 'OwnerDetail')
        for owner in OwnerDetail.objects.filter(is_deleted=False).order_by('-id'):
            if not owner.email:
                continue
            phone = owner.whatsapp_number or owner.contact_number
            if not phone:
                continue
            digits = re.sub(r'\D', '', str(phone).strip())
            if len(digits) > 10:
                digits = digits[-10:]
            if len(digits) == 10 and digits[0] in '6789':
                user = User.objects.filter(email__iexact=owner.email.strip()).first()
                if user:
                    ur, _ = UserRole.objects.get_or_create(user=user)
                    if not ur.mobile_number:
                        ur.mobile_number = digits
                        ur.save(update_fields=['mobile_number'])
    except Exception:
        pass

    # 3. Backfill from DonorVolunteer
    try:
        DonorVolunteer = apps.get_model('heart_charity', 'DonorVolunteer')
        for donor in DonorVolunteer.objects.filter(is_deleted=False).order_by('-id'):
            if not donor.email:
                continue
            phone = donor.whatsapp_number or donor.contact_number
            if not phone:
                continue
            digits = re.sub(r'\D', '', str(phone).strip())
            if len(digits) > 10:
                digits = digits[-10:]
            if len(digits) == 10 and digits[0] in '6789':
                user = User.objects.filter(email__iexact=donor.email.strip()).first()
                if user:
                    ur, _ = UserRole.objects.get_or_create(user=user)
                    if not ur.mobile_number:
                        ur.mobile_number = digits
                        ur.save(update_fields=['mobile_number'])
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('heart_charity', '0022_userrole_mobile_number_whatsappotp'),
    ]

    operations = [
        migrations.RunPython(backfill_mobile_numbers, reverse_code=migrations.RunPython.noop),
    ]


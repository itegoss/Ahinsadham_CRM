# Generated manually to safely backfill collector and owner_detail relationships

from django.db import migrations


def backfill_relationships(apps, schema_editor):
    DonationBox = apps.get_model('heart_charity', 'DonationBox')
    Employee = apps.get_model('heart_charity', 'Employee')
    OwnerDetail = apps.get_model('heart_charity', 'OwnerDetail')

    # Build unique name lookups for Employees to ensure only unambiguous matches
    emp_by_fullname = {}
    emp_by_firstname = {}
    for emp in Employee.objects.all():
        first = (emp.first_name or '').strip().lower()
        last = (emp.last_name or '').strip().lower()
        full = f"{first} {last}".strip()
        if full:
            emp_by_fullname.setdefault(full, []).append(emp)
        if first:
            emp_by_firstname.setdefault(first, []).append(emp)

    # 1. Backfill owner_detail from existing OwnerDetail.donor_box reverse relationship
    for box in DonationBox.objects.all():
        if not box.owner_detail_id:
            active_owners = OwnerDetail.objects.filter(donor_box=box, is_deleted=False)
            if active_owners.count() == 1:
                box.owner_detail = active_owners.first()
                box.save(update_fields=['owner_detail'])
            elif not active_owners.exists():
                all_owners = OwnerDetail.objects.filter(donor_box=box)
                if all_owners.count() == 1:
                    box.owner_detail = all_owners.first()
                    box.save(update_fields=['owner_detail'])

    # 2. Backfill collector from box.box_owner if it matches an Employee unambiguously
    for box in DonationBox.objects.all():
        if not box.collector_id and box.box_owner:
            owner_clean = box.box_owner.strip().lower()
            matching_emps = emp_by_fullname.get(owner_clean, [])
            if len(matching_emps) == 1:
                box.collector = matching_emps[0]
                box.save(update_fields=['collector'])
            elif len(matching_emps) == 0:
                matching_first = emp_by_firstname.get(owner_clean, [])
                if len(matching_first) == 1:
                    box.collector = matching_first[0]
                    box.save(update_fields=['collector'])
            # If 0 matches (e.g. 'vidyaa') or >1 matches, do NOT guess; preserve existing data.


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('heart_charity', '0019_donationbox_collector_donationbox_owner_detail'),
    ]

    operations = [
        migrations.RunPython(backfill_relationships, reverse_backfill),
    ]

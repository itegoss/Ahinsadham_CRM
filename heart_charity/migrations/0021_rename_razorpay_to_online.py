from django.db import migrations

def rename_razorpay_to_online(apps, schema_editor):
    Lookup = apps.get_model('heart_charity', 'Lookup')
    Lookup.objects.filter(lookup_name__iexact='Razorpay').update(lookup_name='Online')

def reverse_rename(apps, schema_editor):
    Lookup = apps.get_model('heart_charity', 'Lookup')
    Lookup.objects.filter(lookup_name__iexact='Online').update(lookup_name='Razorpay')

class Migration(migrations.Migration):

    dependencies = [
        ('heart_charity', '0020_backfill_collector_and_owner_detail'),
    ]

    operations = [
        migrations.RunPython(rename_razorpay_to_online, reverse_rename),
    ]

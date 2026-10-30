from django.contrib import admin
from .models import DonationBox, Employee, OwnerDetail, Donation, DonorVolunteer, Lookup, LookupType


@admin.register(DonationBox)
class DonationBoxAdmin(admin.ModelAdmin):
    list_display = (
        'donation_id',
        'key_id',
        'box_size',
        'status',
        'get_collector_name',
        'get_owner_name',
        'box_percentage',
        'created_at',
        'is_deleted',
    )
    list_filter = ('status', 'box_size', 'is_deleted')
    search_fields = (
        'donation_id',
        'key_id',
        'old_box_id',
        'box_owner',
        'collector__first_name',
        'collector__last_name',
        'owner_detail__business_name',
        'owner_detail__first_name',
        'owner_detail__last_name',
    )
    raw_id_fields = ('collector', 'owner_detail', 'created_by', 'updated_by', 'deleted_by', 'uploaded_by')

    @admin.display(description='Collector')
    def get_collector_name(self, obj):
        if obj.collector:
            return f"{obj.collector.first_name or ''} {obj.collector.last_name or ''}".strip()
        return obj.box_owner or '—'

    @admin.display(description='Box Owner')
    def get_owner_name(self, obj):
        if obj.owner_detail:
            return str(obj.owner_detail)
        first_owner = obj.box_owner_details.filter(is_deleted=False).first() or obj.box_owner_details.first()
        if first_owner:
            return str(first_owner)
        return '—'


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'last_name', 'department', 'designation', 'contact_number', 'is_deleted')
    search_fields = ('first_name', 'last_name', 'contact_number', 'email', 'pan_number')
    list_filter = ('is_deleted', 'department', 'designation')


@admin.register(OwnerDetail)
class OwnerDetailAdmin(admin.ModelAdmin):
    list_display = ('id', 'business_name', 'first_name', 'last_name', 'contact_number', 'donor_box', 'is_deleted')
    search_fields = ('business_name', 'first_name', 'last_name', 'contact_number', 'pan_number')
    list_filter = ('is_deleted', 'city', 'state')

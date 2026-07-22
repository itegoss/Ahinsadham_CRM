from django.forms import ValidationError
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth import authenticate, login, logout
import random
from django.shortcuts import get_object_or_404
from requests import request
from .models import DonationBox, DonationPaymentBox, User ,Donation
from heart_charity.models import LookupType,Lookup,UserModuleAccess,Module,UserRole,User, DonationOwner, DonorVolunteer
from django.conf import settings
from django.contrib import messages
import csv
from django.http import HttpResponse
import json
from .utils import generate_receipt_id, generate_ach_receipt_id
from django.shortcuts import render, redirect


def home(req):
    return render(req,'home.html')

def signin_view(request):
    # try:
    #     user = User.objects.get(username="username")
    #     login(request, user)
    #     return redirect('welcome') 
    # except User.DoesNotExist:
    #     return render(request, 'signin.html', {"errmsg": """"""})
    try:
        user = User.objects.get(username="username")
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect('welcome')
    except User.DoesNotExist:
        return render(request, 'signin.html', {"errmsg": ""})

def access_control(request):
    modules = Module.objects.all()
    if request.method == "POST":
        role_name = request.POST.get("role_name")
        role_desc = request.POST.get("roleDescription")
        selected_modules = request.POST.getlist("selected_modules")
        # Fallback to single selected_module just in case
        if not selected_modules:
            single_module = request.POST.get("selected_module")
            if single_module:
                selected_modules = [single_module]

        can_access = bool(request.POST.get("access_permission"))
        can_add = bool(request.POST.get("add_permission"))
        can_edit = bool(request.POST.get("edit_permission"))
        can_delete = bool(request.POST.get("delete_permission"))
        can_view = bool(request.POST.get("view_permission"))

        if not role_name:
            messages.error(request, "Role name is required.")
            return redirect("access_control")
        if not selected_modules:
            messages.error(request, "Select at least one module.")
            return redirect("access_control")

        for module_id in selected_modules:
            try:
                module = Module.objects.get(id=module_id)
                role_obj, created = UserModuleAccess.objects.get_or_create(name=role_name, module=module)
                role_obj.description = role_desc
                role_obj.can_access = can_access
                role_obj.can_add = can_add
                role_obj.can_edit = can_edit
                role_obj.can_delete = can_delete
                role_obj.can_view = can_view
                if request.user.is_authenticated:
                    if created:
                        role_obj.created_by = request.user
                    role_obj.updated_by = request.user
                role_obj.save()
            except Module.DoesNotExist:
                continue

        messages.success(request, "Role & Permissions saved successfully!")
        return redirect("access_control")
    return render(request, "access_control.html", {
        "modules": modules,
    })

from django.db.models import Q
from django.utils.timezone import now
from django.utils import timezone
def show_lookup_data(request):
    lookup_types = LookupType.objects.filter(is_deleted=False)
    lookups = Lookup.objects.select_related("lookup_type").filter(is_deleted=False).order_by("id")

    return render(request, "lookup_display.html", {
        "lookup_types": lookup_types,
        "lookups": lookups
    })
from django.core.paginator import Paginator as DjangoPaginator
import hashlib
import time

_counts_cache = {}

class FastPaginator(DjangoPaginator):
    def __init__(self, object_list, per_page, orphans=0, allow_empty_first_page=True, ttl=10):
        self.ttl = ttl
        super().__init__(object_list, per_page, orphans, allow_empty_first_page)

    @property
    def count(self):
        c = getattr(self, '_count', None)
        if c is None:
            try:
                # Generate unique key based on SQL query
                sql = str(self.object_list.query)
                cache_key = hashlib.md5(sql.encode('utf-8')).hexdigest()
                now = time.time()
                cached_val, expiry = _counts_cache.get(cache_key, (None, 0))
                if cached_val is not None and now < expiry:
                    self._count = cached_val
                else:
                    self._count = self.object_list.count()
                    _counts_cache[cache_key] = (self._count, now + self.ttl)
            except Exception:
                # Fallback to default behavior if query cannot be stringified
                self._count = self.object_list.count()
            c = self._count
        return c

Paginator = FastPaginator
from .helpers import get_user_permissions

def apply_column_filters(queryset, request, prefix, mapping):
    for key, fields in mapping.items():
        param_name = f"{prefix}_col_{key}"
        val = request.GET.get(param_name, "").strip()
        if val:
            if isinstance(fields, list):
                q_obj = Q()
                for field in fields:
                    if field.endswith('__is_deleted') or field == 'is_deleted' or field.endswith('__is_active') or field == 'is_active' or field == 'is_superuser':
                        if val.lower() in ['yes', 'true', '1']:
                            q_obj |= Q(**{field: True})
                        elif val.lower() in ['no', 'false', '0']:
                            q_obj |= Q(**{field: False})
                    else:
                        q_obj |= Q(**{field + "__icontains": val})
                queryset = queryset.filter(q_obj)
            else:
                field = fields
                if field.endswith('__is_deleted') or field == 'is_deleted' or field.endswith('__is_active') or field == 'is_active' or field == 'is_superuser' or field == 'can_access' or field == 'can_add' or field == 'can_edit' or field == 'can_delete' or field == 'can_view':
                    if val.lower() in ['yes', 'true', '1']:
                        queryset = queryset.filter(**{field: True})
                    elif val.lower() in ['no', 'false', '0']:
                        queryset = queryset.filter(**{field: False})
                else:
                    if '__icontains' not in field and not field.endswith('__year') and not field.endswith('__month') and not field.endswith('__day'):
                        queryset = queryset.filter(**{field + "__icontains": val})
                    else:
                        queryset = queryset.filter(**{field: val})
    return queryset


def order_queryset(queryset, request, prefix, mapping, default_order='id'):
    sort_col = request.GET.get(f"{prefix}_sort")
    order = request.GET.get(f"{prefix}_order", "asc")
    
    if sort_col and sort_col in mapping:
        fields = mapping[sort_col]
        if not isinstance(fields, list):
            fields = [fields]
            
        ordering_fields = []
        for field in fields:
            if order == "desc":
                ordering_fields.append("-" + field)
            else:
                ordering_fields.append(field)
        
        secondary = default_order
        if secondary.startswith('-'):
            secondary = secondary[1:]
        if order == "desc":
            ordering_fields.append("-" + secondary)
        else:
            ordering_fields.append(secondary)
            
        return queryset.order_by(*ordering_fields)
        
    return queryset.order_by(default_order)


donor_mapping = {
    '2': 'id',
    '3': 'person_type__lookup_name',
    '4': 'first_name',
    '5': 'middle_name',
    '6': 'last_name',
    '7': 'gender',
    '8': 'date_of_birth',
    '9': 'contact_number',
    '10': 'email',
    '11': 'donor_box__donation_id',
    '12': 'id_type__lookup_name',
    '13': 'id_number',
    '14': 'occupation_name',
    '15': 'occupation_nature__lookup_name',
    '16': 'occupation_type__lookup_name',
    '17': 'gst_number',
    '18': 'address',
    '19': 'city',
    '20': 'state',
    '21': 'country',
    '22': 'postal_code',
    '23': 'native_place',
    '24': 'created_by__username',
    '25': 'created_at',
    '26': 'updated_by__username',
    '27': 'updated_at',
    '28': 'is_deleted',
    '29': 'deleted_by__username',
    '30': 'deleted_at',
}

donation_mapping = {
    '1': 'id',
    '2': 'receipt_id',
    '3': ['donor__first_name', 'donor__last_name'],
    '4': 'donor__city',
    '5': 'donation_amount_declared',
    '6': 'donation_amount_paid',
    '7': 'donation_date',
    '8': 'donation_category__lookup_name',
    '9': 'payment_method__lookup_name',
    '10': 'transaction_id',
    '11': 'payment_status__lookup_name',
    '12': 'check_no',
    '13': 'place_of_donation',
    '14': 'description',
    '15': 'name_of_bank',
    '16': 'branch',
    '17': 'created_by__username',
    '18': 'created_at',
    '19': 'updated_by__username',
    '20': 'updated_at',
    '21': 'is_deleted',
    '22': 'deleted_by__username',
    '23': 'deleted_at',
    '24': 'verified_by__username',
}

user_mapping = {
    '1': 'userrole__role__name',
    '2': 'id',
    '3': 'username',
    '4': 'first_name',
    '5': 'last_name',
    '6': 'email',
    '7': 'is_active',
    '8': 'is_superuser',
    '9': 'date_joined',
}

roles_mapping = {
    '1': 'id',
    '2': 'module__id',
    '3': 'module__module_name',
    '4': 'description',
    '5': 'name',
    '6': 'can_access',
    '7': 'can_add',
    '8': 'can_delete',
    '9': 'can_edit',
    '10': 'can_view',
    '11': 'created_by__username',
    '12': 'created_at',
    '13': 'updated_by__username',
    '14': 'updated_at',
}

lt_mapping = {
    '1': 'id',
    '2': 'type_name',
    '3': 'created_by__username',
    '4': 'created_at',
    '5': 'updated_by__username',
    '6': 'updated_at',
    '7': 'is_deleted',
    '8': 'deleted_by__username',
    '9': 'deleted_at',
}

lu_mapping = {
    '1': 'id',
    '2': 'lookup_name',
    '3': 'lookup_type__type_name',
    '4': 'created_by__username',
    '5': 'created_at',
    '6': 'updated_by__username',
    '7': 'updated_at',
    '8': 'is_deleted',
    '9': 'deleted_by__username',
    '10': 'deleted_at',
}

payments_mapping = {
    '1': 'id',
    '2': 'receipt_id',
    '3': ['owner__first_name', 'owner__last_name'],
    '4': 'donation_box__donation_id',
    '5': 'amount',
    '6': 'payment_mode__lookup_name',
    '7': ['opened_by__first_name', 'opened_by__last_name'],
    '8': ['received_by__first_name', 'received_by__last_name'],
    '9': 'i_witness',
    '10': 'name_of_bank',
    '11': 'branch',
    '12': 'transaction_id',
    '13': 'created_by__username',
    '14': 'created_at',
    '15': 'updated_by__username',
    '16': 'updated_at',
    '17': 'deleted_by__username',
    '18': 'is_deleted',
    '19': 'deleted_at',
}

box_mapping = {
    '1': 'donation_id',
    '3': 'key_id',
    '4': 'box_size',
    '5': 'status',
    '6': 'box_owner',
    '7': 'box_percentage',
    '8': 'created_by__username',
    '9': 'created_at',
    '10': 'updated_by__username',
    '11': 'updated_at',
    '12': 'is_deleted',
    '13': 'deleted_by__username',
    '14': 'deleted_at',
}

def get_welcome_context(request, donors=None, donations=None, roles_qs=None, users=None, lookup_types=None, lookups=None, donation_boxes=None, donation_payment=None, extra_context=None):
    user = request.user
    permissions = get_user_permissions(user)
    if user.is_superuser:
        class SuperPerm:
            can_add = True
            can_edit = True
            can_delete = True
            can_view = True
            can_access = True
        permissions = SuperPerm()

    if users is None:
        users = User.objects.all()
    users = users.select_related('userrole__role').order_by('id')

    if roles_qs is None:
        roles_qs = UserModuleAccess.objects.all()
    roles_qs = roles_qs.select_related('module', 'created_by', 'updated_by', 'deleted_by')

    if donations is None:
        donations = Donation.objects.all()
    donations = donations.select_related('donor', 'donation_category', 'donation_sub_category', 'payment_method', 'payment_status', 'created_by', 'updated_by', 'deleted_by', 'verified_by')

    if donors is None:
        donors = DonorVolunteer.objects.all()
    donors = donors.select_related("person_type", "donor_box", "id_type", "occupation_nature", "occupation_type", "created_by", "updated_by", "deleted_by")

    if lookup_types is None:
        lookup_types = LookupType.objects.all()
    lookup_types = lookup_types.select_related('created_by', 'updated_by', 'deleted_by').order_by("id")

    if lookups is None:
        lookups = Lookup.objects.all()
    lookups = lookups.select_related("lookup_type", "created_by", "updated_by", "deleted_by").order_by("id")

    if donation_boxes is None:
        donation_boxes = DonationBox.objects.all()
    donation_boxes = donation_boxes.select_related('uploaded_by', 'created_by', 'deleted_by')

    if donation_payment is None:
        donation_payment = DonationPaymentBox.objects.all()
    donation_payment = donation_payment.select_related("owner", "donation_box", "opened_by", "received_by", "payment_mode", "verified_by", "created_by", "updated_by", "deleted_by")

    donation_owners = DonationOwner.objects.select_related('owner_name', 'donation_box').all()
    roles_qss = UserModuleAccess.objects.values_list("name", flat=True)
    clean_roles = sorted(set(roles_qss))
    role_names = roles_qs.values_list("name", flat=True).order_by().distinct()

    users = apply_column_filters(users, request, 'user', user_mapping)
    roles_qs = apply_column_filters(roles_qs, request, 'roles', roles_mapping)
    donations = apply_column_filters(donations, request, 'donation', donation_mapping)
    donors = apply_column_filters(donors, request, 'donor', donor_mapping)
    lookup_types = apply_column_filters(lookup_types, request, 'lt', lt_mapping)
    lookups = apply_column_filters(lookups, request, 'lu', lu_mapping)
    donation_boxes = apply_column_filters(donation_boxes, request, 'box', box_mapping)
    donation_payment = apply_column_filters(donation_payment, request, 'payments', payments_mapping)

    # Pagination
    donors = order_queryset(donors, request, 'donor', donor_mapping, 'id')
    donations = order_queryset(donations, request, 'donation', donation_mapping, 'id')
    users = order_queryset(users, request, 'user', user_mapping, 'id')
    roles_qs = order_queryset(roles_qs, request, 'roles', roles_mapping, 'id')
    lookup_types = order_queryset(lookup_types, request, 'lt', lt_mapping, 'id')
    lookups = order_queryset(lookups, request, 'lu', lu_mapping, 'id')
    donation_payment = order_queryset(donation_payment, request, 'payments', payments_mapping, 'id')
    donation_boxes = order_queryset(donation_boxes, request, 'box', box_mapping, 'id')

    page_obj = Paginator(donors, 10).get_page(request.GET.get('donor_page'))
    donation_page_obj = Paginator(donations, 10).get_page(request.GET.get('donation_page'))
    user_page_obj = Paginator(users, 10).get_page(request.GET.get('user_page'))
    roles_page_obj = Paginator(roles_qs, 10).get_page(request.GET.get('roles_page'))
    lookup_page_obj = Paginator(lookup_types, 5).get_page(request.GET.get("lt_page"))
    lookup_table_obj = Paginator(lookups, 5).get_page(request.GET.get("lu_page"))
    payments_page_obj = Paginator(donation_payment, 5).get_page(request.GET.get("payments_page"))
    box_page_obj = Paginator(donation_boxes, 5).get_page(request.GET.get("box_page"))

    icon_map = {
        "User": "bi bi-person",
        "Roles": "bi bi-shield-lock",
        "Donation Module": "bi bi-cash-coin",
        "Donation Box Module": "bi bi-box",
        "Donor/Volunteer Management System": "bi bi-heart",
        "Event Management System": "bi bi-calendar-event",
        "Timesheet System": "bi bi-clock",
        "Leave Management System": "bi bi-calendar-x",
        "Visitor Management System": "bi bi-person-badge",
        "Vendor Management System": "bi bi-truck",
        "Request Management System": "bi bi-clipboard-check",
        "Inventory Management System": "bi bi-boxes",
        "Asset Management System": "bi bi-pc-display",
        "Fleet Management System": "bi bi-truck",
        "Financial Asset Module": "bi bi-graph-up",
        "Expense Module": "bi bi-receipt",
        "Medical Module": "fa-solid fa-syringe",
        "Rehabilitation Module": "bi bi-hand-thumbs-up",
        "Adoption Module": "bi bi-people-fill",
        "Trees Module": "bi bi-tree",
        "Seeds Module": "bi bi-flower1",
    }

    context = {
        'user': user,
        'username': user.username if user.is_authenticated else "",
        'first_name': user.first_name if user.is_authenticated else "",
        'donation_payment': donation_payment,
        'permissions': permissions,  
        'donation_owners': donation_owners,
        'roles_qss': roles_qss,
        'role_names': role_names,
        'clean_roles': clean_roles,
        'page_obj': page_obj,
        'donations': donations,
        'today': now().date(),
        'donation_page_obj': donation_page_obj,
        'user_page_obj': user_page_obj,
        'roles_page_obj': roles_page_obj,
        'lookup_types': lookup_types,
        'lookups': lookups,
        'lookup_page_obj': lookup_page_obj,
        'lookup_table_obj': lookup_table_obj,
        'showall': users.exclude(is_superuser=True),
        'donation_boxes': donation_boxes,
        'payments_page_obj': payments_page_obj,
        'box_page_obj': box_page_obj,
        'icon_map': icon_map,
    }

    # Pass column filter parameters back to the context
    for prefix in ['lt', 'lu', 'user', 'roles', 'payments', 'donor', 'box', 'donation']:
        for col_idx in range(1, 35):
            param_name = f"{prefix}_col_{col_idx}"
            val = request.GET.get(param_name, "")
            if val:
                context[param_name] = val

    if user.is_authenticated and user.is_superuser:
        all_modules = Module.objects.all().values_list('module_name', flat=True)
        context['allowed_modules'] = list(all_modules)
    elif user.is_authenticated:
        user_role = UserRole.objects.filter(user=user).select_related('role').first()
        if user_role and user_role.role:
            allowed_modules = (
                UserModuleAccess.objects.filter(
                    name=user_role.role.name,
                    can_access=True
                ).select_related('module')
                .values_list('module__module_name', flat=True)
            )
            context['allowed_modules'] = list(allowed_modules)
        else:
            context['allowed_modules'] = []
            messages.warning(request, "⚠️ No role assigned. Contact admin.")
    else:
        context['allowed_modules'] = []

    if extra_context:
        context.update(extra_context)

    return context

@login_required
def welcome_view(request):
    user = request.user
    permissions = get_user_permissions(user)
    if user.is_superuser:
        class SuperPerm:
            can_add = True
            can_edit = True
            can_delete = True
            can_view = True
            can_access = True
        permissions = SuperPerm()

    if request.method == "POST" and "save_user_role" in request.POST:
        user_id = request.POST.get("user_id")
        role_name = request.POST.get("role")

        if not user_id or not role_name:
            messages.error(request, "❌ Please select both user and role.")
            return redirect("welcome")
        selected_user = get_object_or_404(User, id=user_id)
        previous_super_state = selected_user.is_superuser

        selected_role = UserModuleAccess.objects.filter(name=role_name).first()
        if not selected_role:
            messages.error(request, "❌ Invalid role selected.")
            return redirect("welcome")

        user_role, created = UserRole.objects.get_or_create(user=selected_user)
        user_role.role = selected_role
        user_role.save()

        if selected_user.is_superuser != previous_super_state:
            selected_user.is_superuser = previous_super_state
            selected_user.save(update_fields=["is_superuser"])

        messages.success(
            request,
            f"✅ Role '{role_name}' has been assigned to {selected_user.username}."
        )
        return redirect("welcome")

    context = get_welcome_context(request)
    return render(request, "welcome.html", context)

def logout_view(req):
    logout(req)
    return redirect("home")

def send_otp(request):
    if request.method == "POST":
        phone = request.POST.get("phone")
        otp = str(random.randint(100000, 999999))
        otp_storage[phone] = otp
        print(f"OTP for {phone}: {otp}")  # For testing only
        return redirect(f"/verify-otp/?phone={phone}")
    return redirect('signin')  # fallback if GET

from twilio.rest import Client
TWILIO_ACCOUNT_SID = 'AC730c5a6779806941ef6ef4215f92629a'
TWILIO_AUTH_TOKEN = '8ab4ce8083246cb7fc38dccacc5a521b'
TWILIO_PHONE = '+917208542366'  

def send_otp(request):
    if request.method == "POST":
        phone = request.POST.get("phone")
        otp = str(random.randint(100000, 999999))
        otp_storage[phone] = otp

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=f"Your OTP is {otp}",
            from_=TWILIO_PHONE,
            to=f"+91{phone}" 
        )

        return redirect(f"/verify-otp/?phone={phone}")
    return redirect('signin')

# ------------Globle All Search-------------------

@login_required
def search_lookup_type(request):
    lookup_query = request.GET.get('lookup_query', '').strip()
    active_tab = request.GET.get('active_tab', 'mdm')
    lookup_types = LookupType.objects.select_related('created_by', 'updated_by', 'deleted_by').all().order_by('id')
    if lookup_query:
        filters = (
            Q(type_name__icontains=lookup_query) |
            Q(created_by__username__icontains=lookup_query) |
            Q(updated_by__username__icontains=lookup_query) |
            Q(created_at__icontains=lookup_query) |
            Q(updated_at__icontains=lookup_query) |
            Q(deleted_at__icontains=lookup_query)
        )

        # Boolean search ("true/false/yes/no")
        if lookup_query.lower() in ["true", "false", "yes", "no"]:
            filters |= Q(is_deleted=(lookup_query.lower() in ["true", "yes"]))

        # Numeric → search by ID
        if lookup_query.isdigit():
            filters |= Q(id=int(lookup_query))
        lookup_types = lookup_types.filter(filters)

    # 🟢 DOWNLOAD SEARCHED DATA
    if request.GET.get('download') == '1':
        filename = f"lookup_types_{lookup_query or 'all'}.csv"
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(['ID', 'Type Name', 'Created By', 'Created At','Updated By','Updated At','Deleted At','Is Deleted'])

        for lookup in lookup_types:
            writer.writerow([lookup.id, lookup.type_name, lookup.created_by, lookup.created_at,lookup.updated_by,lookup.updated_at,lookup.deleted_at,lookup.is_deleted])

        return response

    context = get_welcome_context(request, lookup_types=lookup_types, extra_context={
        "lookup_query": lookup_query,
        "active_tab": active_tab,
    })
    return render(request, "welcome.html", context)

@login_required
def search_lookup_table(request):
    sub_lookup_query = request.GET.get('sub_lookup_query', '').strip()
    active_tab = request.GET.get('active_tab', 'mdm')
    lookups = Lookup.objects.select_related("lookup_type", "created_by", "updated_by", "deleted_by").all().order_by('id')
    if sub_lookup_query:
        month_map = {
            "jan": 1, "january": 1,
            "feb": 2, "february": 2,
            "mar": 3, "march": 3,
            "apr": 4, "april": 4,
            "may": 5,
            "jun": 6, "june": 6,
            "jul": 7, "july": 7,
            "aug": 8, "august": 8,
            "sep": 9, "sept": 9, "september": 9,
            "oct": 10, "october": 10,
            "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }

        filters = (
            Q(lookup_name__icontains=sub_lookup_query) |
            Q(lookup_type__type_name__icontains=sub_lookup_query) |
            Q(created_by__username__icontains=sub_lookup_query) |
            Q(updated_by__username__icontains=sub_lookup_query) |
            Q(created_at__icontains=sub_lookup_query) |
            Q(updated_at__icontains=sub_lookup_query) |
            Q(deleted_at__icontains=sub_lookup_query)
        )

        # Numeric → ID support
        if sub_lookup_query.isdigit():
            filters |= Q(id=int(sub_lookup_query))

        # Boolean search
        if sub_lookup_query.lower() in ["true", "false", "yes", "no"]:
            filters |= Q(is_deleted=(sub_lookup_query.lower() in ["true", "yes"]))

        # Month search (Dec, January, etc.)
        q_lower = sub_lookup_query.lower()
        if q_lower in month_map:
            month = month_map[q_lower]
            filters |= (
                Q(created_at__month=month) |
                Q(updated_at__month=month) |
                Q(deleted_at__month=month)
            )

        lookups = lookups.filter(filters)

    # 🟢 DOWNLOAD CSV (same style & naming like search_lookup_type)
    if request.GET.get('download') == '1':
        filename = f"lookup_table_{sub_lookup_query or 'all'}.csv"
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(["ID", "Lookup Name", "Lookup Type", "Created By", "Created At", "Updated By", "Updated At", "Deleted At", "Is Deleted"])

        for l in lookups:
            writer.writerow([
                l.id,
                l.lookup_name,
                l.lookup_type.type_name if l.lookup_type else "",
                l.created_by.username if l.created_by else "",
                l.created_at,
                l.updated_by.username if l.updated_by else "",
                l.updated_at,
                l.deleted_at,
                l.is_deleted,
            ])

        return response
    context = get_welcome_context(request, lookups=lookups, extra_context={
        "sub_lookup_query": sub_lookup_query,
        "active_tab": active_tab,
    })
    return render(request, "welcome.html", context)

from django.contrib.auth.models import User

@login_required
def search_users(request):
    query = request.GET.get("user_query", "")
    active_tab = request.GET.get("active_tab", "user")
    download = request.GET.get("download")
    users = User.objects.all().order_by("id")
    if query:
        users = users.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )

    # ✅ If download clicked → return CSV, DO NOT REDIRECT
    if download == "1":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="users.csv"'

        writer = csv.writer(response)
        writer.writerow(["ID", "Username", "First Name", "Last Name", "Email", "Active", "Superuser", "Date Joined"])

        for u in users:
            writer.writerow([
                u.id, u.username, u.first_name, u.last_name, u.email,
                u.is_active, u.is_superuser, u.date_joined
            ])

        return response  # ⬅️ No redirect, download starts directly

    context = get_welcome_context(request, users=users, extra_context={
        "user_query": query,
        "active_tab": active_tab,
    })
    return render(request, "welcome.html", context)

@login_required
def search_roles(request):
    query1 = request.GET.get('query1', '').strip()
    active_tab = "roles"
    roles = UserModuleAccess.objects.all().order_by('id')
    if query1:
        month_map = {
            "jan": 1, "january": 1,
            "feb": 2, "february": 2,
            "mar": 3, "march": 3,
            "apr": 4, "april": 4,
            "may": 5,
            "jun": 6, "june": 6,
            "jul": 7, "july": 7,
            "aug": 8, "august": 8,
            "sep": 9, "sept": 9, "september": 9,
            "oct": 10, "october": 10,
            "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }

        filters = (
            Q(name__icontains=query1) |
            Q(description__icontains=query1) |
            Q(module__module_name__icontains=query1) |
            Q(created_by__username__icontains=query1) |
            Q(updated_by__username__icontains=query1) |
            # Q(created_at__icontains=query1) |
            # Q(updated_at__icontains=query1) |
            Q(deleted_at__icontains=query1)
        )
        if query1.isdigit():
            filters |= (
                Q(id=int(query1)) |
                Q(module_id=int(query1))
            )
        truthy = ["true", "yes", "enable", "enabled"]
        falsy = ["false", "no", "disable", "disabled"]
        qlow = query1.lower()

        if qlow in truthy or qlow in falsy:
            val = qlow in truthy
            filters |= (
                Q(can_access=val) |
                Q(can_add=val) |
                Q(can_edit=val) |
                Q(can_delete=val) |
                Q(can_view=val) |
                Q(is_deleted=val)
            )
        if qlow in month_map:
            month_num = month_map[qlow]
            filters |= (
                Q(created_at__month=month_num) |
                Q(updated_at__month=month_num) |
                Q(deleted_at__month=month_num)
            )
        roles = roles.filter(filters)
    if request.GET.get('download') == '1':
        filename = f"roles_{query1 or 'all'}.csv"
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        writer.writerow(['Role', 'Description', 'Can Access', 'Can Add', 'Can Edit', 'Can Delete', 'Can View', 'Created By', 'Created At', 'Updated By', 'Updated At', 'Deleted At', 'Is Deleted'])

        for role in roles:
            writer.writerow([
                role.name,
                role.description,
                role.can_access,
                role.can_add,
                role.can_edit,
                role.can_delete,
                role.can_view,
                role.created_by,
                role.created_at,
                role.updated_by,
                role.updated_at,
                role.deleted_at,
                role.is_deleted,
            ])

        return response
    context = get_welcome_context(request, roles_qs=roles, extra_context={
        "query1": query1,
        "active_tab": active_tab,
    })
    return render(request, "welcome.html", context)

def manage_user_roles(request):
    users = User.objects.all()
    roles = UserModuleAccess.objects.select_related('module').all()
    user_roles = {ur.user_id: ur for ur in UserRole.objects.select_related('user', 'role__module').all()}

    if request.method == "POST":
        user_id = request.POST.get('user_id')
        role_id = request.POST.get('role_id')

        if user_id:
            user = User.objects.get(id=user_id)

            if role_id:
                access_role = UserModuleAccess.objects.get(id=role_id)
                user_role, created = UserRole.objects.get_or_create(user=user)
                user_role.role = access_role
                user_role.save()
                messages.success(request, f"Role '{access_role.role.name}' assigned to {user.username}.")
            else:
                UserRole.objects.filter(user=user).delete()
                messages.warning(request, f"Role removed for {user.username}.")

        return redirect('manage_user_roles')

    return render(request, 'manage_user_roles.html', {
        'users': users,
        'roles': roles,
        'user_roles': user_roles,
    })

def assign_role(request):
    users = User.objects.all()

    # Fetch UNIQUE role names only
    roles = UserModuleAccess.objects.values_list('name', flat=True).order_by().distinct()

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        selected_role_name = request.POST.get("role")  # from <select name="role">

        print("🟡 POST DATA:", request.POST)
        print(f"➡️ user_id={user_id}, role={selected_role_name}")

        if user_id and selected_role_name:
            user = User.objects.get(id=user_id)

            # Get the role object based on name
            role = UserModuleAccess.objects.filter(name=selected_role_name).first()

            if role:
                user_role, created = UserRole.objects.get_or_create(user=user)
                user_role.role = role
                user_role.save()

                print(f"✅ Saved: {user.username} → {role.name}")
            else:
                print("❌ Role not found!")

        else:
            print("❌ Missing user_id or role value!")

        return redirect('welcome')

    return render(request, "welcome.html", {"users": users, "roles": roles})

from datetime import datetime, date

def search_donor_volunteer(request):
    donorvolunteer = DonorVolunteer.objects.select_related(
        "person_type", "id_type", "donor_box",
        "created_by", "updated_by", "occupation_nature", "occupation_type",
        "department", "position", "designation", "deleted_by"
    ).all()

    query2 = request.GET.get('q')
    if query2:
        query2 = query2.strip()
        if query2 != "":
            month_map = {
                "jan": 1, "january": 1,
                "feb": 2, "february": 2,
                "mar": 3, "march": 3,
                "apr": 4, "april": 4,
                "may": 5,
                "jun": 6, "june": 6,
                "jul": 7, "july": 7,
                "aug": 8, "august": 8,
                "sep": 9, "sept": 9, "september": 9,
                "oct": 10, "october": 10,
                "nov": 11, "november": 11,
                "dec": 12, "december": 12,
            }

            qlow = query2.lower()
            filters = (
                Q(person_type__lookup_name__icontains=query2) |
                Q(first_name__icontains=query2) |
                Q(middle_name__icontains=query2) |
                Q(last_name__icontains=query2) |
                Q(gender__icontains=query2) |
                Q(blood_group__icontains=query2) |
                Q(email__icontains=query2) |
                Q(contact_number__icontains=query2) |
                Q(whatsapp_number__icontains=query2) |
                Q(donor_box__donation_id__icontains=query2) |
                Q(donor_box__key_id__icontains=query2) |
                Q(address__icontains=query2) |
                Q(city__icontains=query2) |
                Q(state__icontains=query2) |
                Q(country__icontains=query2) |
                Q(postal_code__icontains=query2) |
                Q(native_place__icontains=query2) |
                # Q(native_postal_code__icontains=query2) |
                Q(id_type__lookup_name__icontains=query2) |
                Q(id_number__icontains=query2) |
                Q(pan_number__icontains=query2) |
                Q(created_by__username__icontains=query2) |
                Q(updated_by__username__icontains=query2)
            )
            if query2.isdigit():
                try:
                    num = int(query2)
                    filters |= (
                        Q(id=num) |
                        Q(age=num)
                    )
                except ValueError:
                    pass
            truthy = {"true", "yes", "active", "1"}
            falsy = {"false", "no", "inactive", "0"}
            if qlow in truthy or qlow in falsy:
                if qlow in truthy:
                    filters |= Q(is_deleted=False)
                else:
                    filters |= Q(is_deleted=True)
            if qlow in month_map:
                month_num = month_map[qlow]
                filters |= (
                    Q(date_of_birth__month=month_num) |
                    Q(created_at__month=month_num) |
                    Q(updated_at__month=month_num) |
                    Q(deleted_at__month=month_num)
                )
            try:
                import re

                date_parsed = False

                # 1. Date formats with separators (e.g. "15-07-2026", "15.07.26", "15/07/2026", "22 jun 2026")
                # Normalize separators: dots, slashes, dashes, multiple spaces to a single space
                clean_query = re.sub(r'[-./\s]+', ' ', query2).strip()
                for fmt in ("%d %m %Y", "%d %m %y", "%Y %m %d", "%d %b %Y", "%d %B %Y", "%d %b %y", "%d %B %y"):
                    try:
                        parsed = datetime.strptime(clean_query, fmt).date()
                        filters |= (
                            Q(date_of_birth=parsed) |
                            Q(created_at__date=parsed) |
                            Q(updated_at__date=parsed) |
                            Q(deleted_at__date=parsed)
                        )
                        date_parsed = True
                        break
                    except ValueError:
                        pass

                # If it's a full date, we do not run other partial/year matches to prevent polluting results.
                if not date_parsed:
                    # 2. 4-digit year search (e.g. "2026")
                    if len(query2) == 4 and query2.isdigit():
                        y = int(query2)
                        filters |= (
                            Q(date_of_birth__year=y) |
                            Q(created_at__year=y) |
                            Q(updated_at__year=y) |
                            Q(deleted_at__year=y)
                        )

                    # 3. Partial dates: DD-MM (e.g. "15-07", "15/07", "15.07")
                    match_dd_mm = re.match(r'^(\d{1,2})[-/.](\d{1,2})$', query2)
                    if match_dd_mm:
                        d = int(match_dd_mm.group(1))
                        m = int(match_dd_mm.group(2))
                        if 1 <= d <= 31 and 1 <= m <= 12:
                            filters |= (
                                Q(date_of_birth__day=d, date_of_birth__month=m) |
                                Q(created_at__day=d, created_at__month=m) |
                                Q(updated_at__day=d, updated_at__month=m) |
                                Q(deleted_at__day=d, deleted_at__month=m)
                            )

                    # 4. Partial dates: MM-YYYY (e.g. "07-2026", "07/2026", "07.2026")
                    match_mm_yyyy = re.match(r'^(\d{1,2})[-/.](\d{4})$', query2)
                    if match_mm_yyyy:
                        m = int(match_mm_yyyy.group(1))
                        y = int(match_mm_yyyy.group(2))
                        if 1 <= m <= 12:
                            filters |= (
                                Q(date_of_birth__month=m, date_of_birth__year=y) |
                                Q(created_at__month=m, created_at__year=y) |
                                Q(updated_at__month=m, updated_at__year=y) |
                                Q(deleted_at__month=m, deleted_at__year=y)
                            )

                    # 5. Natural month names and combinations (e.g. "July 2026", "15 July")
                    for month_name, month_num in month_map.items():
                        if month_name in qlow:
                            # Extract year
                            year_match = re.search(r'\b(\d{4})\b', qlow)
                            y_val = None
                            if year_match:
                                y_val = int(year_match.group(1))
                                filters |= (
                                    Q(date_of_birth__month=month_num, date_of_birth__year=y_val) |
                                    Q(created_at__month=month_num, created_at__year=y_val) |
                                    Q(updated_at__month=month_num, updated_at__year=y_val) |
                                    Q(deleted_at__month=month_num, deleted_at__year=y_val)
                                )
                            # Extract day (excluding the year match digits)
                            text_to_search_day = qlow
                            if year_match:
                                text_to_search_day = qlow.replace(year_match.group(1), '')
                            day_match = re.search(r'\b(\d{1,2})\b', text_to_search_day)
                            if day_match:
                                d_val = int(day_match.group(1))
                                if 1 <= d_val <= 31:
                                    filters |= (
                                        Q(date_of_birth__day=d_val, date_of_birth__month=month_num) |
                                        Q(created_at__day=d_val, created_at__month=month_num) |
                                        Q(updated_at__day=d_val, updated_at__month=month_num) |
                                        Q(deleted_at__day=d_val, deleted_at__month=month_num)
                                    )
            except Exception:
                pass
            donorvolunteer = donorvolunteer.filter(filters).distinct().order_by("id")

    # ---- DOWNLOAD CSV ----
    if request.GET.get('download') == '1':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="donor_volunteer.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Person Type', 'First Name', 'Middle Name', 'Last Name', 
            'Gender', 'DOB', 'Email', 'Contact Number','Blood Group','WhatsApp Number','Donor Box', 'Address', 'City', 'State', 'Country','Postal Code', 'Native Place', 'Native Postal Code',
             'occupation_type','occupation_nature','department','position','designation','business_type', 'ID Type', 'ID Number', 
            'PAN Number', 'Age', 'Created By', 'Created At', 'Updated By', 'Updated At', 'Deleted At', 'Is Deleted',   
        
        ])

        for dv in donorvolunteer:
            writer.writerow([
                dv.person_type.lookup_name if dv.person_type else '',
                dv.first_name,
                dv.middle_name,
                dv.last_name,
                dv.gender,
                dv.date_of_birth,
                dv.email,
                dv.contact_number,
                dv.blood_group,
                dv.whatsapp_number,
                dv.donor_box.donation_id if dv.donor_box else '',
                dv.address,
                dv.city,
                dv.state,
                dv.country,
                dv.postal_code,
                dv.native_place,
                dv.occupation_type,
                dv.occupation_nature,
                dv.department,
                dv.position,
                dv.designation,
                # dv.business_type,
                # dv.id_type.lookup_name if dv.id_type else '',
                dv.id_number,
                dv.pan_number,
                dv.age,
                dv.created_by.username if dv.created_by else '',
                dv.created_at,
                dv.updated_by.username if dv.updated_by else '',
                dv.updated_at,
                dv.deleted_at,
                dv.is_deleted,

            ])

        return response
    context = get_welcome_context(request, donors=donorvolunteer, extra_context={
        "query": query2 if query2 else "",
        "query2": query2 if query2 else "",
    })
    return render(request, "welcome.html", context)

from django.db.models import Value
from django.db.models.functions import Concat

def search_donation(request):
    donations = Donation.objects.select_related(
        'donor', 'donation_category', 'donation_sub_category',
        'payment_method', 'payment_status', 'created_by', 'updated_by',
        'deleted_by', 'verified_by'
    ).all()
    query3 = request.GET.get('q', '').strip()

    if query3:
        donations = donations.annotate(
            full_name=Concat(
                'donor__first_name',
                Value(' '),
                'donor__last_name'
            )
        ).filter(
            Q(full_name__icontains=query3) |
            Q(donation_date__icontains=query3) |
            Q(donation_amount_declared__icontains=query3) |
            Q(donation_amount_paid__icontains=query3) |
            Q(transaction_id__icontains=query3) |
            Q(payment_status__lookup_name__icontains=query3) |
            Q(receipt_id__icontains=query3) |
            Q(donation_category__lookup_name__icontains=query3) |
            Q(payment_method__lookup_name__icontains=query3)
        ).distinct()

    # ---- DOWNLOAD CSV ----
    if request.GET.get('download') == '1':
        filename = f"donations_{query3 if query3 else 'all'}.csv"
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow([
            'ID',
            'Receipt No.',
            'Donor Name',
            'Display Name',
            'Donation Date',
            'Amount Declared',
            'Amount Paid',
            'Category',
            'Payment Method',
            'Bank Name',
            'Branch',
            'Transaction ID',
            'Status',
            'created_by',
            'updated_by',
            'created_at',
            'updated_at',
            'deleted_at',
            'is_deleted',
            'Verified By',
            'Verified at',

        ])

        for d in donations:
            donor_name = f"{d.donor.first_name} {d.donor.last_name}" if d.donor else ""
            writer.writerow([
                d.id,
                d.receipt_id,
                donor_name,
                d.display_name,
                d.donation_date,
                d.donation_amount_declared,
                d.donation_amount_paid,
                d.donation_category.lookup_name if d.donation_category else "",
                d.payment_method.lookup_name if d.payment_method else "",
                d.name_of_bank,
                d.branch,
                d.transaction_id,
                d.payment_status.lookup_name if d.payment_status else "",
                d.created_by.username if d.created_by else '',
                d.updated_by.username if d.updated_by else '',
                d.created_at,
                d.updated_at,
                d.deleted_at,
                d.is_deleted,
                d.verified_by,
                d.verified_at,    ])
        return response

    context = get_welcome_context(request, donations=donations, extra_context={
        'query3': query3,
    })
    return render(request, 'welcome.html', context)

@login_required
def search_donation_payment(request):
    payments_query = request.GET.get("payments_query", "").strip()
    payments = DonationPaymentBox.objects.select_related(
        'owner', 'donation_box', 'opened_by', 'received_by', 'payment_mode',
        'verified_by', 'created_by', 'updated_by', 'deleted_by'
    ).filter(is_deleted=False)
    if payments_query:
        q = payments_query.lower()
        month_map = {
            "jan": 1, "january": 1,
            "feb": 2, "february": 2,
            "mar": 3, "march": 3,
            "apr": 4, "april": 4,
            "may": 5,
            "jun": 6, "june": 6,
            "jul": 7, "july": 7,
            "aug": 8, "august": 8,
            "sep": 9, "sept": 9, "september": 9,
            "oct": 10, "october": 10,
            "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }

        filters = (
            Q(donation_box__donation_id__icontains=payments_query) |
            Q(donation_box__key_id__icontains=payments_query) |
            Q(donation_box__box_size__icontains=payments_query) |
            Q(donation_box__status__icontains=payments_query) |
            Q(opened_by__first_name__icontains=payments_query) |
            Q(opened_by__last_name__icontains=payments_query) |
            Q(opened_by__contact_number__icontains=payments_query) |
            Q(received_by__first_name__icontains=payments_query) |
            Q(received_by__last_name__icontains=payments_query) |
            Q(received_by__contact_number__icontains=payments_query) |
            Q(address__icontains=payments_query) |
            Q(i_witness__icontains=payments_query) |
            Q(owner__first_name__icontains=payments_query) |
            Q(owner__last_name__icontains=payments_query) |
            Q(created_by__username__icontains=payments_query) |
            Q(updated_by__username__icontains=payments_query)
        )
        if payments_query.replace('.', '', 1).isdigit():
            try:
                from decimal import Decimal
                amt = Decimal(payments_query)
                filters |= (
                    Q(amount=amt) |
                    Q(id=int(float(payments_query)))
                )
            except Exception:
                try:
                    filters |= Q(id=int(float(payments_query)))
                except Exception:
                    pass
        active_values = {"true", "yes", "active", "1"}
        inactive_values = {"false", "no", "inactive", "0"}

        if q in active_values:
            filters |= Q(is_deleted=False)
        elif q in inactive_values:
            filters |= Q(is_deleted=True)
        if len(payments_query) == 4 and payments_query.isdigit():
            y = int(payments_query)
            filters |= (
                Q(date_time__year=y) |
                Q(created_at__year=y) |
                Q(updated_at__year=y) |
                Q(deleted_at__year=y)
            )
        if q in month_map:
            m = month_map[q]
            filters |= (
                Q(date_time__month=m) |
                Q(created_at__month=m) |
                Q(updated_at__month=m) |
                Q(deleted_at__month=m)
            )
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(payments_query, fmt).date()
                filters |= (
                    Q(date_time__date=parsed) |
                    Q(created_at__date=parsed) |
                    Q(updated_at__date=parsed) |
                    Q(deleted_at__date=parsed)
                )
                break
            except:
                pass

        payments = payments.filter(filters).distinct().order_by("id")
    if request.GET.get("download") == "1":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="donation_payments.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "Donation ID",
            "Owner",
            "Opened By",
            "Amount",
            "Payment Mode",
            "Address",
            "Witness",
            "Bank Name",
            "Branch",
            "Created By",
            "Created At",
            "Updated By",
            "Updated At",
            "Deleted At",
            "Is Deleted",
            "Verified By",
            "Verified On", ])

        for p in payments:
            writer.writerow([
                p.donation_box.donation_id if p.donation_box else "",
                f"{p.owner.first_name} {p.owner.last_name}" if p.owner else "",
                p.opened_by,
                p.amount,
                p.payment_mode.lookup_name if p.payment_mode else "",
                p.address,
                p.i_witness,
                p.name_of_bank,
                p.branch,
                p.created_by.username if p.created_by else "",
                p.created_at,
                p.updated_by.username if p.updated_by else "",
                p.updated_at,
                p.deleted_at,
                p.is_deleted,
                p.verified_by,
                p.verified_at,
            ])
        return response

    context = get_welcome_context(request, donation_payment=payments, extra_context={
        "payments_query": payments_query,
    })
    return render(request, "welcome.html", context)

@login_required
def search_donation_box(request):

    box_query = request.GET.get("box_query", "").strip()
    boxes = DonationBox.objects.select_related(
        'uploaded_by', 'created_by', 'deleted_by'
    ).filter(is_deleted=False).order_by("id")
    if box_query:
        qlow = box_query.lower()
        month_map = {
            "jan": 1, "january": 1,
            "feb": 2, "february": 2,
            "mar": 3, "march": 3,
            "apr": 4, "april": 4,
            "may": 5,
            "jun": 6, "june": 6,
            "jul": 7, "july": 7,
            "aug": 8, "august": 8,
            "sep": 9, "sept": 9, "september": 9,
            "oct": 10, "october": 10,
            "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }
        filters = (
            Q(donation_id__icontains=box_query) |
            Q(key_id__icontains=box_query) |
            Q(box_size__icontains=box_query) |
            Q(status__icontains=box_query) |
            Q(uploaded_by__username__icontains=box_query) |
            Q(created_by__username__icontains=box_query)
        )
        if box_query.isdigit():
            filters |= Q(id=int(box_query))
        truthy = {"true", "yes", "active", "1"}
        falsy = {"false", "no", "inactive", "0"}
        if qlow in truthy:
            filters |= Q(is_deleted=False)
        elif qlow in falsy:
            filters |= Q(is_deleted=True)
        if len(box_query) == 4 and box_query.isdigit():
            y = int(box_query)
            filters |= (
                Q(created_at__year=y) |
                Q(updated_at__year=y) |
                Q(deleted_at__year=y)
            )
        if qlow in month_map:
            m = month_map[qlow]
            filters |= (
                Q(created_at__month=m) |
                Q(updated_at__month=m) |
                Q(deleted_at__month=m)
            )
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(box_query, fmt).date()
                filters |= (
                    Q(created_at__date=parsed) |
                    Q(updated_at__date=parsed) |
                    Q(deleted_at__date=parsed)
                )
                break
            except:
                pass

        boxes = boxes.filter(filters).distinct().order_by("id")
    # ---------------------------------------
    # 📥 CSV DOWNLOAD
    # ---------------------------------------
    if request.GET.get("download") == "1":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="donation_boxes.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "ID",
            "Donation ID",
            # "Location",
            "Key ID",
            "Box Size",
               "Status",
             "Created At",
            "Created By",
            "Uploaded By",   
            "Updated At",
            "Deleted At",
            "Is Deleted",

        ])

        for b in boxes:
            writer.writerow([
                b.id,
                b.donation_id,
                # b.location,
                b.key_id or "",
                b.box_size,
                 b.status,
                b.created_at,
                b.created_by.username if b.created_by else "",
                b.uploaded_by.username if b.uploaded_by else "",
                b.updated_at,
                b.deleted_at,
                b.is_deleted,
            ])
        return response

    context = get_welcome_context(request, donation_boxes=boxes, extra_context={
        "box_query": box_query,
    })
    return render(request, "welcome.html", context)

#----------------Globle End Search--------------
from django.core.files.storage import default_storage
from .models import DonorVolunteer, DonationBox, Lookup

def add_donor_volunteer(request):

    person_type_options = Lookup.objects.filter(lookup_type__type_name__iexact='Person Type')
    id_type_options = Lookup.objects.filter(lookup_type__type_name__iexact='ID Type')

    occupation_types = Lookup.objects.filter(lookup_type__type_name__iexact="Occupation Type")
    occupation_natures = Lookup.objects.filter(lookup_type__type_name__iexact="Occupation Nature")

    departments = Lookup.objects.filter(lookup_type__type_name__iexact="Department")
    positions = Lookup.objects.filter(lookup_type__type_name__iexact="Position")
    designations = Lookup.objects.filter(lookup_type__type_name__iexact="Designation")

    org_types = Lookup.objects.filter(lookup_type__type_name__iexact="Organization Type")

    donation_boxes = DonationBox.objects.filter(is_deleted=False)
    all_donors = DonorVolunteer.objects.none()

    blood_groups = [
        ("A+", "A+"), ("A-", "A-"),
        ("B+", "B+"), ("B-", "B-"),
        ("AB+", "AB+"), ("AB-", "AB-"),
        ("O+", "O+"), ("O-", "O-"),
    ]

    def get_lookup(field):
        value = request.POST.get(field)
        return Lookup.objects.get(id=value) if value and value.isdigit() else None

    def get_donor(field):
        value = request.POST.get(field)
        return DonorVolunteer.objects.get(id=value) if value and value.isdigit() else None

    def get_box(field):
        value = request.POST.get(field)
        return DonationBox.objects.get(id=value) if value and value.isdigit() else None

    if request.method == "POST":
        try:
            email = request.POST.get("email") or None

            if email and DonorVolunteer.objects.filter(email__iexact=email).exists():
                messages.error(request, "This email already exists.")
                return redirect("add_donor_volunteer")

            # CONTACT
            contact_code = request.POST.get("contact_country_code")
            contact_number = request.POST.get("contact_number")
            full_contact = f"{contact_code}{contact_number}" if contact_code and contact_number else None

            # WHATSAPP
            whatsapp_code = request.POST.get("whatsapp_country_code")
            whatsapp_number = request.POST.get("whatsapp_number")
            full_whatsapp = f"{whatsapp_code}{whatsapp_number}" if whatsapp_code and whatsapp_number else None
            gst_number = request.POST.get("gst_number")

            donor = DonorVolunteer.objects.create(

                # BASIC
                person_type=get_lookup("person_type"),
                referred_by=get_donor("referred_by"),
                donor_box=get_box("donor_box"),
                old_box_id=request.POST.get("old_box_id") or None,

                first_name=request.POST.get("first_name"),
                middle_name=request.POST.get("middle_name"),
                last_name=request.POST.get("last_name"),
                gender=request.POST.get("gender"),
                blood_group=request.POST.get("blood_group"),

                # CONTACT
                contact_number=full_contact,
                whatsapp_number=full_whatsapp,
                email=email,

                # PERSONAL
                date_of_birth=request.POST.get("date_of_birth") or None,
                age=request.POST.get("age") or None,
                doa=request.POST.get("doa") or None,
                years_to_marriage=request.POST.get("years_to_marriage") or None,

                # ADDRESS
                address=request.POST.get("address"),
                city=request.POST.get("city"),
                area=request.POST.get("area"),
                state=request.POST.get("state"),
                country=request.POST.get("country") or "India",
                postal_code=request.POST.get("postal_code"),
                native_place=request.POST.get("native_place"),

                # OCCUPATION
                occupation_salutation=request.POST.get("occupation_salutation"),
                occupation_type=get_lookup("occupation_type"),
                occupation_name=request.POST.get("occupation_name"),
                occupation_nature=get_lookup("occupation_nature"),
                gst_number=request.POST.get("gst_number"),

                # JOB
                department=get_lookup("department"),
                position=get_lookup("position"),
                designation=get_lookup("designation"),

                # ID
                id_type=get_lookup("id_type"),
                id_number=request.POST.get("id_number"),
                pan_number=request.POST.get("pan_number"),

                created_by=request.user,
                updated_by=request.user,
            )

            donor.save()

            messages.success(request, "Saved successfully!")
            return redirect("welcome")

        except Exception as e:
            print("ERROR:", e)
            messages.error(request, str(e))

    return render(request, "add_donor_volunteer.html", {
        "person_type_options": person_type_options,
        "id_type_options": id_type_options,
        "donation_boxes": donation_boxes,
        "all_donors": all_donors,
        "occupation_types": occupation_types,
        "occupation_natures": occupation_natures,
        "departments": departments,
        "positions": positions,
        "designations": designations,
        "org_types": org_types,
        "blood_groups": blood_groups,
    })


from django.db import IntegrityError, transaction, DatabaseError
from django.db.models import Sum

def adddonation(request):
    donors = DonorVolunteer.objects.none()
    today = now().date()
    donation_categories = Lookup.objects.filter(
        lookup_type__type_name__iexact="Donation Category",
        is_deleted=False
    )
    donation_sub_categories = Lookup.objects.filter(
        lookup_type__type_name__iexact="Donation-Sub-Category",
        is_deleted=False
    )
    payment_methods = Lookup.objects.filter(
        lookup_type__type_name__iexact="Payment Method",
        is_deleted=False
    )
    payment_statuses = Lookup.objects.filter(
        lookup_type__type_name__iexact="Payment Status",
        is_deleted=False
    )
    if request.method == "POST":
        donor_id = request.POST.get("donor")
        if not donor_id or not donor_id.isdigit():
            messages.error(request, "Please select a valid donor.")
            return redirect("adddonation")
        donor_obj = DonorVolunteer.objects.get(id=donor_id)
        def fk(val):
            return val if val not in ("", None) else None

        category_id = fk(request.POST.get("donation_category"))
        sub_category_id = fk(request.POST.get("donation_sub_category"))
        declared_amount = float(request.POST.get("donation_amount_declared") or 0)
        paid_amount = float(request.POST.get("donation_amount_paid") or 0)
        previous_donations = Donation.objects.filter(donor=donor_obj)

        if previous_donations.exists():
            used_categories = previous_donations.values_list("donation_category_id", flat=True)
            used_sub_categories = previous_donations.values_list("donation_sub_category_id", flat=True)
            totals = previous_donations.aggregate(
                total_declared=Sum("donation_amount_declared"),
                total_paid=Sum("donation_amount_paid")
            )
            remaining = (totals["total_declared"] or 0) - (totals["total_paid"] or 0)
            if remaining > 0 and category_id not in used_categories:
                messages.error(request,"This donation category is not allowed for this donor.")
                return redirect("adddonation")
            if remaining > 0 and sub_category_id and sub_category_id not in used_sub_categories:
                messages.error(request,"This donation sub-category is not allowed for this donor.")
                return redirect("adddonation")
        if paid_amount > declared_amount:
            messages.error(request, "Paid amount cannot exceed declared amount.")
            return redirect("adddonation")
        donation_date_raw = request.POST.get("donation_date")

        if donation_date_raw:
            donation_date = donation_date_raw
        else:
            donation_date = timezone.now().date()

        transaction_id = request.POST.get("transaction_id")
        payment_status_id = fk(request.POST.get("payment_status"))
        payment_method_id = fk(request.POST.get("payment_method"))

        payment_method_obj = Lookup.objects.filter(id=payment_method_id).first() if payment_method_id else None
        if payment_method_obj and payment_method_obj.lookup_name.strip().lower() == "razorpay":
            if not transaction_id:
                messages.error(request, "Razorpay payment is required when payment method is Razorpay.")
                return redirect("adddonation")
            if not payment_status_id:
                payment_status_id = Lookup.objects.filter(
                    lookup_type__type_name__iexact="Payment Status",
                    lookup_name__in=["Completed", "Paid", "Success"]
                ).values_list("id", flat=True).first()

        Donation.objects.create(
            donor=donor_obj,
            display_name=request.POST.get("display_name"),
            donation_amount_declared=declared_amount,
            donation_amount_paid=paid_amount,
            donation_date=donation_date,
            donation_category_id=category_id,
            donation_sub_category_id=sub_category_id,
            place_of_donation=request.POST.get("place_of_donation"),
            donation_received_by=request.POST.get("donation_received_by"),
            reference_name=request.POST.get("reference_name"),
            description=request.POST.get("description"),
            payment_method_id=payment_method_id,
            payment_status_id=payment_status_id,
            name_of_bank=request.POST.get("name_of_bank"),
            branch=request.POST.get("branch"),
            transaction_id=transaction_id,
            check_no=request.POST.get("check_no"),
            created_by=request.user,
        )
        messages.success(request, "Donation added successfully!")
        return redirect("welcome")

    return render(request, "adddonation.html", {
        "donors": donors,
        "donation_categories": donation_categories,
        "donation_sub_categories": donation_sub_categories,
        "payment_methods": payment_methods,
        "payment_statuses": payment_statuses,
        "today": today,
        "RAZORPAY_KEY_ID": settings.RAZORPAY_KEY_ID,
    })

def donation_summary(request, id):
    donation = get_object_or_404(
        Donation.objects.select_related(
            'donor', 'donation_category', 'donation_sub_category',
            'payment_method', 'payment_status', 'created_by', 'updated_by'
        ),
        id=id
    )
    donors = [donation.donor] if donation.donor else []
    today = timezone.now().date()
    donation_categories = Lookup.objects.filter(
        lookup_type__type_name__iexact="Donation Category",
        is_deleted=False
    )
    donation_sub_categories = Lookup.objects.filter(
        lookup_type__type_name__iexact="Donation-Sub-Category",
        is_deleted=False
    )
    payment_methods = Lookup.objects.filter(
        lookup_type__type_name__iexact="Payment Method",
        is_deleted=False
    )
    payment_statuses = Lookup.objects.filter(
        lookup_type__type_name__iexact="Payment Status",
        is_deleted=False
    )
    if request.method == "POST":
        def fk(val):
            return val if val not in ("", None) else None
        donation.donor_id = request.POST.get("donor")
        donation.display_name = request.POST.get("display_name")
        donation.reference_name = request.POST.get("reference_name")
        donation.donation_category_id = fk(request.POST.get("donation_category"))
        donation.donation_sub_category_id = fk(request.POST.get("donation_sub_category"))
        donation.donation_amount_declared = float(request.POST.get("donation_amount_declared") or 0)
        donation.donation_amount_paid = float(request.POST.get("donation_amount_paid") or 0)
        donation_date_raw = request.POST.get("donation_date")
        donation.donation_date = (donation_date_raw if donation_date_raw else timezone.now().date())
        donation.place_of_donation = request.POST.get("place_of_donation")
        donation.donation_received_by = request.POST.get("donation_received_by")
        donation.description = request.POST.get("description")
        donation.payment_method_id = fk(request.POST.get("payment_method"))
        donation.payment_status_id = fk(request.POST.get("payment_status"))
        donation.name_of_bank = request.POST.get("name_of_bank")
        donation.branch = request.POST.get("branch")
        donation.transaction_id = request.POST.get("transaction_id")
        donation.check_no = request.POST.get("check_no")
        donation.save()

        messages.success(request, "Donation updated successfully!")
        return redirect("donation_summary", donation.id)
    return render(request, "donation_summary.html", {
        "donation": donation,
        "donors": donors,
        "donation_categories": donation_categories,
        "donation_sub_categories": donation_sub_categories,
        "payment_methods": payment_methods,
        "payment_statuses": payment_statuses,
        "today": today,
    })

from django.http import JsonResponse

def donation_detail_ajax(request, donation_id):
    donation = get_object_or_404(Donation, id=donation_id)
    return JsonResponse({
        "donor": donation.donor_id,
        "display_name": donation.display_name,
        "reference_name": donation.reference_name,
        "donation_category": donation.donation_category_id,
        "donation_sub_category": donation.donation_sub_category_id,
        "declared_amount": donation.donation_amount_declared,
        "paid_amount": donation.donation_amount_paid,
        "payment_method": donation.payment_method_id,
        "payment_status": donation.payment_status_id,
        "donation_date": donation.donation_date.strftime("%Y-%m-%d") if donation.donation_date else "",
        "place_of_donation": donation.place_of_donation,
        "donation_received_by": donation.donation_received_by,
        "description": donation.description,
    })

def donation_summary_ajax(request, donor_id):
    donations = Donation.objects.filter(donor_id=donor_id)
    totals = donations.aggregate(
        total_declared=Sum("donation_amount_declared"),
        total_paid=Sum("donation_amount_paid")
    )
    total_declared = totals["total_declared"] or 0
    total_paid = totals["total_paid"] or 0
    remaining = total_declared - total_paid
    last_donation = donations.order_by("-id").first()

    return JsonResponse({
        "total_declared": total_declared,
        "total_paid": total_paid,
        "remaining": remaining,
        "last_category": (
            last_donation.donation_category_id if last_donation else None
        ),
        "last_sub_category": (
            last_donation.donation_sub_category_id if last_donation else None
        ),
        "last_payment_method": (
            last_donation.payment_method_id if last_donation else None
        ),
        "last_payment_status": (
            last_donation.payment_status_id if last_donation else None
        ),
        "transaction_id": last_donation.transaction_id if last_donation else "",
        "check_no": last_donation.check_no if last_donation else "",
    })

def donation_list(request):
    donations = Donation.objects.all().select_related('donor')
    return render(request, 'donation-list.html', {'donations': donations})

from xhtml2pdf import pisa
import os
from django.conf import settings
def link_callback(uri, rel):
    """
    Convert HTML image paths to absolute filesystem paths for xhtml2pdf
    """
    if uri.startswith(settings.STATIC_URL):
        path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
    elif uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
    else:
        return uri

    if not os.path.isfile(path):
        raise Exception(f"Media URI must start with {settings.STATIC_URL} or {settings.MEDIA_URL}")
    return path

from io import BytesIO
from django.core.files.base import ContentFile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

def donation_receipt_preview(request, id):
    donation = get_object_or_404(
        Donation.objects.select_related(
            'donor', 'donation_category', 'donation_sub_category',
            'payment_method', 'payment_status', 'created_by', 'updated_by'
        ),
        id=id
    )
    logo_url = request.build_absolute_uri(settings.STATIC_URL + "images/alogo.png")
    signature_url = request.build_absolute_uri(settings.STATIC_URL + "images/signature.png")
    facebook_icon = request.build_absolute_uri(settings.STATIC_URL + "images/facebook.png")
    instagram_icon = request.build_absolute_uri(settings.STATIC_URL + "images/instagram.png")
    youtube_icon = request.build_absolute_uri(settings.STATIC_URL + "images/youtube.png")
    globe_icon = request.build_absolute_uri(settings.STATIC_URL + "images/globe.png")
    return render(request, "donation_receipt.html", {
        "donation": donation,
        "signature_url": signature_url,
        "facebook_icon": facebook_icon,
        "instagram_icon": instagram_icon,
        "youtube_icon": youtube_icon,
        "globe_icon": globe_icon,
        "preview": True,
        "logo_url": logo_url,
    })
from django.template.loader import render_to_string
from reportlab.lib.colors import HexColor, black
from xhtml2pdf import pisa
from reportlab.lib.pagesizes import A5, landscape
import os
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib import colors

def download_receipt_pdf(request, id):
    donation = get_object_or_404(
        Donation.objects.select_related(
            'donor', 'donation_category', 'donation_sub_category',
            'payment_method', 'payment_status', 'created_by', 'updated_by'
        ),
        id=id
    )

    logo_url = request.build_absolute_uri(
        settings.STATIC_URL + "images/alogo.png"
    )
    signature_url = request.build_absolute_uri(
        settings.STATIC_URL + "images/signature.png"
    )
    facebook_icon = request.build_absolute_uri(
        settings.STATIC_URL + "images/facebook.png"
    )
    instagram_icon = request.build_absolute_uri(
        settings.STATIC_URL + "images/instagram.png"
    )
    youtube_icon = request.build_absolute_uri(
        settings.STATIC_URL + "images/youtube.png"
    )
    globe_icon = request.build_absolute_uri(
        settings.STATIC_URL + "images/globe.png"
    )

    html = render_to_string(
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

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="donation_receipt_{donation.receipt_id or donation.id}.pdf"'
    )

    pisa.CreatePDF(html, dest=response)

    return response

def donation_payment_receipt_view(request, id):
    payment = get_object_or_404(
        DonationPaymentBox.objects.select_related(
            "owner", "donation_box", "opened_by", "received_by", "payment_mode",
            "verified_by", "created_by", "updated_by"
        ),
        id=id,
        is_deleted=False
    )
    donor = payment.owner
    owner = payment.owner
    logo_url = request.build_absolute_uri(settings.STATIC_URL + "images/alogo.png")
    signature_url = request.build_absolute_uri(settings.STATIC_URL + "images/signature.png")
    facebook_icon = request.build_absolute_uri(settings.STATIC_URL + "images/facebook.png")
    instagram_icon = request.build_absolute_uri(settings.STATIC_URL + "images/instagram.png")
    youtube_icon = request.build_absolute_uri(settings.STATIC_URL + "images/youtube.png")
    globe_icon = request.build_absolute_uri(settings.STATIC_URL + "images/globe.png")

    return render(
        request,
        "donation_owner_receipt_pdf.html",
        {
            "payment": payment,
            "donor":donor,
            "owner": owner,
            "logo_url": logo_url,
            "signature_url": signature_url,
            "facebook_icon": facebook_icon,
            "instagram_icon": instagram_icon,
            "youtube_icon": youtube_icon,
            "globe_icon": globe_icon,
            "preview": True,
        }
    )

def donation_payment_receipt_pdf(request, id):
    payment = get_object_or_404(
        DonationPaymentBox.objects.select_related(
            "owner", "donation_box", "opened_by", "received_by", "payment_mode",
            "verified_by", "created_by", "updated_by"
        ),
        id=id,
        is_deleted=False
    )
    donor = payment.owner
    owner = payment.owner
    logo_url = request.build_absolute_uri(settings.STATIC_URL + "images/alogo.png")
    signature_url = request.build_absolute_uri(settings.STATIC_URL + "images/signature.png")
    facebook_icon = request.build_absolute_uri(
        settings.STATIC_URL + "images/facebook.png"
    )
    instagram_icon = request.build_absolute_uri(
        settings.STATIC_URL + "images/instagram.png"
    )
    youtube_icon = request.build_absolute_uri(
        settings.STATIC_URL + "images/youtube.png"
    )
    globe_icon = request.build_absolute_uri(
        settings.STATIC_URL + "images/globe.png"
    )
    owner = payment.owner
    owner_contact = None
    for attr in ("contact_number", "whatsapp_number", "mobile_no", "phone", "username", "email"):
        owner_contact = getattr(owner, attr, None)
        if owner_contact:
            break
    html = render_to_string("donation_owner_receipt_pdf.html", {
        "payment": payment,
        "donor":donor,
        "logo_url": logo_url,
        "owner_contact": owner_contact,
        "pdf": True,
        "signature_url": signature_url,
        "facebook_icon": facebook_icon,
        "instagram_icon": instagram_icon,
        "youtube_icon": youtube_icon,
        "globe_icon": globe_icon,
    })
    response = HttpResponse(content_type="application/pdf")
    response['Content-Disposition'] = f'attachment; filename="donation_payment_{payment.id}.pdf"'
    try:
        pisa_status = pisa.CreatePDF(html, dest=response, link_callback=link_callback)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return HttpResponse(f"PDF generation error: {e}\n\n{tb}", status=500)

    if getattr(pisa_status, 'err', False):
        return HttpResponse("Error generating PDF", status=500)

    return response

from datetime import date, timedelta
def download_donor_report(request):
    days = request.GET.get('days')
    donors = []
    label = ""

    if days:
        days = int(days)
        start_date = date.today() - timedelta(days=days)
        donors = DonorVolunteer.objects.filter(created_at__date__gte=start_date)
        label = f"Last {days} Days"
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="donor_report_{days}_days.pdf"'
        p = canvas.Canvas(response, pagesize=A5)
        width, height = A5
        p.setFont("Helvetica-Bold", 16)
        p.drawString(180, height - 50, f"Donor Report - {label}")
        p.setFont("Helvetica-Bold", 12)
        y = height - 100
        p.drawString(50, y, "Name")
        p.drawString(250, y, "Person Type")
        p.drawString(400, y, "City")
        y -= 20
        p.setFont("Helvetica", 11)
        for donor in donors:
            full_name = f"{donor.first_name} {donor.last_name}"
            p.drawString(50, y, full_name)
            p.drawString(250, y, donor.person_type)
            p.drawString(400, y, donor.city)
            y -= 20

            if y < 50:
                p.showPage()
                p.setFont("Helvetica", 11)
                y = height - 50

        p.showPage()
        p.save()
        return response

    return render(request, 'download_donor_report.html')

def user_list(request):
    users = User.objects.filter(userprofile__is_deleted=False)
    return render(request, 'user_list.html', {'users': users})

GREEN = HexColor("#0c6d34")
LIGHT_GREEN = HexColor("#f0f7f3")
GRAY = HexColor("#666666")
def donation_receipt_view(request, donation_id):
    """Generate a PDF receipt for the donation, save it to the model, and return it as an HTTP response."""
    donation = get_object_or_404(Donation, id=donation_id)
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A5)
    width, height = A5
    margin = 15 * mm
    y = height - margin
    line = 14
    # ================= HEADER BAR =================
    c.setFillColor(GREEN)
    c.rect(0, height - 12, width, 12, stroke=0, fill=1)
    c.setFillColor(black)
    # ================= LOGO =================
    logo_path = os.path.join(settings.BASE_DIR, "static/images/logo.png")
    if os.path.exists(logo_path):
        c.drawImage(
            ImageReader(logo_path),
            width - margin - 40,
            y - 40,
            width=35,
            height=35,
            preserveAspectRatio=True,
            mask="auto",
        )

    # ================= TITLE =================
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, y, "BHAGWAN MAHAVIR PASHU RAKSHA KENDRA")

    y -= line + 4
    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2, y, "Organised by : Sheth Shri Lalji Velji Shah")
    y -= line
    c.drawCentredString(width / 2, y, "Inspired by : Shri Jadavji Ravji Gangar")
    y -= line
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(width / 2, y, "'Anchorwala Ahinsadham'")
    y -= line * 1.5
    # ================= RECEIPT META =================
    c.setFont("Helvetica", 9)
    c.drawString(margin, y, f"Receipt No : {donation.receipt_id}")
    c.drawRightString(width - margin, y, f"Date : {donation.donation_date}")
    if donation.place_of_donation:
        y -= 10
        c.drawString(margin, y, f"({donation.place_of_donation})")
        y -= (line * 1.5 - 10)
    else:
        y -= line * 1.5
    # ================= SECTION: DONOR =================
    c.setFillColor(LIGHT_GREEN)
    c.rect(margin, y - 12, width - 2 * margin, 14, stroke=0, fill=1)
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 6, y - 8, "Donor Details")
    c.setFillColor(black)
    y -= line * 1.5
    c.setFont("Helvetica", 9)
    donor = getattr(donation, "donor", None)
    donor_name = ""
    donor_mobile = ""
    donor_address = ""
    if donor:
        donor_name = f"{donor.first_name or ''} {donor.last_name or ''}".strip()
        donor_mobile = getattr(donor, "contact_number", "")
        donor_address = getattr(donor, "address", "")
    c.drawString(margin, y, f"Name : {donor_name}")
    y -= line
    c.drawString(margin, y, f"Mobile : {donor_mobile}")
    y -= line
    c.drawString(margin, y, f"Address : {donor_address}")
    y -= line * 1.5
    # ================= SECTION: DONATION =================
    c.setFillColor(LIGHT_GREEN)
    c.rect(margin, y - 12, width - 2 * margin, 14, stroke=0, fill=1)
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 6, y - 8, "Donation Details")
    c.setFillColor(black)
    y -= line * 1.5
    c.setFont("Helvetica", 9)
    c.drawString(margin, y, f"Category : {getattr(donation, 'donation_category', '')}")
    y -= line
    c.drawString(margin, y, f"Payment Mode : {getattr(donation, 'payment_method', '')}")
    y -= line
    c.drawString(margin, y, f"Payment Status : {getattr(donation, 'payment_status', '')}")

    y -= line * 1.2

    # ================= AMOUNT =================
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(GREEN)
    total_paid = getattr(donation, 'donation_amount_paid', 0)
    c.drawRightString(width - margin, y, f"TOTAL : ₹ {total_paid}")
    c.setFillColor(black)

    y -= line * 2

    # ================= FOOTER =================
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(width / 2, y, "Thank you for your valuable Donation")

    y -= line * 2
    c.setFont("Helvetica", 9)
    c.drawRightString(width - margin, y, "Authorized Signatory")
    c.showPage()
    c.save()
    buffer.seek(0)
    pdf_data = buffer.getvalue()
    try:
        if hasattr(donation, 'receipt') and donation.receipt:
            try:
                donation.receipt.delete(save=False)
            except Exception:
                pass
    except Exception:
        pass
    file_name = f"donation_receipt_{getattr(donation, 'receipt_id', donation_id)}.pdf"
    if hasattr(donation, 'receipt'):
        try:
            donation.receipt.save(file_name, ContentFile(pdf_data))
            donation.save()
        except Exception:
            receipts_dir = os.path.join(settings.MEDIA_ROOT, 'receipts')
            os.makedirs(receipts_dir, exist_ok=True)
            file_path = os.path.join(receipts_dir, file_name)
            with open(file_path, 'wb') as f:
                f.write(pdf_data)
    else:
        receipts_dir = os.path.join(settings.MEDIA_ROOT, 'receipts')
        os.makedirs(receipts_dir, exist_ok=True)
        file_path = os.path.join(receipts_dir, file_name)
        with open(file_path, 'wb') as f:
            f.write(pdf_data)
    buffer.close()
    response = HttpResponse(pdf_data, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{file_name}"'
    return response

from .models import DonationPaymentBox, DonationBox
from django.core.mail import send_mail
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
import json
@login_required
def add_donation_payment(request):
    payment_mode = None
    payment_type = LookupType.objects.filter(
        type_name__iexact="payment_mode",
        is_deleted=False
    ).first()

    payment_modes = Lookup.objects.filter(
        lookup_type=payment_type,
        is_deleted=False
    )

    donation_boxes = DonationBox.objects.filter(
        is_deleted=False,
        donorvolunteer__isnull=False
    ).distinct()

    donor_volunteers = DonorVolunteer.objects.filter(
        is_deleted=False,
        person_type__lookup_name__iexact="Employee"
    ).only('id', 'first_name', 'last_name')

    box_owner_map = []

    owners = DonorVolunteer.objects.filter(
        is_deleted=False,
        donor_box__isnull=False
    ).select_related('donor_box').only('id', 'first_name', 'last_name', 'address', 'city', 'state', 'postal_code', 'donor_box__id')

    for owner in owners:
        address = ", ".join(filter(None, [
            owner.address,
            owner.city,
            owner.state,
            owner.postal_code
        ]))

        box_owner_map.append({
            "box_id": owner.donor_box.id,
            "owner_id": owner.id,
            "owner_name": f"{owner.first_name} {owner.last_name}",
            "address": address,
        })

    if request.method == "POST":

        donation_box = get_object_or_404(
            DonationBox,
            id=request.POST.get("donation_box")
        )

        opened_by_id = request.POST.get("opened_by")
        received_by_id = request.POST.get("received_by")

        opened_by = DonorVolunteer.objects.filter(id=opened_by_id).first() if opened_by_id else None
        received_by = DonorVolunteer.objects.filter(id=received_by_id).first() if received_by_id else None

        owner = DonorVolunteer.objects.filter(
            donor_box=donation_box,
            is_deleted=False
        ).first()

        payment_mode_id = request.POST.get("payment_mode")

        if not payment_mode_id:
            messages.error(request, "Please select payment mode.")
            return redirect("add_donation_payment")

        payment_mode = Lookup.objects.filter(id=payment_mode_id).first()

        DonationPaymentBox.objects.create(
            owner=owner,
            donation_box=donation_box,
            address=request.POST.get("address"),
            opened_by=opened_by,
            received_by=received_by,
            amount=request.POST.get("amount"),
            payment_mode=payment_mode,
            date_time=request.POST.get("date_time"),
            i_witness=request.POST.get("i_witness"),
            created_by=request.user,
            updated_by=request.user,
        )

        messages.success(request, "Donation Payment Added Successfully!")
        return redirect("welcome")

    context = {
        "donation_boxes": donation_boxes,
        "payment_modes": payment_modes,
        "donor_volunteers": donor_volunteers,
        "box_owner_map": json.dumps(box_owner_map, cls=DjangoJSONEncoder),
        "current_time": timezone.now(),
        "RAZORPAY_KEY_ID": settings.RAZORPAY_KEY_ID
    }

    return render(request, "add_donationbox_payment.html", context)


from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import DonationBox

@login_required
def add_donation_box(request):
    if request.method == "POST":
        key_id = request.POST.get("key_id")
        box_size = request.POST.get("box_size")  
        status = request.POST.get("status")
        qr_code = request.FILES.get("qr_code")
        box_owner = request.POST.get("box_owner")
        box_percentage = request.POST.get("box_percentage")

        if not box_owner or not box_percentage:
            messages.error(request, "Box Owner and Box % are required!")
            return redirect("add_donation_box")

        try:
            box_percentage = float(box_percentage)
            if box_percentage < 0 or box_percentage > 100:
                messages.error(request, "Box % must be between 0 and 100!")
                return redirect("add_donation_box")
        except ValueError:
            messages.error(request, "Invalid Box % value!")
            return redirect("add_donation_box")

        box = DonationBox(
            key_id=key_id,
            box_size=box_size,
            status=status,
            qr_code=qr_code if qr_code else None,
            box_owner=box_owner,
            box_percentage=box_percentage,
            uploaded_by=request.user,
            created_by=request.user,
            created_at=timezone.now(),
        )

        box.save()

        messages.success(request, "Donation Box Added Successfully!")
        return redirect("welcome")

    context = {
        "status_choices": DonationBox.status_choices,
    }
    return render(request, "add_donation_box.html", context)
def all_donations(request):
    q = request.GET.get('q', '').strip()
    donations = Donation.objects.filter(is_deleted=False)

    if q:
        donations = donations.filter(
            Q(donor__first_name__icontains=q) |
            Q(donor__last_name__icontains=q) |
            Q(donation_category__icontains=q) |
            Q(donation_mode__icontains=q) |
            Q(payment_method__icontains=q) |
            Q(transaction_id__icontains=q)
        ).distinct()
    message = None
    if q and not donations.exists():
        message = f'No matching records found for "{q}".'

    return render(request, 'donation-list.html', {
        'donations': donations,
        'query': q,
        'message': message
    })

def donation_list(request):
    donations = Donation.objects.all().order_by('id')
    page = request.GET.get('page', 1) 
    paginator = Paginator(donations, 1)
    donations_page = paginator.get_page(page)
    return render(request, 'donation_list.html', {'donations': donations_page})

def lookup_type_create(request):
    if request.method == "POST":
        type_name = request.POST.get("type_name").strip()
        if LookupType.objects.filter(type_name__iexact=type_name, is_deleted=False).exists():
            messages.error(
                request,
                f"Lookup Type '{type_name}' already exists!"
            )
            return render(request, "lookup_type_form.html", {"lookup_type": None})
        deleted_record = LookupType.objects.filter(type_name__iexact=type_name, is_deleted=True).first()
        if deleted_record:
            deleted_record.is_deleted = False
            deleted_record.deleted_at = None
            deleted_record.updated_by = request.user
            deleted_record.save()

            messages.success(request, f"Lookup Type '{type_name}' restored successfully!")
            return render(request, "lookup_type_form.html", {"lookup_type": None})
        lookup_type = LookupType(
            type_name=type_name,
            created_by=request.user,
            updated_by=request.user,
        )
        lookup_type.save()
        messages.success(request, "Lookup Type added successfully!")
        return render(request, "lookup_type_form.html", {"lookup_type": None})
    return render(request, "lookup_type_form.html", {"lookup_type": None})

def lookup_create(request):
    lookup_types = LookupType.objects.filter(is_deleted=False)
    if request.method == "POST":
        name = request.POST.get("lookup_name")
        type_id = request.POST.get("lookup_type")
        if Lookup.objects.filter(lookup_name=name, lookup_type_id=type_id).exists():
            messages.error(request, "This Lookup already exists!")
            return render(request, "lookup_form.html", {
                "lookup_types": lookup_types,
                "lookup_name": name,
                "lookup_type_id": type_id,
                "lookup": None
            })

        try:
            lookup = Lookup(
                lookup_name=name,
                lookup_type_id=type_id,
                created_by=request.user,
                updated_by=request.user
            )
            lookup.save()

            messages.success(request, "Lookup added successfully!")
            return redirect("lookup_create")
        except IntegrityError:
            messages.error(request, "Error: Duplicate or invalid data!")
            return render(request, "lookup_form.html", {
                "lookup_types": lookup_types,
                "lookup_name": name,
                "lookup_type_id": type_id,
                "lookup": None
            })
    return render(request, "lookup_form.html", {
        "lookup_types": lookup_types,
        "lookup": None
    })
# ************* Edit Data Start *************
def edit_lookup_type(request, id):
    lookup_type = get_object_or_404(
        LookupType,
        id=id,
        is_deleted=False 
    )
    if request.method == "POST":
        lookup_type.type_name = request.POST.get("type_name", lookup_type.type_name)
        lookup_type.updated_by = request.user
        lookup_type.save()
        messages.success(request, "Lookup Type updated successfully!")
        return redirect("welcome")
    return render(request, "edit_lookup_type.html", {
        "lookup_type": lookup_type
    })
def edit_lookup(request, id):
    lookup = get_object_or_404(Lookup, id=id)
    types = LookupType.objects.all()
    if request.method == "POST":
        lookup.lookup_name = request.POST.get("lookup_name")
        lookup.lookup_type_id = request.POST.get("lookup_type")
        lookup.updated_by = request.user
        lookup.save()
        return redirect("welcome")
    return render(request, "edit_lookup.html", {
        "lookup": lookup,
        "types": types
    })

@login_required
def edit_user(request, id):
    user_obj = get_object_or_404(User, id=id)
    user_role_obj, created = UserRole.objects.get_or_create(user=user_obj)
    roles = UserModuleAccess.objects.values_list('name', flat=True).order_by().distinct()

    if request.method == 'POST':
        new_username = request.POST.get('username')

        if User.objects.filter(username=new_username).exclude(id=user_obj.id).exists():
            messages.error(request, "Username already exists! Please choose a different one.")
            return redirect(request.path)

        user_obj.first_name = request.POST.get('first_name')
        user_obj.last_name  = request.POST.get('last_name')
        user_obj.username   = new_username
        user_obj.email      = request.POST.get('email')

        role_name_selected = request.POST.get('role')
        if role_name_selected in ["", "none", "None", None]:
            user_role_obj.role = None
            user_role_obj.save()
        else:
            if not request.user.is_superuser:
                messages.error(request, "❌ You are not allowed to assign roles.")
                return redirect("welcome")

            selected_role = UserModuleAccess.objects.filter(name=role_name_selected).first()
            if not selected_role:
                messages.error(request, "❌ Selected role does not exist.")
                return redirect("welcome")
            user_role_obj.role = selected_role
            user_role_obj.save()

        user_obj.save()
        messages.success(request, "User updated successfully!")
        return redirect('welcome')

    return render(
        request,
        'edit_user.html',
        {
            'edit_user': user_obj,
            'roles': roles,
            'user_role': user_role_obj,
        }
    )

def edit_usermoduleaccess(request, id):
    record = get_object_or_404(UserModuleAccess, id=id)
    if request.method == 'POST':
        record.name = request.POST.get("name") or record.name
        record.description = request.POST.get("description") or record.description
        record.can_access = bool(request.POST.get("can_access"))
        record.can_add = bool(request.POST.get("can_add"))
        record.can_edit = bool(request.POST.get("can_edit"))
        record.can_delete = bool(request.POST.get("can_delete"))
        record.can_view = bool(request.POST.get("can_view"))
        record.save()
        return redirect("welcome")
    return render(request, "edit_usermoduleaccess.html", {"access": record})

from .models import DonationBox
from django.contrib.auth.decorators import login_required

@login_required
def edit_donor(request, donor_id):
    donor = get_object_or_404(DonorVolunteer, id=donor_id)

    donors = [donor.referred_by] if donor.referred_by and not donor.referred_by.is_deleted else []

    person_type_options = Lookup.objects.filter(lookup_type__type_name__iexact='Person Type')
    id_types = Lookup.objects.filter(lookup_type__type_name="ID Type", is_deleted=False)

    occupation_types = Lookup.objects.filter(lookup_type__type_name="Occupation Type", is_deleted=False)
    occupation_natures = Lookup.objects.filter(lookup_type__type_name="Occupation Nature", is_deleted=False)

    departments = Lookup.objects.filter(lookup_type__type_name="Department", is_deleted=False)
    positions = Lookup.objects.filter(lookup_type__type_name="Position", is_deleted=False)
    designations = Lookup.objects.filter(lookup_type__type_name="Designation", is_deleted=False)

    donation_boxes = DonationBox.objects.filter(is_deleted=False)

    if request.method == "POST":
        try:
            donor.person_type_id = request.POST.get("person_type") or None
            donor.referred_by_id = request.POST.get("referred_by") or None
            donor.donor_box_id = request.POST.get("donor_box") or None
            donor.old_box_id = request.POST.get("old_box_id") or None

            donor.salutation = request.POST.get("salutation")
            donor.first_name = request.POST.get("first_name")
            donor.middle_name = request.POST.get("middle_name")
            donor.last_name = request.POST.get("last_name")
            donor.gender = request.POST.get("gender")
            donor.blood_group = request.POST.get("blood_group")

            contact_code = request.POST.get("contact_country_code")
            contact_number = request.POST.get("contact_number")
            donor.contact_number = f"{contact_code}{contact_number}" if contact_code and contact_number else None

            whatsapp_code = request.POST.get("whatsapp_country_code")
            whatsapp_number = request.POST.get("whatsapp_number")
            donor.whatsapp_number = f"{whatsapp_code}{whatsapp_number}" if whatsapp_code and whatsapp_number else None

            donor.email = request.POST.get("email")
            donor.date_of_birth = request.POST.get("date_of_birth") or None
            donor.age = request.POST.get("age") or None
            donor.doa = request.POST.get("doa") or None
            donor.years_to_marriage = request.POST.get("years_to_marriage") or None

            donor.address = request.POST.get("address")
            donor.city = request.POST.get("city")
            donor.area = request.POST.get("area")
            donor.state = request.POST.get("state")
            donor.country = request.POST.get("country") or "India"
            donor.postal_code = request.POST.get("postal_code")
            donor.native_place = request.POST.get("native_place")

            donor.occupation_salutation = request.POST.get("occupation_salutation")
            donor.occupation_type_id = request.POST.get("occupation_type") or None
            donor.occupation_name = request.POST.get("occupation_name")
            donor.occupation_nature_id = request.POST.get("occupation_nature") or None
            donor.gst_number = request.POST.get("gst_number")

            donor.department_id = request.POST.get("department") or None
            donor.position_id = request.POST.get("position") or None
            donor.designation_id = request.POST.get("designation") or None

            donor.id_type_id = request.POST.get("id_type") or None
            donor.id_number = request.POST.get("id_number")
            donor.pan_number = request.POST.get("pan_number")

            if request.FILES.get("id_proof_image"):
                donor.id_proof_image = request.FILES["id_proof_image"]

            if request.FILES.get("pan_card_image"):
                donor.pan_card_image = request.FILES["pan_card_image"]

            donor.updated_by = request.user
            donor.save()

            messages.success(request, "Updated successfully!")
            return redirect("welcome")

        except Exception as e:
            print("ERROR:", e)
            messages.error(request, str(e))

    return render(request, "edit_donor.html", {
        "donor": donor,
        "donors": donors,
        "person_type_options": person_type_options,
        "id_types": id_types,
        "donation_boxes": donation_boxes,
        "occupation_types": occupation_types,
        "occupation_natures": occupation_natures,
        "departments": departments,
        "positions": positions,
        "designations": designations,
        "gst_number": donor.gst_number,
        "blood_groups": DonorVolunteer.BLOOD_GROUP_CHOICES,
    })



def edit_donation(request, id):
    donation = get_object_or_404(Donation, id=id)
    donors = [donation.donor] if donation.donor else []
    donation_categories = Lookup.objects.filter(
        lookup_type__type_name="Donation Category"
    )
    donation_modes = Lookup.objects.filter(
        lookup_type__type_name="Donation Mode"
    )
    payment_methods = Lookup.objects.filter(
        lookup_type__type_name="Payment Method"
    )
    payment_statuses = Lookup.objects.filter(
        lookup_type__type_name="Payment Status"
    )

    if request.method == "POST":
        donation.donor_id = request.POST.get("donor")
        donation.donation_date = request.POST.get("donation_date")
        donation.donation_category_id = request.POST.get("donation_category")
        donation.donation_mode_id = request.POST.get("donation_mode")
        donation.payment_method_id = request.POST.get("payment_method")
        donation.payment_status_id = request.POST.get("payment_status")

        donation.transaction_id = request.POST.get("transaction_id")
        donation.receipt_id = request.POST.get("receipt_id")
        donation.check_no = request.POST.get("check_no")
        donation.place_of_donation = request.POST.get("place_of_donation")
        donation.description = request.POST.get("description")

        donation.donation_amount_declared = request.POST.get("donation_amount_declared") or 0
        donation.donation_amount_paid = request.POST.get("donation_amount_paid") or 0
        donation.updated_by = request.user
        donation.save()

        messages.success(request, "Donation updated successfully!")
        return redirect("welcome")

    return render(request, "edit_donation.html", {
        "donation": donation,
        "donors": donors,
        "donation_categories": donation_categories,
        "donation_modes": donation_modes,
        "payment_methods": payment_methods,
        "payment_statuses": payment_statuses,
    })

from django.utils.dateparse import parse_datetime

def edit_box_payment(request, id):
    payment = get_object_or_404(DonationPaymentBox, id=id)

    if request.method == 'POST':

        # Text / numeric fields
        payment.address = request.POST.get('address')
        payment.amount = request.POST.get('amount')
        payment.i_witness = request.POST.get('i_witness')
        payment.name_of_bank = request.POST.get('name_of_bank')
        payment.branch = request.POST.get('branch')
        payment.transaction_id = request.POST.get('transaction_id')

        # Foreign keys (IMPORTANT)
        payment.payment_method_id = (
            int(request.POST.get('payment_method'))
            if request.POST.get('payment_method') else None
        )

        payment.opened_by_id = (
            int(request.POST.get('opened_by'))
            if request.POST.get('opened_by') else None
        )

        payment.received_by_id = (
            int(request.POST.get('received_by'))
            if request.POST.get('received_by') else None
        )

        # Datetime (VERY IMPORTANT)
        date_time = request.POST.get('date_time')
        if date_time:
            payment.date_time = parse_datetime(date_time)

        # Audit
        payment.updated_by = request.user
        payment.updated_at = timezone.now()

        payment.save()

        messages.success(request, "Payment updated successfully!")
        return redirect('welcome')

    return render(request, 'BoxPayment.html', {
        'payment': payment,
        'payment_methods': Lookup.objects.filter(
            lookup_type__type_name__iexact='Payment Method',
            is_deleted=False
        ),
        'donors': DonorVolunteer.objects.filter(is_deleted=False).only('id', 'first_name', 'last_name')
    })

from decimal import Decimal

def edit_donation_box(request, id):
    box = get_object_or_404(DonationBox, id=id)

    if request.method == 'POST':
        box.key_id = request.POST.get('key_id')
        box.box_size = request.POST.get('box_size')
        box.box_owner = request.POST.get('box_owner')

        percentage = request.POST.get('box_percentage')
        if percentage:
            box.box_percentage = Decimal(percentage)
        else:
            box.box_percentage = None

        box.status = request.POST.get('status')

        qr_file = request.FILES.get('qr_code')
        if qr_file:
            box.qr_code = qr_file

        box.save()
        messages.success(request, "Donation Box updated successfully!")
        return redirect('welcome')

    return render(request, 'DonationBoxedit.html', {
        'box': box,
        'status_choices': DonationBox.status_choices,
        'box_sizes': DonationBox.BOX_SIZES
    })
# ************* End Edit Data Start *************

# ************* delete Data Start *************

def delete_user(request, user_id):
    print("Delete function triggered for:", user_id)
    user_to_delete = get_object_or_404(User, id=user_id)
    user_to_delete.is_active = False 
    user_to_delete.save()
    return redirect('welcome')

from django.urls import reverse
@login_required
def delete_lookup_type(request, lookup_type_id):
    if request.method == "POST":
        lookup_type = get_object_or_404(LookupType, id=lookup_type_id)
        lookup_type.is_deleted = True
        lookup_type.deleted_at = timezone.now()
        lookup_type.updated_by = request.user
        lookup_type.deleted_by = request.user
        lookup_type.save()
        messages.success(request, f"🗑 Lookup Type '{lookup_type.type_name}' deleted successfully.")
        page = request.POST.get("lt_page", 1)
        return redirect(reverse("welcome") + f"?lt_page={page}")

    return redirect("welcome")

@login_required
def delete_lookup(request, lookup_id):
    if request.method == "POST":
        lookup = get_object_or_404(Lookup, id=lookup_id)
        lookup.is_deleted = True
        lookup.deleted_at = timezone.now()
        lookup.deleted_by = request.user
        lookup.save()
        messages.success(request, f"✅ Lookup '{lookup.lookup_name}' deactivated.")
        page = request.GET.get("lu_page", 1)
        return redirect(reverse("welcome") + f"?lu_page={page}")
    return redirect("welcome")

@login_required
def delete_user_module_access(request, access_id):
    if request.method == "POST":
        access = get_object_or_404(UserModuleAccess, id=access_id)
        access.is_deleted = True
        access.deleted_at = timezone.now()
        access.updated_by = request.user
        access.deleted_by = request.user
        access.save()
        messages.success(request, f"🗑️ Role '{access.name}' has been deleted successfully.")
        page = request.GET.get("uma_page", 1)
        return redirect(reverse("welcome") + f"?uma_page={page}")
    return redirect("welcome")

@login_required
def delete_donor_volunteer(request, donor_id):
    if request.method == "POST":
        donor = get_object_or_404(DonorVolunteer, id=donor_id)
        donor.is_deleted = True
        donor.deleted_at = timezone.now()
        donor.updated_by = request.user
        donor.deleted_by = request.user
        donor.save()
        messages.success(request, f"🗑️ '{donor.first_name} {donor.last_name}' has been deleted successfully.")
        page = request.GET.get("dv_page", 1)
        return redirect(reverse("welcome") + f"?dv_page={page}")

    return redirect("welcome")
@login_required
def delete_donation(request, donation_id):
    if request.method == "POST":
        donation = get_object_or_404(Donation, id=donation_id)
        donation.is_deleted = True
        donation.deleted_at = timezone.now()
        donation.updated_by = request.user
        donation.deleted_by = request.user
        donation.save()
        messages.success(request, f"🗑 Donation receipt '{donation.receipt_id}' deleted successfully.")
        page = request.GET.get("donation_page", 1)
        return redirect(reverse("welcome") + f"?donation_page={page}")

    return redirect("welcome")

from .models import DonationPaymentBox

@login_required
def delete_box_payment(request, id):
    if request.method == "POST":
        payment = get_object_or_404(DonationPaymentBox,id=id,is_deleted=False)
        payment.is_deleted = True
        payment.deleted_at = now()
        payment.updated_by = request.user
        payment.deleted_by = request.user
        payment.save()
        messages.success(request, "Donation Box Payment deleted successfully!")
    return redirect("welcome")

def delete_donation_box(request, id):
    if request.method == "POST":
        box = get_object_or_404(DonationBox, id=id,is_deleted=False)
        box.is_deleted = True
        box.deleted_at = now()
        box.deleted_by = request.user
        box.save()
        messages.success(request, "Donation box deleted successfully!")
        return redirect('welcome')
# ************* delete Data end *************

def edit_box_payment(request, id):
    payment = get_object_or_404(DonationPaymentBox, id=id)

    if request.method == 'POST':
        payment.address = request.POST.get('address')
        payment.amount = request.POST.get('amount')
        payment.i_witness = request.POST.get('i_witness')
        payment.updated_by = request.user
        payment.save()

        messages.success(request, "Payment updated successfully!")
        return redirect('welcome') 

    return render(request, 'BoxPayment.html', {
        'payment': payment
    })

# donationbox eidt view------------------------------

@login_required
def verify_donation(request, donation_id):
    donation = get_object_or_404(Donation, id=donation_id)
    if not donation.verified:
        donation.verified = True
        donation.verified_by = request.user
        donation.save(update_fields=["verified", "verified_by"])
    messages.success(request, "Donation verified successfully.")
    return redirect("welcome")

@login_required
def verify_payment(request, payment_id):
    try:
        payment = get_object_or_404(DonationPaymentBox, id=payment_id)
        payment.verified = True
        payment.verified_by = request.user
        payment.verified_at = timezone.now()
        payment.save()
        messages.success(request, "Payment has been verified successfully!")

    except Exception as e:
        messages.error(request, f"Error verifying payment: {str(e)}")

    return redirect("welcome")

def select_donation_box(request):
    if request.method == "POST":
        donation_box_id = request.POST.get("donation_box_id", "").strip()

        if not donation_box_id:
            messages.error(
                request,"Please scan the QR code or enter a valid Donation Box ID."
            )
            return redirect("select_donation_box")

        try:
            donation_box = DonationBox.objects.get(
                donation_id__iexact=donation_box_id,is_deleted=False)
            request.session["selected_donation_box_id"] = donation_box.id

            messages.success(
                request,
                f"Donation Box '{donation_box.donation_id}' selected successfully."
            )
            return redirect("add_donation_payment")

        except DonationBox.DoesNotExist:
            messages.error(
                request,"Invalid Donation Box ID. Please scan the correct QR code or re-enter the ID."
            )
            return redirect("select_donation_box")

    return render(request, "donation_box_input.html")

from django.http import JsonResponse

def get_donation_boxes_data(request):
    """Returns all donation boxes for the modal dropdown"""
    boxes = DonationBox.objects.filter(is_deleted=False).values(
        'id', 'donation_id', 'key_id', 'box_size', 'box_owner'
    ).order_by('-created_at')
    
    return JsonResponse({
        'boxes': list(boxes)
    })

def get_donation_box_details(request, box_id):
    """Returns auto-fill data for a selected donation box"""
    try:
        box = DonationBox.objects.get(id=box_id, is_deleted=False)
        last_payment = DonationPaymentBox.objects.filter(
            donation_box=box,
            is_deleted=False
        ).order_by('-created_at').first()
        
        last_donation = Donation.objects.filter(
            is_deleted=False
        ).order_by('-created_at').first()
        
        data = {
            'donation_id': box.donation_id,
            'key_id': box.key_id or '',
            'box_owner': box.box_owner or '',
            'box_size': box.box_size,
            'payment_id': f"PAY_{box.donation_id}_{DonationPaymentBox.objects.filter(donation_box=box).count() + 1:03d}",
            'last_payment_method': last_payment.payment_method_id if last_payment else (last_donation.payment_method_id if last_donation else None),
            'last_payment_status': last_payment.payment_status_id if last_payment else None,
            'bank_name': last_payment.name_of_bank if last_payment else (last_donation.name_of_bank if last_donation else ''),
            'branch': last_payment.branch if last_payment else (last_donation.branch if last_donation else ''),
            'transaction_id': last_payment.transaction_id if last_payment else '',
        }
        
        return JsonResponse(data)
    
    except DonationBox.DoesNotExist:
        return JsonResponse({'error': 'Donation box not found'}, status=404)

def get_donation_data(request, donation_id):
    """Returns auto-fill data for a selected donation"""
    try:
        donation = Donation.objects.get(id=donation_id, is_deleted=False)
        
        data = {
            'donation_id': donation.id,
            'donor_name': f"{donation.donor.first_name} {donation.donor.last_name}",
            'donor_pan': donation.donor.pan_number or '',
            'display_name': donation.display_name or '',
            'donation_amount_declared': str(donation.donation_amount_declared or 0),
            'donation_amount_paid': str(donation.donation_amount_paid or 0),
            'payment_method': donation.payment_method_id,
            'payment_status': donation.payment_status_id,
            'bank_name': donation.name_of_bank or '',
            'branch': donation.branch or '',
            'transaction_id': donation.transaction_id or '',
            'check_no': donation.check_no or '',
            'donation_date': str(donation.donation_date),
        }
        
        return JsonResponse(data)
    
    except Donation.DoesNotExist:
        return JsonResponse({'error': 'Donation not found'}, status=404)
    
def add_event(request):
    if request.method == "POST":
        Event.objects.create(
            event_name = request.POST.get('event_name'),
            event_type = request.POST.get('event_type'),
            event_date = request.POST.get('event_date'),
            start_time = request.POST.get('start_time'),
            end_time = request.POST.get('end_time'),
            venue = request.POST.get('venue'),
            organizer_name = request.POST.get('organizer_name'),
            organizer_contact = request.POST.get('organizer_contact'),
            description = request.POST.get('description'),
        )
        return redirect('welcome')

    return render(request, 'add_event.html')

import razorpay
from django.conf import settings
from django.http import JsonResponse

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
def create_order(request):
    amount = int(request.GET.get("amount")) * 100
    payment = client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": "1"
    })

    return JsonResponse({
        "order_id": payment["id"],
        "amount": payment["amount"]
    })


from django.shortcuts import render

def add_leave(request):
    return render(request, "add_leave.html")


def add_timesheet(request):
    return render(request,"add_timesheet.html")

def add_visitor(request):
    return render(request,"add_visitor.html")

def add_vendor(request):
    return render(request, "add_vendor.html")

def add_request(request):
    return render(request, "add_request.html")

def add_inventory(request):
    return render(request, "add_inventory.html")

def add_assets(request):
    return render(request, "add_assets.html")

def add_fleet(request):
    return render(request, "add_fleet.html")

def add_financial_asset(request):
    return render(request, "add_financial_asset.html")

def add_expense(request):
    return render(request, "add_expense.html")

def add_medical(request):
    return render(request, "add_medical.html")

def add_rehabilitation(request):
    return render(request, "add_rehabilitation.html")

def add_adoption(request):
    return render(request, "add_adoption.html")   

def add_trees(request):
    return render(request, "add_trees.html")

def add_seeds(request):
    return render(request, "add_seeds.html") 


import os
import json
import uuid
from decimal import Decimal, InvalidOperation

import razorpay
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static as static_url
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Donation, DonorVolunteer

def _validate_donation_post(post_data):
    """Validate and normalize the plain HTML donation form."""
    field_names = (
        'first_name', 'middle_name', 'last_name', 'pan_number', 'mobile_number', 'email', 'address', 'area',
        'city', 'state', 'country', 'postal_code', 'native_place',
        'donation_amount', 'reference',
    )
    cleaned_data = {
        field: (post_data.get(field) or '').strip()
        for field in field_names
    }
    errors = {}

    for field in ('first_name', 'last_name', 'pan_number', 'mobile_number', 'country', 'donation_amount'):
        if not cleaned_data[field]:
            errors[field] = ['This field is required.']

    pan = cleaned_data['pan_number']
    if pan:
        pan = pan.upper()
        cleaned_data['pan_number'] = pan
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan):
            errors['pan_number'] = ['Enter a valid 10-character PAN (e.g. ABCDE1234F).']

    mobile = cleaned_data['mobile_number']
    if mobile:
        mobile_to_check = mobile[1:] if mobile.startswith('+') else mobile
        if not mobile_to_check.isdigit() or not 10 <= len(mobile_to_check) <= 15:
            errors['mobile_number'] = [
                'Enter a valid mobile number between 10 and 15 digits.'
            ]

    email = cleaned_data['email']
    if email:
        try:
            validate_email(email)
        except ValidationError:
            errors['email'] = ['Enter a valid email address.']

    if cleaned_data['country'] and cleaned_data['country'] not in ('India', 'Other'):
        errors['country'] = ['Select a valid choice.']

    amount = cleaned_data['donation_amount']
    if amount:
        try:
            amount_decimal = Decimal(amount)
            if not amount_decimal.is_finite() or amount_decimal <= 0:
                raise InvalidOperation
            if len(amount_decimal.as_tuple().digits) > 12:
                errors['donation_amount'] = [
                    'Ensure that there are no more than 12 digits in total.'
                ]
            elif abs(amount_decimal.as_tuple().exponent) > 2:
                errors['donation_amount'] = [
                    'Ensure that there are no more than 2 decimal places.'
                ]
            else:
                cleaned_data['donation_amount'] = amount_decimal
        except (InvalidOperation, ValueError):
            errors['donation_amount'] = ['Enter a valid amount.']

    return cleaned_data, errors


def _is_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _get_razorpay_credentials():
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', None) or os.getenv(
        'RAZORPAY_KEY_ID'
    )
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', None) or os.getenv(
        'RAZORPAY_KEY_SECRET'
    )
    return key_id, key_secret


def donation_view(request):
    form_data = {}
    initial_amount = ''

    if request.method == 'POST':
        donation_data, errors = _validate_donation_post(request.POST)
        form_data = request.POST.dict()
        if not errors:
            try:
                # Don't save yet. Store cleaned data in session and create Razorpay order.
                # Decimal to string for serialization
                if 'donation_amount' in donation_data:
                    donation_data['donation_amount'] = str(donation_data['donation_amount'])

                # Include selected scheme info from POST (hidden inputs) if present
                scheme_id = request.POST.get('scheme_id')
                scheme_name = request.POST.get('scheme_name')
                if scheme_id:
                    donation_data['scheme_id'] = scheme_id
                if scheme_name:
                    donation_data['scheme_name'] = scheme_name

                # Persist selected scheme in session for later (payment) pages
                if scheme_id or scheme_name:
                    request.session['selected_scheme'] = {'id': scheme_id, 'name': scheme_name}
                request.session['donation_data'] = donation_data



                key_id, key_secret = _get_razorpay_credentials()

                amount_paise = int(float(donation_data['donation_amount']) * 100)
                receipt = donation_data.get('reference') or f"donation_{timezone.now().timestamp()}"

                # Mock mode if keys are not configured
                if not key_id or not key_secret:
                    mock_order_id = f"mock_order_{uuid.uuid4().hex[:10]}"
                    order = {
                        'id': mock_order_id,
                        'amount': amount_paise,
                        'currency': 'INR',
                        'receipt': receipt
                    }
                    request.session['razorpay_order'] = order
                    if _is_ajax(request):
                        return JsonResponse({'success': True, 'order': order, 'is_mock': True})
                    return redirect('payment')

                # Real Razorpay flow
                client = razorpay.Client(auth=(key_id, key_secret))
                try:
                    order = client.order.create({
                        'amount': amount_paise,
                        'currency': 'INR',
                        'receipt': receipt,
                        'payment_capture': '1'
                    })
                except Exception:
                    return JsonResponse({
                        'success': False,
                        'error': 'Unable to create the payment order. Please try again.'
                    }, status=500)

                # Store order in session for verification later
                request.session['razorpay_order'] = order

                # If AJAX request, return order details and key so frontend opens Razorpay
                if _is_ajax(request):
                    return JsonResponse({'success': True, 'order': order, 'key_id': key_id, 'is_mock': False})

                # non-AJAX fallback: redirect to payment page
                return redirect('payment')
            
            except Exception:
                return JsonResponse({
                    'success': False,
                    'error': 'Unable to process the donation. Please try again.'
                }, status=500)
        else:
            if _is_ajax(request):
                return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        # If scheme info passed via query params, prefill and show selected scheme
        scheme_id = request.GET.get('scheme_id')
        scheme_name = request.GET.get('scheme_name')
        scheme_image = request.GET.get('image')
        amount = request.GET.get('amount')
        if amount:
            try:
                initial_amount = str(float(amount))
            except Exception:
                pass
        if scheme_id or scheme_name or scheme_image:
            selected_scheme = {'id': scheme_id, 'name': scheme_name, 'amount': amount, 'image': scheme_image}
            # store temporarily in session so it persists across POST if JS navigation occurs
            request.session['selected_scheme'] = selected_scheme

    context = {
        'form_data': form_data,
        'initial_amount': initial_amount,
    }
    # attach selected scheme from session if available (prefer query params over session)
    if 'selected_scheme' in request.session:
        context['selected_scheme'] = request.session.get('selected_scheme')

    # Resolve scheme image (use absolute/https if provided, otherwise use static helper)
    scheme_image_url = None
    selected = context.get('selected_scheme')
    if selected and selected.get('image'):
        img = selected.get('image')
        try:
            if isinstance(img, str) and (img.startswith('http://') or img.startswith('https://') or img.startswith('/')):
                scheme_image_url = img
            else:
                scheme_image_url = static_url(img)
        except Exception:
            scheme_image_url = None

    if not scheme_image_url:
        scheme_image_url = '/static/donation_app/images/s1.svg'

    context['scheme_image'] = scheme_image_url
    return render(request, 'ACHdonation.html', context)


def payment_view(request):
    donation_data = request.session.get('donation_data')
    order = request.session.get('razorpay_order')
    if not donation_data or not order:
        return redirect(reverse('donation_form'))

    # Reconstruct name for template compatibility
    first_name = donation_data.get('first_name', '')
    middle_name = donation_data.get('middle_name', '')
    last_name = donation_data.get('last_name', '')
    donation_data['name'] = ' '.join(filter(None, [first_name, middle_name, last_name]))

    key_id, _ = _get_razorpay_credentials()
    context = {
        'donation': donation_data,
        'order': json.dumps(order),
        'key_id': key_id or 'mock_key',
    }
    return render(request, 'ACHpayment.html', context)


@require_POST
def payment_verify(request):
    import logging
    import traceback
    logger = logging.getLogger('heart_charity.views.payment_verify')

    payload = request.POST
    razorpay_payment_id = payload.get('razorpay_payment_id')
    razorpay_order_id = payload.get('razorpay_order_id')
    razorpay_signature = payload.get('razorpay_signature')
    is_mock = payload.get('is_mock') == 'true'

    logger.info("payment_verify view triggered. is_mock=%s, razorpay_payment_id=%s, razorpay_order_id=%s", is_mock, razorpay_payment_id, razorpay_order_id)

    donation_data = request.session.get('donation_data')
    order = request.session.get('razorpay_order')
    
    logger.info("Session retrieval check: donation_data is %s, razorpay_order is %s", "present" if donation_data else "absent", "present" if order else "absent")

    if not donation_data or not order:
        logger.error("Session expired or missing required payment/donation details in session.")
        return JsonResponse({'success': False, 'error': 'Session expired.', 'redirect_url': reverse('payment_failed')}, status=400)

    key_id, key_secret = _get_razorpay_credentials()

    if not is_mock and key_id and key_secret:
        client = razorpay.Client(auth=(key_id, key_secret))
        # Verify signature
        try:
            params_dict = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            }
            logger.info("Verifying signature via Razorpay Client API...")
            client.utility.verify_payment_signature(params_dict)
            logger.info("Razorpay payment signature verified successfully.")
        except Exception as e:
            logger.error("Razorpay signature verification failed! Traceback:\n%s", traceback.format_exc())
            request.session.pop('donation_data', None)
            request.session.pop('razorpay_order', None)
            return JsonResponse({'success': False, 'redirect_url': reverse('payment_failed')})
    else:
        logger.info("Using mock/local verification flow.")
        razorpay_payment_id = f"mock_payment_{uuid.uuid4().hex[:10]}"

    # Save donation: create or find DonorVolunteer, then create Donation using new model fields
    try:
        # Extract donor info from session-stored donation_data
        first_name = donation_data.get('first_name', '') or None
        middle_name = donation_data.get('middle_name', '') or None
        last_name = donation_data.get('last_name', '') or None

        email = donation_data.get('email')
        mobile = donation_data.get('mobile_number')

        # Normalize and try to find existing donor by email (case-insensitive) or mobile
        email_norm = email.strip().lower() if isinstance(email, str) and email.strip() else None
        mobile_norm = mobile.strip() if isinstance(mobile, str) and mobile.strip() else None

        logger.info("Preparing to save donation. Email: %s, Mobile: %s", email_norm, mobile_norm)

        donor = None
        try:
            if email_norm:
                logger.info("Searching for existing donor by email: %s", email_norm)
                donor = DonorVolunteer.objects.filter(email__iexact=email_norm).first()
            if not donor and mobile_norm:
                logger.info("Searching for existing donor by mobile: %s", mobile_norm)
                donor = DonorVolunteer.objects.filter(contact_number=mobile_norm).first()

            if not donor:
                # Attempt to create; handle possible race-condition duplicate insert
                try:
                    logger.info("No matching donor found. Creating new DonorVolunteer...")
                    donor = DonorVolunteer.objects.create(
                        first_name=first_name or None,
                        middle_name=middle_name or None,
                        last_name=last_name or None,
                        email=email_norm or None,
                        contact_number=mobile_norm or None,
                        address=donation_data.get('address') or None,
                        area=donation_data.get('area') or None,
                        city=donation_data.get('city') or None,
                        state=donation_data.get('state') or None,
                        country=donation_data.get('country') or None,
                        postal_code=donation_data.get('postal_code') or None,
                        native_place=donation_data.get('native_place') or None,
                        pan_number=donation_data.get('pan_number') or None,
                    )
                    logger.info("New DonorVolunteer created successfully with ID: %s", donor.id)
                except IntegrityError as e:
                    logger.warning("IntegrityError encountered (race condition during donor creation). Retrying lookup. Details: %s", e)
                    # Another process may have created the donor concurrently; fetch existing
                    donor = None
                    if email_norm:
                        donor = DonorVolunteer.objects.filter(email__iexact=email_norm).first()
                    if not donor and mobile_norm:
                        donor = DonorVolunteer.objects.filter(contact_number=mobile_norm).first()
                    if not donor:
                        raise e
            else:
                logger.info("Existing donor found with ID: %s", donor.id)
        except Exception as e:
            logger.error("Exception occurred during donor search/creation: %s. Traceback:\n%s", e, traceback.format_exc())
            donor = None

        if donor:
            try:
                updated = False
                new_pan = (donation_data.get('pan_number') or '').strip()
                if new_pan and getattr(donor, 'pan_number', None) != new_pan:
                    donor.pan_number = new_pan
                    updated = True
                
                if first_name and not getattr(donor, 'first_name', None):
                    donor.first_name = first_name
                    updated = True
                if middle_name and not getattr(donor, 'middle_name', None):
                    donor.middle_name = middle_name
                    updated = True
                if last_name and not getattr(donor, 'last_name', None):
                    donor.last_name = last_name
                    updated = True

                for field in ['address', 'area', 'city', 'state', 'country', 'postal_code', 'native_place']:
                    val = donation_data.get(field) or None
                    if val and not getattr(donor, field, None):
                        setattr(donor, field, val)
                        updated = True
                
                if email_norm and getattr(donor, 'email', None) != email_norm:
                    if not DonorVolunteer.objects.filter(email__iexact=email_norm).exists():
                        donor.email = email_norm
                        updated = True

                if updated:
                    logger.info("Updating fields for DonorVolunteer ID: %s", donor.id)
                    donor.save()
            except Exception as e:
                logger.error("Swallowed exception during DonorVolunteer update/save: %s. Traceback:\n%s", e, traceback.format_exc())

        # Compose donation fields
        declared_amount = donation_data.get('donation_amount')
        try:
            declared_amount_decimal = None
            if declared_amount is not None:
                declared_amount_decimal = float(declared_amount)
        except Exception as e:
            logger.error("Failed to parse declared_amount: %s. Exception: %s", declared_amount, e)
            declared_amount_decimal = None

        # Build description including scheme info if present
        description_parts = []
        if donation_data.get('scheme_name'):
            description_parts.append(f"Scheme: {donation_data.get('scheme_name')}")
        if donation_data.get('reference'):
            description_parts.append(f"Reference: {donation_data.get('reference')}")
        description = '\n'.join(description_parts) if description_parts else donation_data.get('description')

        # Determine numeric IDs for category/method/status if available; avoid writing strings into *_id columns
        def safe_int(val):
            try:
                return int(val)
            except Exception:
                return None

        # Resolve the "Schemes" Category lookup under the "Donation Category" lookup type
        donation_category_id = None
        try:
            category_type = LookupType.objects.filter(type_name__iexact="Donation Category").first()
            if category_type:
                schemes_cat_lookup, _ = Lookup.objects.get_or_create(
                    lookup_name="Schemes",
                    lookup_type=category_type
                )
                donation_category_id = schemes_cat_lookup.id
        except Exception as e:
            logger.error("Error resolving Donation Category: %s. Traceback:\n%s", e, traceback.format_exc())

        scheme_id = donation_data.get('scheme_id')
        s_mapping = {
            's1': 12,
            's2': 13,
            's3': 14,
            's4': 15,
            's5': 16,
            's6': 17,
            's7': 18,
            's8': 19,
        }
        if scheme_id in s_mapping:
            donation_sub_category_id = s_mapping[scheme_id]
        else:
            donation_sub_category_id = safe_int(scheme_id)
        
        # Ensure Razorpay is saved as the payment method lookup
        payment_method_id = None
        payment_method_lookup_type = LookupType.objects.filter(type_name__iexact="Payment Method").first()
        if payment_method_lookup_type:
            razorpay_lookup, created = Lookup.objects.get_or_create(
                lookup_name="Razorpay",
                lookup_type=payment_method_lookup_type,
                defaults={'created_by': (request.user if request.user and request.user.is_authenticated else None)}
            )
            payment_method_id = razorpay_lookup.id
        
        if not payment_method_id:
            payment_method_id = safe_int(donation_data.get('payment_method'))

        # For payment_status, prefer to leave None; set to an integer only if provided numerically
        payment_status_id = safe_int(donation_data.get('payment_status'))

        # Extract UTM values from session if present
        utm_params = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_id']
        utm_values = [request.session.get(param) for param in utm_params if request.session.get(param)]
        
        place_of_donation = None
        if utm_values:
            # Construct comma-separated string of the UTM values
            place_of_donation = ", ".join(utm_values)
            
            # If UTM parameters are present and payment is successful, set payment status to Successful
            try:
                status_type = LookupType.objects.filter(type_name__iexact="Payment Status").first()
                if status_type:
                    payment_status_lookup, _ = Lookup.objects.get_or_create(
                        lookup_name="Successful",
                        lookup_type=status_type
                    )
                    payment_status_id = payment_status_lookup.id
            except Exception as e:
                logger.error("Failed to resolve 'Successful' payment status lookup: %s", e)

        # Reconstruct display name from first, middle, last name fields
        display_name = ' '.join(filter(None, [first_name, middle_name, last_name])) or None
        
        logger.info("Creating Donation record in database...")
        # Create Donation record (fields map to existing DB columns)
        donation = Donation.objects.create(
            donor=donor,
            display_name=display_name,
            donation_date=timezone.now(),
            donation_category_id=donation_category_id,
            donation_sub_category_id=donation_sub_category_id,
            payment_method_id=payment_method_id,
            payment_status_id=payment_status_id,
            transaction_id=razorpay_payment_id,
            receipt_id=generate_ach_receipt_id(),
            place_of_donation=place_of_donation,
            check_no=None,
            donation_received_by=None,
            reference_name=donation_data.get('reference') or None,
            description=description or None,
            donation_amount_declared=declared_amount_decimal,
            donation_amount_paid=declared_amount_decimal,
            name_of_bank=None,
            branch=None,
            created_by=(request.user if request.user and request.user.is_authenticated else None),
            updated_by=(request.user if request.user and request.user.is_authenticated else None),
            verified=True,
        )
        logger.info("Donation record created successfully. ID: %s, Receipt ID: %s", donation.id, donation.receipt_id)

        if email_norm:
            try:
                from io import BytesIO
                from django.core.mail import EmailMultiAlternatives
                from django.template.loader import render_to_string
                from xhtml2pdf import pisa
                from django.conf import settings

                logger.info("Starting email receipt sending process. Recipient: %s", email_norm)

                # Use relative static URLs and pass link_callback to resolve them locally
                logo_url = settings.STATIC_URL + "images/alogo.png"
                signature_url = settings.STATIC_URL + "images/signature.png"
                facebook_icon = settings.STATIC_URL + "images/facebook.png"
                instagram_icon = settings.STATIC_URL + "images/instagram.png"
                youtube_icon = settings.STATIC_URL + "images/youtube.png"
                globe_icon = settings.STATIC_URL + "images/globe.png"

                # HTML for email body
                logger.info("Rendering HTML template 'donation_receipt.html'...")
                html_content = render_to_string(
                    "donation_receipt.html",
                    {
                        "donation": donation,
                        "donor_name": display_name,
                        "amount": declared_amount_decimal,
                        "transaction_id": razorpay_payment_id,
                        "logo_url": logo_url,
                        "signature_url": signature_url,
                        "facebook_icon": facebook_icon,
                        "instagram_icon": instagram_icon,
                        "youtube_icon": youtube_icon,
                        "globe_icon": globe_icon,
                        "preview": False,
                    },
                )
                logger.info("HTML template rendered successfully. size: %d chars", len(html_content))

                logger.info("Initializing EmailMultiAlternatives object...")
                email = EmailMultiAlternatives(
                    subject="Payment Successful - Ahinsadham",
                    body="Thank you for your donation. Your donation receipt is attached with this email.",
                    from_email=settings.EMAIL_HOST_USER,
                    to=[email_norm],
                )

                # Validate required variables
                if not email.to or not email.to[0]:
                    logger.warning("Warning: Recipient list is empty or invalid.")
                if not email.from_email:
                    logger.warning("Warning: from_email is not set/empty.")
                if not settings.EMAIL_HOST_USER:
                    logger.warning("Warning: settings.EMAIL_HOST_USER is not configured.")

                pdf_buffer = BytesIO()

                logger.info("Generating PDF via xhtml2pdf CreatePDF...")
                result = pisa.CreatePDF(
                    html_content,
                    dest=pdf_buffer,
                    link_callback=link_callback,
                )
                logger.info("PDF Generation call complete. result.err: %s", result.err)

                if result.err:
                    logger.error("PDF Generation error: %s", result.err)
                    print("PDF Generation Error")
                    return

                pdf_buffer.seek(0)
                pdf_data = pdf_buffer.read()
                logger.info("PDF buffer size generated: %d bytes", len(pdf_data))

                # Attach PDF
                attachment_name = f"Donation_Receipt_{donation.receipt_id or donation.id}.pdf"
                email.attach(
                    attachment_name,
                    pdf_data,
                    "application/pdf",
                )
                logger.info("Receipt PDF successfully attached as: %s", attachment_name)

                logger.info("Calling email.send()...")
                sent_count = email.send()
                logger.info("email.send() call complete. Result code (sent count): %s", sent_count)

            except Exception as e:
                logger.error("Failed to generate PDF or send email! Exception: %s. Traceback:\n%s", e, traceback.format_exc())
                print("Email Error:", e)
        else:
            logger.warning("Skipping email receipt sending because recipient email_norm is empty/None.")

    except Exception as e:
        logger.critical("Critical database save or processing failure in payment_verify view! Exception: %s. Traceback:\n%s", e, traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error_msg': 'Unable to save the donation.',
            'redirect_url': reverse('payment_failed')
        }, status=500)

    # Clear session
    request.session.pop('donation_data', None)
    request.session.pop('razorpay_order', None)
    request.session.pop('selected_scheme', None)
    
    # Clear UTM parameters from session on successful payment completion
    for param in ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_id']:
        request.session.pop(param, None)

    logger.info("payment_verify view successfully finished. Session cleared. Redirecting to success page.")

    return JsonResponse({'success': True, 'redirect_url': reverse('payment_success')})


def payment_success(request):
    return render(request, 'ACHdonation.html', {'payment_result': 'success'})


def payment_failed(request):
    return render(request, 'ACHdonation.html', {'payment_result': 'failed'})


from heart_charity.models import Lookup

def schemes_view(request):

    foundation_scheme = Lookup.objects.filter(id=12).first()
    icu_scheme = Lookup.objects.filter(id=13).first()
    sanctuary_scheme = Lookup.objects.filter(id=14).first()
    medical_scheme = Lookup.objects.filter(id=15).first()
    special_day_scheme = Lookup.objects.filter(id=16).first()
    fresh_grass_scheme = Lookup.objects.filter(id=17).first()
    adopt_cow_scheme = Lookup.objects.filter(id=18).first()
    plant_tree_scheme = Lookup.objects.filter(id=19).first()

    schemes = [
        {
            'id': foundation_scheme.id if foundation_scheme else 12,
            'name': foundation_scheme.lookup_name if foundation_scheme else 'FOUNDATION PILLAR SUPPORT',
            'amount': 500000,
            'amount_display': '500,000',
            'image': 'images/FOUNDATION.png',
            'slider_image': 'images/slider/foundation_pillar_support.jpg',
            'description': 'Become a pillar of compassion—your name will stand tall on our Donor Wall, honoring your lasting impact on rescued lives.'
        },
        {
            'id': icu_scheme.id if icu_scheme else 13,
            'name': icu_scheme.lookup_name if icu_scheme else 'ICU ANIMAL CARE - ONE MONTH',
            'amount': 351000,
            'amount_display': '351,000',
            'image': 'images/ICU_ANIMAL_CARE.png',
            'slider_image': 'images/slider/icu_animal_care_one_month.jpg',
            'description': 'We provide nutritious diets and therapies to ICU animals-your support speeds up their healing and recovery.'
        },
        {
            'id': sanctuary_scheme.id if sanctuary_scheme else 14,
            'name': sanctuary_scheme.lookup_name if sanctuary_scheme else 'SANCTUARY ABHYARANYA SUPPORT',
            'amount': 108000,
            'amount_display': '108,000',
            'image': 'images/SANCTUARY_ABHYARANYA.png',
            'slider_image': 'images/slider/sanctuary_support.jpg',
            'description': "Join our Rs. 10 lakh tree plantation mission - your donation nurtures the sanctuary's soul and shelters every life within."
        },
        {
            'id': medical_scheme.id if medical_scheme else 15,
            'name': medical_scheme.lookup_name if medical_scheme else 'MEDICAL AID - ONE MONTH',
            'amount': 108000,
            'amount_display': '108,000',
            'image': 'images/MEDICAL_AID.png',
            'slider_image': 'images/slider/medical_aid_one_month.jpg',
            'description': 'Support life-saving medicines, emergency kits, injections, and creams for animals and birds in need.'
        },
        {
            'id': special_day_scheme.id if special_day_scheme else 16,
            'name': special_day_scheme.lookup_name if special_day_scheme else 'SPECIAL DAY TRIBUTE (KAYMITITHI)',
            'amount': 54000,
            'amount_display': '54,000',
            'image': 'images/SPECIAL_DAY.png',
            'slider_image': 'images/slider/special_tribute.jpg',
            'description': 'Celebrate a birthday, anniversary, or memorial-your tribute will be displayed annually on our premise.'
        },
        {
            'id': fresh_grass_scheme.id if fresh_grass_scheme else 17,
            'name': fresh_grass_scheme.lookup_name if fresh_grass_scheme else 'ONE TRUCK OF FRESH GRASS',
            'amount': 27000,
            'amount_display': '27,000',
            'image': 'images/ONE_TRUCK.png',
            'slider_image': 'images/slider/1_truck_of_fresh_grass.jpg',
            'description': 'One truck full of grass can feed hundreds of rescued animals - sponsor their next meal today.'
        },
        {
            'id': adopt_cow_scheme.id if adopt_cow_scheme else 18,
            'name': adopt_cow_scheme.lookup_name if adopt_cow_scheme else 'ADOPT A COW - 1 YEAR',
            'amount': 12000,
            'amount_display': '12,000',
            'image': 'images/ADOPTCOW.png',
            'slider_image': 'images/slider/adopt_a_cow.jpg',
            'description': 'Adopt a divine soul - Support monthly cow care-food, checkups, and vaccinations that ensure her comfort and wellbeing.'
        },
        {
            'id': plant_tree_scheme.id if plant_tree_scheme else 19,
            'name': plant_tree_scheme.lookup_name if plant_tree_scheme else 'PLANT A TREE',
            'amount': 2700,
            'amount_display': '2,700',
            'image': 'images/PLANT.png',
            'slider_image': 'images/slider/plant_a_tree.jpg',
            'description': 'Plant a tree to expand our green habitat-your gift creates shade, shelter, and serenity for all life.'
        },
    ]

    return render(request, 'ACHschemas.html', {'schemes': schemes})

from django.http import JsonResponse
from django.db.models import Q

def donor_autocomplete_ajax(request):
    q = request.GET.get('q', '').strip()
    person_type = request.GET.get('person_type', '').strip()
    
    donors = DonorVolunteer.objects.filter(is_deleted=False)
    if person_type == 'donor':
        donors = donors.filter(person_type__lookup_name__icontains='donor')
    elif person_type == 'Employee':
        donors = donors.filter(person_type__lookup_name__iexact="Employee")
        
    if q:
        donors = donors.filter(
            Q(first_name__icontains=q) | 
            Q(last_name__icontains=q) |
            Q(contact_number__icontains=q) |
            Q(pan_number__icontains=q)
        )
    
    results = []
    for d in donors.only('id', 'first_name', 'last_name', 'pan_number')[:30]:
        pan_suffix = f" - {d.pan_number}" if d.pan_number else ""
        results.append({
            "id": d.id,
            "text": f"{d.first_name} {d.last_name}{pan_suffix}"
        })
    return JsonResponse({"results": results})
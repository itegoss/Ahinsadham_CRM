from django.shortcuts import render
from django.forms import ValidationError
from django.contrib.auth.decorators import login_required
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth import authenticate, login, logout
import random
from django.shortcuts import render, redirect
from django.contrib.auth import login
from .models import DonationBox, DonationPaymentBox, User 
from heart_charity.models import LookupType   # ⬅️ ADD THIS


# Create your views here.
def home(req):
    return render(req,'home.html')

from django.contrib.auth import authenticate, login

def signin_view(request):
    try:
        # Replace 'defaultuser' with the actual username of your single user
        user = User.objects.get(username="username")
        login(request, user)
        return redirect('welcome')  # redirect to welcome page
    except User.DoesNotExist:
        # Show an error page if the user does not exist
        return render(request, 'signin.html', {"errmsg": """"""})


def check_module_access(request,user_id):
    user = get_object_or_404(User, id=user_id)

    modules = Module.objects.all()  # fetch all records
    # print("Modules fetched:", modules)  # ✅ Debug line
    allowed_modules = UserModuleAccess.objects.filter(
        user=user,
        can_access=True
    ).select_related('module').values_list('module__module_name', flat=True)

    return render(request, 'welcome.html', { 'user': user,'allowed_modules':list(allowed_modules),'modules': modules})


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import UserModuleAccess, Module
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Module, UserModuleAccess, UserRole

def access_control(request):

    modules = Module.objects.all()
    mode = request.GET.get("mode", "add")
    role_id = request.GET.get("role_id")
    role_instance = None
    if mode == "edit" and role_id:
        role_instance = UserModuleAccess.objects.filter(id=role_id).first()
    if request.method == "POST":
        role_name = request.POST.get("role_name").strip()
        role_description = request.POST.get("roleDescription").strip()
        if mode == "edit" and role_instance:
            UserModuleAccess.objects.filter(name=role_instance.name).delete()
        selected_modules = request.POST.getlist("modules")
        for module_id in selected_modules:
            module = get_object_or_404(Module, id=module_id)

            UserModuleAccess.objects.create(
                module=module,
                name=role_name,
                description=role_description,
                can_access=True,
                can_add=f"permissions_{module_id}_add" in request.POST,
                can_edit=f"permissions_{module_id}_edit" in request.POST,
                can_delete=f"permissions_{module_id}_delete" in request.POST,
                can_view=f"permissions_{module_id}_view" in request.POST,
                created_by=request.user,
                updated_by=request.user,
            )

        messages.success(request, "Role & permissions saved successfully!")
        return redirect("welcome")
    context = {
        "modules": modules,
        "mode": mode,
        "role_instance": role_instance,
    }

    return render(request, "access_control.html", context)

# User = get_user_model()
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils.timezone import now
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import User, UserRole, UserModuleAccess, DonationOwner, DonorVolunteer, Donation

from django.shortcuts import render
from .models import LookupType, Lookup

def show_lookup_data(request):
    lookup_types = LookupType.objects.filter(is_deleted=False)
    lookups = Lookup.objects.select_related("lookup_type").filter(is_deleted=False).order_by("id")

    return render(request, "lookup_display.html", {
        "lookup_types": lookup_types,
        "lookups": lookups
    })
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils.timezone import now
from .models import (
    User, DonorVolunteer, Donation, DonationOwner,
    UserModuleAccess, UserRole, LookupType, Lookup, Module
)
from .helpers import get_user_permissions
@login_required
def welcome_view(request):
    user = request.user
    # ------------------------------------------------------------
    # FETCH PERMISSIONS  (NEW)
    # ------------------------------------------------------------
    permissions = get_user_permissions(user)
    if user.is_superuser:
            class SuperPerm:
                can_add = True
                can_edit = True
                can_delete = True
                can_view = True
                can_access = True
            permissions = SuperPerm()

    # ------------------------------------------------------------
    # FETCH DATA
    # ------------------------------------------------------------
    users = User.objects.all().order_by('id')
    donation_owners = DonationOwner.objects.all()
    roles_qs = UserModuleAccess.objects.all().order_by("name").distinct()
    clean_roles = [role.name.replace("—", "").replace("–", "").strip() for role in roles_qs]

    donations = Donation.objects.all().select_related('donor')
    donors = DonorVolunteer.objects.all()

    lookup_types = LookupType.objects.all().order_by("id")
    lookups = Lookup.objects.select_related("lookup_type").order_by("id")
    donation_boxes = DonationBox.objects.all()
    donation_payment = DonationPaymentBox.objects.all().select_related("owner", "donation_box")
    # Pagination
    page_obj = Paginator(donors, 1).get_page(request.GET.get('donor_page'))
    donation_page_obj = Paginator(donations, 1).get_page(request.GET.get('donation_page'))
    user_page_obj = Paginator(users, 1).get_page(request.GET.get('user_page'))
    roles_page_obj = Paginator(roles_qs, 10).get_page(request.GET.get('roles_page'))
    lookup_page_obj = Paginator(lookup_types, 1).get_page(request.GET.get("lt_page"))
    lookup_table_obj = Paginator(lookups, 1).get_page(request.GET.get("lu_page"))
    payments_page_obj = Paginator(donation_payment, 1).get_page(request.GET.get("payments_page"))
    box_page_obj = Paginator(donation_boxes, 1).get_page(request.GET.get("box_page"))
    # ------------------------------------------------------------
    # ASSIGN ROLE TO USER (ADMIN ONLY)
    # ------------------------------------------------------------
    if request.method == "POST" and "save_user_role" in request.POST:
        user_id = request.POST.get("user_id")
        role_name = request.POST.get("role")

        if not user_id or not role_name:
            messages.error(request, "❌ Please select both user and role.")
            return redirect("welcome")

        selected_user = get_object_or_404(User, id=user_id)

        # Save previous superuser status
        previous_super_state = selected_user.is_superuser

        selected_role = UserModuleAccess.objects.filter(name=role_name).first()
        if not selected_role:
            messages.error(request, "❌ Invalid role selected.")
            return redirect("welcome")

        user_role, created = UserRole.objects.get_or_create(user=selected_user)
        user_role.role = selected_role
        user_role.save()

        # Prevent accidental superuser change
        if selected_user.is_superuser != previous_super_state:
            selected_user.is_superuser = previous_super_state
            selected_user.save(update_fields=["is_superuser"])

        messages.success(
            request,
            f"✅ Role '{role_name}' has been assigned to {selected_user.username}."
        )
        return redirect("welcome")

    # Unique role names
    role_names = roles_qs.values_list("name", flat=True).distinct()

    # ------------------------------------------------------------
    # CONTEXT (COMMON)
    # ------------------------------------------------------------
    context = {
        'user': user,
        'username': user.username,
        'first_name': user.first_name,
        'donation_payment':donation_payment,
        'permissions': permissions,   # <-- NEW LINE

        'donation_owners': donation_owners,
        'roles_qs': roles_qs,
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
    }

    # ------------------------------------------------------------
    # ACCESS CONTROL
    # ------------------------------------------------------------
    if user.is_superuser:
        all_modules = Module.objects.all().values_list('module_name', flat=True)
        context['allowed_modules'] = list(all_modules)

    else:
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

    return render(request, 'welcome.html', context)


def validate_password(password):
    # Check minimum length
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long.")

    # Check maximum length
    if len(password) > 128:
        raise ValidationError("Password cannot exceed 128 characters.")

    # Initialize flags for character checks
    has_upper = False
    has_lower = False
    has_digit = False
    has_special = False
    special_characters = "@$!%*?&"

    # Check for character variety
    for char in password:
        if char.isupper():
            has_upper = True
        elif char.islower():
            has_lower = True
        elif char.isdigit():
            has_digit = True
        elif char in special_characters:
            has_special = True

    if not has_upper:
        raise ValidationError("Password must contain at least one uppercase letter.")
    if not has_lower:
        raise ValidationError("Password must contain at least one lowercase letter.")
    if not has_digit:
        raise ValidationError("Password must contain at least one digit.")
    if not has_special:
        raise ValidationError(
            "Password must contain at least one special character (e.g., @$!%*?&)."
        )

    # Check against common passwords
    common_passwords = [
        "password",
        "123456",
        "qwerty",
        "abc123",
    ]  # Add more common passwords
    if password in common_passwords:
        raise ValidationError("This password is too common. Please choose another one.")

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
import random
from django.core.mail import send_mail
def request_password_reset(req):
    if req.method == "GET":
        return render(req, "request_password_reset.html")
    else:
        uname = req.POST.get("uname")
        context = {}
        try:
            userdata = User.objects.get(username=uname)
            return redirect("reset_password", uname=userdata.username)

        except User.DoesNotExist:
            context["errmsg"] = "No account found with this username"
            return render(req, "request_password_reset.html",context)

def reset_password(req, uname):
    userdata = User.objects.get(username=uname)
    if req.method == "GET":
        return render(req, "reset_password.html", {"user": userdata.username})
    else:
        upass = req.POST["upass"]
        ucpass = req.POST["ucpass"]
        context = {}
        userdata = User.objects.get(username=uname)
        try:
            if upass == "" or ucpass == "":
                context["errmsg"] = "Field can't be empty"
                return render(req, "reset_password.html", context)
            elif upass != ucpass:
                context["errmsg"] = "Password and confirm password need to match"
                return render(req, "reset_password.html", context)
            else:
                # validate_password(upass)
                userdata.set_password(upass)
                userdata.save()
                return redirect("signin")

        except ValidationError as e:
            context["errmsg"] = str(e)
            return render(req, "reset_password.html", context)

def logout_view(req):
    logout(req)
    return redirect("home")

def admin_dashboard(request):
    users = []
    donations = []
    
    if request.method == "POST":
     
        try:
            users = User.objects.all()
        except NameError:
             users = []
             
        try:
            donations = Donate.objects.all()
        except NameError:
             donations = []

    context = {
        "users": users,
        "donations": donations
    }
    
    return render(request, "admin_dashboard.html", context)

def user_dashboard(req):
    causes = Cause.objects.all()
    return render(req, 'user_dashboard.html', {"causes": causes})  
otp_storage = {}

def send_otp(request):
    if request.method == "POST":
        phone = request.POST.get("phone")
        otp = str(random.randint(100000, 999999))
        otp_storage[phone] = otp

        # Here you send SMS via API (example: Twilio)
        print(f"OTP for {phone}: {otp}")  # For testing only

        # Redirect to OTP verification page
        return redirect(f"/verify-otp/?phone={phone}")
    return redirect('signin')  # fallback if GET

from django.contrib.auth import login
from .models import User
from twilio.rest import Client

# Twilio credentials
TWILIO_ACCOUNT_SID = 'AC730c5a6779806941ef6ef4215f92629a'
TWILIO_AUTH_TOKEN = '8ab4ce8083246cb7fc38dccacc5a521b'
TWILIO_PHONE = '+917208542366'  # Twilio number

def send_otp(request):
    if request.method == "POST":
        phone = request.POST.get("phone")
        otp = str(random.randint(100000, 999999))
        otp_storage[phone] = otp

        # Send SMS using Twilio
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=f"Your OTP is {otp}",
            from_=TWILIO_PHONE,
            to=f"+91{phone}"  # or include country code
        )

        return redirect(f"/verify-otp/?phone={phone}")
    return redirect('signin')

# ------------Globle All Search-------------------

from django.db.models import Q

import csv
from django.http import HttpResponse
from django.db.models import Q
from django.core.paginator import Paginator
def search_lookup_type(request):
    lookup_query = request.GET.get('lookup_query', '').strip()
    active_tab = request.GET.get('active_tab', 'mdm')  # keep active tab info

    lookup_types = LookupType.objects.all().order_by('id')

    # 🔍 UPDATED SEARCH FILTER (Full Field Search)
    if lookup_query:
        filters = (
            Q(type_name__icontains=lookup_query) |
            Q(created_by__username__icontains=lookup_query) |
            Q(updated_by__username__icontains=lookup_query) |
            Q(created_date__icontains=lookup_query) |
            Q(updated_date__icontains=lookup_query) |
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
        writer.writerow(['ID', 'Type Name', 'Created By', 'Created Date','Updated By','Updated Date','Deleted At','Is Deleted'])

        for lookup in lookup_types:
            writer.writerow([lookup.id, lookup.type_name, lookup.created_by, lookup.created_date,lookup.updated_by,lookup.updated_date,lookup.deleted_at,lookup.is_deleted])

        return response

    # ✅ Pagination
    paginator = Paginator(lookup_types, 1)
    page_number = request.GET.get("lt_page")
    lookup_types_page = paginator.get_page(page_number)

    return render(request, "welcome.html", {
        "lookup_page_obj": lookup_types_page,
        "lookup_query": lookup_query,
        "active_tab": active_tab,
    })


def search_lookup_table(request):
    sub_lookup_query = request.GET.get('sub_lookup_query', '').strip()
    active_tab = request.GET.get('active_tab', 'mdm')

    lookups = Lookup.objects.select_related("lookup_type").all().order_by('id')

    # 🔍 UPDATED FULL SEARCH FILTER
    if sub_lookup_query:

        # Month mapping for searching "Dec", "December", etc.
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
            Q(created_date__icontains=sub_lookup_query) |
            Q(updated_date__icontains=sub_lookup_query) |
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
                Q(created_date__month=month) |
                Q(updated_date__month=month) |
                Q(deleted_at__month=month)
            )

        lookups = lookups.filter(filters)

    # 🟢 DOWNLOAD CSV (same style & naming like search_lookup_type)
    if request.GET.get('download') == '1':
        filename = f"lookup_table_{sub_lookup_query or 'all'}.csv"
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(["ID", "Lookup Name", "Lookup Type", "Created By", "Created Date", "Updated By", "Updated Date", "Deleted At", "Is Deleted"])

        for l in lookups:
            writer.writerow([
                l.id,
                l.lookup_name,
                l.lookup_type.type_name if l.lookup_type else "",
                l.created_by.username if l.created_by else "",
                l.created_date,
                l.updated_by.username if l.updated_by else "",
                l.updated_date,
                l.deleted_at,
                l.is_deleted,
            ])

        return response

    # 📄 Pagination — 1 record per page (same style)
    paginator = Paginator(lookups, 1)
    lookup_table_obj = paginator.get_page(request.GET.get("lookup_table_page"))

    return render(request, "welcome.html", {
        "lookup_table_obj": lookup_table_obj,
        "sub_lookup_query": sub_lookup_query,
        "active_tab": active_tab,
    })

from .models import User, Module, UserModuleAccess
from django.db.models import Q
from django.shortcuts import render
from django.core.paginator import Paginator
from django.contrib.auth.models import User
from django.db.models import Q
from .models import UserModuleAccess  # if you need roles

def search_users(request):
    query = request.GET.get("user_query", "")
    active_tab = request.GET.get("active_tab", "user")
    download = request.GET.get("download")

    users = User.objects.all().order_by("id")

    # 🔍 Apply search ONLY if query exists
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

    # 🟩 Pagination
    paginator = Paginator(users, 1)
    page = request.GET.get("user_page")
    user_page_obj = paginator.get_page(page)

    return render(request, "welcome.html", {
        "user_page_obj": user_page_obj,
        "user_query": query,
        "active_tab": active_tab,
    })

from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Q
from django.core.paginator import Paginator
from .models import UserModuleAccess
import csv

def search_roles(request):
    query1 = request.GET.get('query1', '').strip()

    active_tab = "roles"

    roles = UserModuleAccess.objects.all().order_by('id')

    # 🔍 UPDATED FULL SEARCH LOGIC (Everything else unchanged)
    if query1:

        # Month name search support
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
            Q(created_date__icontains=query1) |
            Q(updated_date__icontains=query1) |
            Q(deleted_at__icontains=query1)
        )

        # Numeric search → ID / module ID
        if query1.isdigit():
            filters |= (
                Q(id=int(query1)) |
                Q(module_id=int(query1))
            )

        # Boolean fields: can_access, can_add, etc.
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

        # Month name search ("Dec", "January", etc.)
        if qlow in month_map:
            month_num = month_map[qlow]
            filters |= (
                Q(created_date__month=month_num) |
                Q(updated_date__month=month_num) |
                Q(deleted_at__month=month_num)
            )

        roles = roles.filter(filters)

    # Download CSV
    if request.GET.get('download') == '1':

        filename = f"roles_{query1 or 'all'}.csv"

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(['Role', 'Description', 'Can Access', 'Can Add', 'Can Edit', 'Can Delete', 'Can View', 'Created By', 'Created Date', 'Updated By', 'Updated Date', 'Deleted At', 'Is Deleted'])

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
                role.created_date,
                role.updated_by,
                role.updated_date,
                role.deleted_at,
                role.is_deleted,
            ])

        return response

    # Pagination
    role_paginator = Paginator(roles, 10)
    page_number = request.GET.get('roles_page')
    roles_page_obj = role_paginator.get_page(page_number)

    # Keep search value for pagination
    roles_page_obj.query = query1

    return render(request, 'welcome.html', {
        'roles_page_obj': roles_page_obj,
        'query1': query1,
        'active_tab': active_tab,
    })


from .models import LookupType
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import UserRole, UserModuleAccess

def manage_user_roles(request):
    users = User.objects.all()
    roles = UserModuleAccess.objects.select_related('role', 'module').all()
    user_roles = {ur.user.id: ur for ur in UserRole.objects.select_related('role', 'role__role')}

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

from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from .models import UserModuleAccess, UserRole
def assign_role(request):
    users = User.objects.all()

    # Fetch UNIQUE role names only
    roles = UserModuleAccess.objects.values_list('name', flat=True).distinct()

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

from django.shortcuts import render
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.db.models import Q
from .models import DonorVolunteer
import csv

from datetime import datetime, date

def search_donor_volunteer(request):
    donorvolunteer = DonorVolunteer.objects.select_related(
        "person_type", "id_type", "donor_box",
        "created_by", "updated_by"
    ).all()

    query2 = request.GET.get('q')
    if query2:
        query2 = query2.strip()
        if query2 != "":

            # ---- Month mapping ----
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

            # base text filters
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

                # donor box
                Q(donor_box__donation_id__icontains=query2) |
                Q(donor_box__key_id__icontains=query2) |
                Q(donor_box__location__icontains=query2) |

                # address
                Q(house_number__icontains=query2) |
                Q(building_name__icontains=query2) |
                Q(landmark__icontains=query2) |
                Q(area__icontains=query2) |
                Q(city__icontains=query2) |
                Q(state__icontains=query2) |
                Q(country__icontains=query2) |
                Q(postal_code__icontains=query2) |
                Q(native_place__icontains=query2) |
                Q(native_postal_code__icontains=query2) |

                # ID / PAN
                Q(id_type__lookup_name__icontains=query2) |
                Q(id_number__icontains=query2) |
                Q(pan_number__icontains=query2) |

                # user fields
                Q(created_by__username__icontains=query2) |
                Q(updated_by__username__icontains=query2)
            )

            # numeric search (id, age)
            if query2.isdigit():
                try:
                    num = int(query2)
                    filters |= (
                        Q(id=num) |
                        Q(age=num)
                    )
                except ValueError:
                    pass

            # boolean search: true/false/yes/no/active/inactive
            truthy = {"true", "yes", "active", "1"}
            falsy = {"false", "no", "inactive", "0"}
            if qlow in truthy or qlow in falsy:
                # map meaning: "active"/"true"/"yes" -> is_deleted = False
                if qlow in truthy:
                    filters |= Q(is_deleted=False)
                else:
                    filters |= Q(is_deleted=True)

            # month name search (Dec, December, etc.)
            if qlow in month_map:
                month_num = month_map[qlow]
                filters |= (
                    Q(date_of_birth__month=month_num) |
                    Q(created_at__month=month_num) |
                    Q(updated_at__month=month_num) |
                    Q(deleted_at__month=month_num)
                )

            # year/day/time search attempts: if query looks like year or dd-mm-yyyy or yyyy-mm-dd
            # try YYYY or DD-MM-YYYY or YYYY-MM-DD
            try:
                if len(query2) == 4 and query2.isdigit():
                    # year only
                    y = int(query2)
                    filters |= (
                        Q(date_of_birth__year=y) |
                        Q(created_at__year=y) |
                        Q(updated_at__year=y) |
                        Q(deleted_at__year=y)
                    )
                # try common date formats
                for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                    try:
                        parsed = datetime.strptime(query2, fmt).date()
                        filters |= (
                            Q(date_of_birth=parsed) |
                            Q(created_at__date=parsed) |
                            Q(updated_at__date=parsed) |
                            Q(deleted_at__date=parsed)
                        )
                        break
                    except Exception:
                        pass
            except Exception:
                pass

            # apply filters and make results distinct & ordered
            donorvolunteer = donorvolunteer.filter(filters).distinct().order_by("id")

    # ---- DOWNLOAD CSV ----
    if request.GET.get('download') == '1':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="donor_volunteer.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Person Type', 'First Name', 'Middle Name', 'Last Name', 
            'Gender', 'DOB', 'Email', 'Contact Number','Blood Group','WhatsApp Number','Donor Box', 'House Number', 'Building Name',
            'Landmark', 'Area', 'City', 'State', 'Country','Postal Code', 'Native Place', 'Native Postal Code', 'ID Type', 'ID Number', 
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
                dv.house_number,
                dv.building_name,
                dv.landmark,
                dv.area,
                dv.city,
                dv.state,
                dv.country,
                dv.postal_code,
                dv.native_place,
                dv.native_postal_code,
                dv.id_type.lookup_name if dv.id_type else '',
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

    paginator = Paginator(donorvolunteer, 1)
    page_obj = paginator.get_page(request.GET.get('donor_page'))

    return render(request, "welcome.html", {
        "page_obj": page_obj,
        "query2": query2 if query2 else "",
    })

from django.http import HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q, Value
from django.db.models.functions import Concat
import csv
from .models import Donation
def search_donation(request):
    donations = Donation.objects.all()
    query3 = request.GET.get('q', '').strip()

    if query3:
        # Annotate full_name
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
            'Donor Name',
            'Donation Date',
            'Amount Declared',
            'Amount Paid',
            'Category',
            'Payment Method',
            'Transaction ID',
            'Status',
            'created_by',
            'updated_by',
            'created_at',
            'updated_at',
            'deleted_at',
            'is_deleted',

            'Receipt No.'
        ])

        for d in donations:
            donor_name = f"{d.donor.first_name} {d.donor.last_name}" if d.donor else ""
            writer.writerow([
                donor_name,
                d.donation_date,
                d.donation_amount_declared,
                d.donation_amount_paid,
                d.donation_category.lookup_name if d.donation_category else "",
                d.payment_method.lookup_name if d.payment_method else "",
                d.transaction_id,
                d.payment_status.lookup_name if d.payment_status else "",
                d.created_by.username if d.created_by else '',
                d.updated_by.username if d.updated_by else '',
                d.created_at,
                d.updated_at,
                d.deleted_at,
                d.is_deleted,
                d.receipt_id
            ])
        return response

    # ---- PAGINATION ----
    paginator = Paginator(donations, 1)
    donation_page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'welcome.html', {
        'donation_page_obj': donation_page_obj,
        'query3': query3,
    })



from django.http import HttpResponse
from django.db.models import Q
from django.core.paginator import Paginator
import csv

@login_required
def search_donation_payment(request):

    payments_query = request.GET.get("payments_query", "").strip()

    payments = DonationPaymentBox.objects.filter(is_deleted=False)

    # ----------------------------------------------------
    # 🔍 UPDATED SEARCH FILTER — ALL FIELDS SEARCHABLE
    # ----------------------------------------------------
    if payments_query:
        q = payments_query.lower()

        # Month name mapping
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

            # 🔹 Donation Box fields
            Q(donation_box__donation_id__icontains=payments_query) |
            Q(donation_box__key_id__icontains=payments_query) |
            Q(donation_box__location__icontains=payments_query) |
            Q(donation_box__box_size__icontains=payments_query) |
            Q(donation_box__status__icontains=payments_query) |

            # 🔹 Regular fields
            Q(opened_by__icontains=payments_query) |
            Q(received_by__icontains=payments_query) |
            Q(address__icontains=payments_query) |
            Q(i_witness__icontains=payments_query) |

            # 🔹 Lookup (payment method)
            Q(payment_method__lookup_name__icontains=payments_query) |

            # 🔹 Users
            Q(owner__username__icontains=payments_query) |
            Q(created_by__username__icontains=payments_query) |
            Q(updated_by__username__icontains=payments_query)
        )

        # Numeric search → amount or ID
        if payments_query.replace('.', '', 1).isdigit():
            filters |= (
                Q(amount__icontains=payments_query) |
                Q(id=int(float(payments_query)))
            )

        # Boolean search
        active_values = {"true", "yes", "active", "1"}
        inactive_values = {"false", "no", "inactive", "0"}

        if q in active_values:
            filters |= Q(is_deleted=False)
        elif q in inactive_values:
            filters |= Q(is_deleted=True)

        # Year search (e.g., "2025")
        if len(payments_query) == 4 and payments_query.isdigit():
            y = int(payments_query)
            filters |= (
                Q(date_time__year=y) |
                Q(created_at__year=y) |
                Q(updated_at__year=y) |
                Q(deleted_at__year=y)
            )

        # Month search (Dec, December)
        if q in month_map:
            m = month_map[q]
            filters |= (
                Q(date_time__month=m) |
                Q(created_at__month=m) |
                Q(updated_at__month=m) |
                Q(deleted_at__month=m)
            )

        # Full-date search
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
    # ----------------------------------------------------
    # 🔍 END ADVANCED SEARCH
    # ----------------------------------------------------

    # CSV download
    if request.GET.get("download") == "1":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="donation_payments.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "Donation Box",
            "Donation ID",
            "Owner",
            "Opened By",
            "Received By",
            "Amount",
            "Payment Method",
            "Address",
            "Witness",
            "Created By",
            "Created At",
            "Updated By",
            "Updated At",
            "Deleted At",
            "Is Deleted",

        ])

        for p in payments:
            writer.writerow([
                p.donation_box.donation_id if p.donation_box else "",
                f"{p.owner.first_name} {p.owner.last_name}" if p.owner else "",
                p.opened_by,
                p.received_by,
                p.amount,
                p.payment_method.lookup_name if p.payment_method else "",
                p.address,
                p.i_witness,
                p.created_by.username if p.created_by else "",
                p.created_at,
                p.updated_by.username if p.updated_by else "",
                p.updated_at,
                p.deleted_at,
                p.is_deleted,
            ])

        return response

    # Pagination (correct)
    paginator = Paginator(payments, 1)
    page_number = request.GET.get("payments_page")
    payments_page_obj = paginator.get_page(page_number)

    return render(request, "welcome.html", {
        "payments_page_obj": payments_page_obj,
        "payments_query": payments_query,
    })


@login_required
def search_donation_box(request):

    box_query = request.GET.get("box_query", "").strip()
    boxes = DonationBox.objects.filter(is_deleted=False).order_by("id")

    # ----------------------------------------------------
    # 🔍 UPDATED ADVANCED SEARCH LOGIC (Full-field search)
    # ----------------------------------------------------
    if box_query:
        qlow = box_query.lower()

        # Month map
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

        # Base fields
        filters = (
            Q(donation_id__icontains=box_query) |
            Q(location__icontains=box_query) |
            Q(key_id__icontains=box_query) |
            Q(box_size__icontains=box_query) |
            Q(status__icontains=box_query) |
            Q(uploaded_by__username__icontains=box_query) |
            Q(created_by__username__icontains=box_query)
        )

        # Numeric search
        if box_query.isdigit():
            filters |= Q(id=int(box_query))

        # Boolean search
        truthy = {"true", "yes", "active", "1"}
        falsy = {"false", "no", "inactive", "0"}

        if qlow in truthy:
            filters |= Q(is_deleted=False)
        elif qlow in falsy:
            filters |= Q(is_deleted=True)

        # Year search
        if len(box_query) == 4 and box_query.isdigit():
            y = int(box_query)
            filters |= (
                Q(created_at__year=y) |
                Q(updated_at__year=y) |
                Q(deleted_at__year=y)
            )

        # Month search (Dec, December)
        if qlow in month_map:
            m = month_map[qlow]
            filters |= (
                Q(created_at__month=m) |
                Q(updated_at__month=m) |
                Q(deleted_at__month=m)
            )

        # Full date search (DD-MM-YYYY, YYYY-MM-DD)
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
    # ----------------------------------------------------
    # 🔍 END UPDATED LOGIC
    # ----------------------------------------------------

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
            "Location",
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
                b.location,
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

    # ---------------------------------------
    # 📄 PAGINATION
    # ---------------------------------------
    paginator = Paginator(boxes, 1)
    page_number = request.GET.get("box_page")
    box_page_obj = paginator.get_page(page_number)

    # ---------------------------------------
    # 🔁 RENDER PAGE
    # ---------------------------------------
    return render(request, "welcome.html", {
        "box_page_obj": box_page_obj,
        "box_query": box_query,
    })

#----------------Globle End Search--------------
# -----------------Local search------------------------
@login_required
def search_id(request):
    query = request.GET.get('search')
    users = User.objects.all()
    active_tab = 'user'  # 👈 is tab ka id/data-tab HTML me hona chahiye

    if query:
        try:
            users = User.objects.filter(id=int(query))
        except ValueError:
            users = []

    return render(request, 'welcome.html', {
        'users': users,
        'query': query,
        'active_tab': active_tab
    })




@login_required
def searchfirstname(request):
    query = request.GET.get('search')
    users = User.objects.all()
    active_tab = 'user'  # 👈 tab ka id ya data-tab name

    if query:
        # search by first_name (case-insensitive)
        users = User.objects.filter(first_name__icontains=query)

    return render(request, 'welcome.html', {
        'users': users,
        'query': query,
        'active_tab': active_tab
    })





def searchlastname(request):
    query = request.GET.get('search', '').strip()
    users = []

    if query:
        users = User.objects.filter(last_name__icontains=query)

    context = {
        'users': users,
        'query': query,
        'active_tab': 'user',  # stays on "User" tab
    }
    return render(request, 'welcome.html', context)





def searchemail(request):
    query = request.GET.get('search', '').strip()
    users = []

    if query:
        users = User.objects.filter(email__icontains=query)

    context = {
        'users': users,
        'query': query,
        'active_tab': 'user',  # stay on User tab
    }
    return render(request, 'welcome.html', context)






def searchisstaff(request):
    query = request.GET.get('search', '').strip().lower()
    users = []

    if query:
        # Accept "true", "false", "yes", "no", "1", "0"
        if query in ['true', 'yes', '1']:
            users = User.objects.filter(is_staff=True)
        elif query in ['false', 'no', '0']:
            users = User.objects.filter(is_staff=False)

    context = {
        'users': users,
        'query': query,
        'active_tab': 'user',  # stay on User tab
    }
    return render(request, 'welcome.html', context)




def searchactive(request):
    query = request.GET.get('search', '').strip().lower()
    users = []

    if query:
        # Accept multiple keywords for active/inactive
        if query in ['active', 'true', 'yes', '1']:
            users = User.objects.filter(is_active=True)
        elif query in ['inactive', 'false', 'no', '0']:
            users = User.objects.filter(is_active=False)

    context = {
        'users': users,
        'query': query,
        'active_tab': 'user',  # stay on User tab
    }
    return render(request, 'welcome.html', context)




def searchsuperuser(request):
    query = request.GET.get('search', '').strip().lower()
    users = []

    if query:
        # Accept multiple keywords for True/False
        if query in ['true', 'yes', '1', 'superuser']:
            users = User.objects.filter(is_superuser=True)
        elif query in ['false', 'no', '0', 'normal']:
            users = User.objects.filter(is_superuser=False)

    context = {
        'users': users,
        'query': query,
        'active_tab': 'user',  # stay on User tab
    }
    return render(request, 'welcome.html', context)






def search_lastlogin(request):
    query = request.GET.get('search', '').strip().lower()
    users = []

    if query:
        matched_users = []
        for user in User.objects.all():
            if user.last_login:
                # Format example: "Nov. 6, 2025, 10:24 a.m."
                formatted = user.last_login.strftime("%b. %d, %Y, %#I:%M %p").lower()
                clean_formatted = formatted.replace(',', '').replace('.', '')

                # Split date and time
                parts = clean_formatted.split()
                # Example: ['nov', '6', '2025', '1024', 'am']

                date_part = " ".join(parts[:3])   # nov 6 2025
                time_part = " ".join(parts[3:])   # 1024 am

                # Determine if query looks like a time
                looks_like_time = any(x in query for x in [':', 'am', 'pm'])

                if looks_like_time:
                    # Search only in time part
                    if query.replace('.', '') in time_part:
                        matched_users.append(user)
                else:
                    # Search only in date part
                    if query in date_part:
                        matched_users.append(user)

        users = matched_users

    context = {
        'users': users,
        'query': query,
        'active_tab': 'user',
    }
    return render(request, 'welcome.html', context)





def searchdate(request):
    query = request.GET.get('search', '').strip().lower()
    users = []

    if query:
        matched_users = []
        for user in User.objects.all():
            if user.last_login:
                # Format like "Nov. 6, 2025, 10:24 a.m."
                formatted = user.last_login.strftime("%b. %d, %Y, %#I:%M %p").lower()
                clean_formatted = formatted.replace(',', '').replace('.', '')

                # Extract only date part (month, day, year)
                parts = clean_formatted.split()
                date_part = " ".join(parts[:3])  # e.g. "nov 6 2025"

                # ✅ Match only date part
                if query in date_part:
                    matched_users.append(user)

        users = matched_users

    context = {
        'users': users,
        'query': query,
        'active_tab': 'user',  # ✅ redirect to User tab
    }
    return render(request, 'welcome.html', context)
# ----------------------local search ends---------------

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q
from heart_charity.models import LookupType, Lookup, DonorVolunteer, UserModuleAccess, Module
from django.core.files.storage import default_storage
from django.shortcuts import render, redirect, get_object_or_404

def add_donor_volunteer(request):
    # Get Lookup options
    person_type_options = Lookup.objects.filter(
        lookup_type__type_name__iexact='Person Type'
    )
    id_type_options = Lookup.objects.filter(
        lookup_type__type_name__iexact='ID Type'
    )

    # Fetch Donation Boxes (so you can see box IDs)
    donation_boxes = DonationBox.objects.filter(is_deleted=False).order_by('donation_id')

    # Get Donor-Box-Owner ID for template JS toggle safely
    donor_box_owner = Lookup.objects.filter(lookup_name='Donor-Box-Owner').first()
    donor_box_owner_id = donor_box_owner.id if donor_box_owner else None

    if request.method == 'POST':
        # Get Person Type instance
        person_type_id = request.POST.get('person_type')
        person_type_instance = Lookup.objects.get(id=person_type_id) if person_type_id else None

        # File uploads
        id_proof_image = request.FILES.get('id_proof_image')
        pan_card_image = request.FILES.get('pan_card_image')

        donor = DonorVolunteer.objects.create(
            person_type=person_type_instance,
            first_name=request.POST.get('first_name'),
            middle_name=request.POST.get('middle_name'),
            last_name=request.POST.get('last_name'),
            gender=request.POST.get('gender'),
            date_of_birth=request.POST.get('date_of_birth'),
            age=request.POST.get('age') or None,
            blood_group=request.POST.get('blood_group'),
            contact_number=request.POST.get('contact_number'),
            whatsapp_number=request.POST.get('whatsapp_number'),
            email=request.POST.get('email'),

            # Assign box ONLY if person type = Donor-Box-Owner
            donor_box_id=request.POST.get('donor_box') if (
                person_type_instance and person_type_instance.lookup_name == 'Donor-Box-Owner'
            ) else None,

            house_number=request.POST.get('house_number'),
            building_name=request.POST.get('building_name'),
            landmark=request.POST.get('landmark'),
            area=request.POST.get('area'),
            city=request.POST.get('city'),
            state=request.POST.get('state'),
            country=request.POST.get('country'),
            postal_code=request.POST.get('postal_code'),
            native_place=request.POST.get('native_place'),
            native_postal_code=request.POST.get('native_postal_code'),
            id_number=request.POST.get('id_number'),
            pan_number=request.POST.get('pan_number'),
        )

        # Save attachments
        if id_proof_image:
            donor.id_proof_image.save(id_proof_image.name, id_proof_image)
        if pan_card_image:
            donor.pan_card_image.save(pan_card_image.name, pan_card_image)

        return redirect('welcome')

    context = {
        'person_type_options': person_type_options,
        'id_type_options': id_type_options,
        'donor_box_owner_id': donor_box_owner_id,
        'donation_boxes': donation_boxes,  # <-- IMPORTANT LINE
    }

    return render(request, 'add_donor_volunteer.html', context)


def donor_success(request):
    return render(request, "donor_success.html") 


from django.contrib.auth.models import User
from django.utils import timezone

from django.utils.timezone import now
from django.db import IntegrityError, transaction

def adddonation(request):
    donors = DonorVolunteer.objects.all()
    today = now().date()

    donation_categories = Lookup.objects.filter(
        lookup_type__type_name__iexact="Donation Category"
    ).order_by("lookup_name")

    payment_methods = Lookup.objects.filter(
        lookup_type__type_name__iexact="Payment Method"
    ).order_by("lookup_name")

    payment_statuses = Lookup.objects.filter(
        lookup_type__type_name__iexact="Payment Status"
    ).order_by("lookup_name")

    if request.method == "POST":
        try:
            Donation.objects.create(
                donor_id=request.POST.get("donor"),
                donation_amount_declared=request.POST.get("donation_amount_declared") or 0,
                donation_amount_paid=request.POST.get("donation_amount_paid") or 0,
                donation_date=request.POST.get("donation_date"),
                donation_category_id=request.POST.get("donation_category"),
                payment_method_id=request.POST.get("payment_method"),
                payment_status_id=request.POST.get("payment_status"),
                place_of_donation=request.POST.get("place_of_donation"),
                check_no=request.POST.get("check_no"),
                donation_received_by=request.POST.get("donation_received_by"),
                reference_name=request.POST.get("reference_name"),
                description=request.POST.get("description"),
                transaction_id=request.POST.get("transaction_id"),
                created_by=request.user
            )

            messages.success(request, "Donation added successfully!")
            return redirect("adddonation")

        except IntegrityError:
            messages.error(request, "Duplicate value or invalid data. Please check your inputs.")

        except DatabaseError:
            messages.error(request, "Database error occurred! Try again later.")

        except Exception as e:
            messages.error(request, f"Unexpected error: {str(e)}")

    return render(request, "adddonation.html", {
        "donors": donors,
        "donation_categories": donation_categories,
        "payment_methods": payment_methods,
        "payment_statuses": payment_statuses,
        "today": today
    })

def donation_list(request):
    donations = Donation.objects.all().select_related('donor')
    return render(request, 'donation-list.html', {'donations': donations})




from xhtml2pdf import pisa
from django.template.loader import render_to_string
from .models import Donation
from django.http import HttpResponse
from xhtml2pdf import pisa

def donation_receipt(request, id):
    donation = Donation.objects.get(id=id)
    return render(request, "donation_receipt.html", {"donation": donation})

def generate_receipt_pdf(request, id):
    donation = Donation.objects.get(id=id)
    html = render_to_string("donation_receipt_pdf.html", {"donation": donation})

    response = HttpResponse(content_type="application/pdf")
    response['Content-Disposition'] = f'attachment; filename="Receipt_{donation.receipt_id}.pdf"'

    pisa.CreatePDF(html, dest=response)
    return response


from datetime import date, timedelta
from .models import DonorVolunteer
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

def download_donor_report(request):
    # Get 'days' from query parameter
    days = request.GET.get('days')
    donors = []
    label = ""

    if days:
        days = int(days)
        start_date = date.today() - timedelta(days=days)
        donors = DonorVolunteer.objects.filter(created_at__date__gte=start_date)
        label = f"Last {days} Days"

        # Create PDF response
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="donor_report_{days}_days.pdf"'

        p = canvas.Canvas(response, pagesize=A4)
        width, height = A4

        # Header
        p.setFont("Helvetica-Bold", 16)
        p.drawString(180, height - 50, f"Donor Report - {label}")

        # Table Header
        p.setFont("Helvetica-Bold", 12)
        y = height - 100
        p.drawString(50, y, "Name")
        p.drawString(250, y, "Person Type")
        p.drawString(400, y, "City")
        y -= 20

        # Table Data
        p.setFont("Helvetica", 11)
        for donor in donors:
            full_name = f"{donor.first_name} {donor.last_name}"
            
            p.drawString(50, y, full_name)
            p.drawString(250, y, donor.person_type)
            p.drawString(400, y, donor.city)
            y -= 20

            if y < 50:  # Start new page if needed
                p.showPage()
                p.setFont("Helvetica", 11)
                y = height - 50

        p.showPage()
        p.save()
        return response

    return render(request, 'download_donor_report.html')



# views.py
from django.shortcuts import render, get_object_or_404, redirect

def user_list(request):
    users = User.objects.filter(userprofile__is_deleted=False)  # only show active users
    return render(request, 'user_list.html', {'users': users})


from .models import Donation, DonorVolunteer

def donation_receipt_view(request, donor_id):
    donor = get_object_or_404(DonorVolunteer, id=donor_id)
    donations = Donation.objects.filter(donor__id=donor_id)
    return render(request, 'donation_receipt.html', {
        'donor': donor,
        'donations': donations
    })


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import DonationPaymentBox, DonationBox, Lookup, User, DonorVolunteer
import json
from django.core.serializers.json import DjangoJSONEncoder

@login_required
def add_donation_payment(request):

    donation_boxes = DonationBox.objects.filter(is_deleted=False)

    # Fetch payment methods
    payment_methods = Lookup.objects.filter(
        lookup_type__type_name__iexact="Payment Method"
    ).order_by("lookup_name")

    # ----- SIMPLE SOLUTION -----
    # Get donor-volunteer linked to donation box
    box_owner_map = []

    donors = DonorVolunteer.objects.filter(is_deleted=False)

    for d in donors:
        if d.donor_box:   # only if donor is assigned a box
            address = ", ".join(filter(None, [
                d.house_number, d.building_name, d.area, d.city, d.state, d.postal_code
            ]))

            box_owner_map.append({
                "box_id": d.donor_box.id,
                "owner_name": f"{d.first_name} {d.last_name}",
                "address": address,
            })

    if request.method == "POST":
        donation_box_id = request.POST.get("donation_box")
        owner_name = request.POST.get("owner_name")  # from autofilled field
        address = request.POST.get("address")
        opened_by = request.POST.get("opened_by")
        received_by = request.POST.get("received_by")
        amount = request.POST.get("amount")
        payment_method_id = request.POST.get("payment_method")
        date_time = request.POST.get("date_time")
        i_witness = request.POST.get("i_witness")

        payment_method = get_object_or_404(Lookup, id=payment_method_id)
        donation_box = get_object_or_404(DonationBox, id=donation_box_id)

        DonationPaymentBox.objects.create(
            owner=request.user,        # SIMPLE: payment owner = logged-in user
            donation_box=donation_box,
            address=address,
            opened_by=opened_by,
            received_by=received_by,
            amount=amount,
            payment_method=payment_method,
            date_time=date_time,
            i_witness=i_witness,
            created_by=request.user,
            updated_by=request.user,
        )

        messages.success(request, "Donation Payment Added Successfully!")
        return redirect("welcome")

    context = {
        "donation_boxes": donation_boxes,
        "payment_methods": payment_methods,
        "box_owner_map": json.dumps(box_owner_map, cls=DjangoJSONEncoder),
        "current_time": timezone.now(),
    }

    return render(request, "add_donationbox_payment.html", context)


from .models import DonationBox
from django.contrib.auth.decorators import login_required

@login_required
def add_donation_box(request):

    if request.method == "POST":

        key_id = request.POST.get("key_id")
        box_size = request.POST.get("box_size")     # small / medium / large
        location = request.POST.get("location")
        status = request.POST.get("status")
        qr_code = request.FILES.get("qr_code")      # optional

        # Create Donation Box object
        box = DonationBox(
            key_id=key_id,
            box_size=box_size,
            location=location,
            status=status,
            qr_code=qr_code if qr_code else None,
            uploaded_by=request.user,
            created_by=request.user,
            created_at=timezone.now(),
        )

        box.save()  # Auto-generates donation_id + QR if missing

        messages.success(request, "Donation Box Added Successfully!")
        return redirect("welcome")   # Change if needed

    context = {
        "status_choices": DonationBox.status_choices,
    }
    return render(request, "add_donation_box.html", context)

from .models import Employee

def add_employee(request):
    if request.method == "POST":
        try:
            # 🧩 Collect form data
            Employee.objects.create(
                first_name=request.POST.get('firstName'),
                middle_name=request.POST.get('middleName'),
                last_name=request.POST.get('lastName'),
                email=request.POST.get('email'),
                phone=request.POST.get('phone'),
                address=request.POST.get('address'),
                city=request.POST.get('city'),
                state=request.POST.get('state'),
                postal_code=request.POST.get('postalCode'),
                department=request.POST.get('department'),
                designation=request.POST.get('designation'),
                employee_type=request.POST.get('employeeType'),
                joining_date=request.POST.get('joiningDate'),
                bank_name=request.POST.get('bankName'),
                account_number=request.POST.get('accountNumber'),
                ifsc_code=request.POST.get('ifscCode'),
                account_type=request.POST.get('accountType'),
            )

            messages.success(request, "✅ Employee added successfully!")
            return redirect('employee-list')  # Redirect to your employee list view

        except Exception as e:
            messages.error(request, f"❌ Error: {e}")
            return redirect('add-employee')

    return render(request, 'welcome.html')  # Your form page template


def all_donations(request):
    q = request.GET.get('q', '').strip()
    donations = Donation.objects.all()

    if q:
        donations = donations.filter(
            Q(donor__first_name__icontains=q) |
            Q(donor__last_name__icontains=q) |
            Q(donation_category__icontains=q) |
            Q(donation_mode__icontains=q) |
            Q(payment_method__icontains=q) |
            Q(transaction_id__icontains=q)
        ).distinct()

    # If no results found
    message = None
    if q and not donations.exists():
        message = f'No matching records found for "{q}".'

    return render(request, 'donation-list.html', {
        'donations': donations,
        'query': q,
        'message': message
    })



def donationbox_list(request):
    query = request.GET.get('q', '')
    donation_boxes = DonationBox.objects.all()

    if query:
        donation_boxes = donation_boxes.filter(
            Q(donation_box_name__icontains=query) |
            Q(donation_id__icontains=query) |
            Q(location__icontains=query)
        )

    return render(request, 'show_donationbox.html', {'donation_boxes': donation_boxes})

# -------------------Filtered and Download data------------------------

from django.http import HttpResponse
from django.db.models import Q
from django.shortcuts import redirect
from .models import Donation

def download_filtered_donations(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    search = request.GET.get('search', '').strip()

    # ✅ Prevent download if all fields are empty
    if not start_date and not end_date and not search:
        messages.warning(request, "⚠️ Please enter a date range or search term before downloading.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    donations = Donation.objects.all()

    # ✅ Filter by date range
    if start_date and end_date:
        donations = donations.filter(donation_date__range=[start_date, end_date])
    elif start_date:
        donations = donations.filter(donation_date__gte=start_date)
    elif end_date:
        donations = donations.filter(donation_date__lte=end_date)

    # ✅ Apply search filter (search across multiple fields)
    if search:
        donations = donations.filter(
            Q(donor__first_name__icontains=search) |
            Q(donor__last_name__icontains=search) |
            Q(transaction_id__icontains=search) |
            Q(donation_category__icontains=search) |
            Q(donation_mode__icontains=search) |
            Q(payment_method__icontains=search)
        )

    # ✅ Sort by latest first
    donations = donations.order_by('-donation_date')

    # ✅ If no results found after filtering
    if not donations.exists():
        messages.warning(request, "⚠️ No data found for the given filters.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    # ✅ Create Excel workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Filtered Donations"
    headers = ['Donor Name', 'Amount', 'Date', 'Category', 'Mode', 'Payment Method', 'Transaction ID', 'Status']
    sheet.append(headers)

    for donation in donations:
        donor_name = str(donation.donor) if donation.donor else "N/A"
        sheet.append([
            donor_name,
            donation.donation_amount,
            donation.donation_date.strftime('%Y-%m-%d') if donation.donation_date else '',
            donation.donation_category,
            donation.donation_mode,
            donation.payment_method,
            donation.transaction_id,
            donation.payment_status
        ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="filtered_donations.xlsx"'
    workbook.save(response)
    return response

from django.contrib.auth.models import User
from django.http import HttpResponse
from datetime import datetime

def download_filtered_users(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    search = request.GET.get('search', '').strip()

    # ✅ Prevent download if all filters are empty
    if not start_date and not end_date and not search:
        messages.warning(request, "⚠️ Please enter a date range or search term before downloading.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    # ✅ Start with all users
    users = User.objects.all()

    # ✅ Filter by date range (using date_joined)
    if start_date and end_date:
        users = users.filter(date_joined__range=[start_date, end_date])
    elif start_date:
        users = users.filter(date_joined__gte=start_date)
    elif end_date:
        users = users.filter(date_joined__lte=end_date)

    # ✅ Search filter (search by username, first name, last name, or email)
    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )

    # ✅ Order by latest joined users
    users = users.order_by('-date_joined')

    # ✅ If no results found
    if not users.exists():
        messages.warning(request, "⚠️ No users found for the given filters.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    # ✅ Create Excel workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Filtered Users"

    # ✅ Headers
    headers = ['Username', 'First Name', 'Last Name', 'Email', 'Date Joined', 'Last Login', 'Is Staff', 'Is Active']
    sheet.append(headers)

    # ✅ Add user data
    for user in users:
        sheet.append([
            user.username,
            user.first_name,
            user.last_name,
            user.email,
            user.date_joined.strftime('%Y-%m-%d %H:%M') if user.date_joined else '',
            user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else '',
            'Yes' if user.is_staff else 'No',
            'Active' if user.is_active else 'Inactive'
        ])

    # ✅ Prepare response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="filtered_users.xlsx"'
    workbook.save(response)
    return response


from django.shortcuts import redirect
from django.http import HttpResponse
from .models import UserModuleAccess  # Make sure this import is correct

def download_filtered_user_access(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    search = request.GET.get('search', '').strip()

    # ✅ Prevent download if all filters are empty
    if not start_date and not end_date and not search:
        messages.warning(request, "⚠️ Please enter a date range or search term before downloading.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    # ✅ Start with all user access data
    accesses = UserModuleAccess.objects.all()

    # ✅ Filter by date range (if created_at exists)
    if hasattr(UserModuleAccess, 'created_at'):
        if start_date and end_date:
            accesses = accesses.filter(created_at__range=[start_date, end_date])
        elif start_date:
            accesses = accesses.filter(created_at__gte=start_date)
        elif end_date:
            accesses = accesses.filter(created_at__lte=end_date)

    # ✅ Apply search filter
    if search:
        accesses = accesses.filter(
            Q(module__name__icontains=search) |
            Q(role__icontains=search) |
            Q(description__icontains=search)
        )

    # ✅ Order by latest created
    if hasattr(UserModuleAccess, 'created_at'):
        accesses = accesses.order_by('-created_at')

    # ✅ If no results found
    if not accesses.exists():
        messages.warning(request, "⚠️ No records found for the given filters.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    # ✅ Create Excel workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "User Access Data"

    # ✅ Headers
    headers = [
        'Module Name', 'Role', 'Description',
        'Can Access', 'Can Add', 'Can Edit', 'Can Delete'
    ]
    if hasattr(UserModuleAccess, 'created_at'):
        headers.append('Created At')

    sheet.append(headers)

    # ✅ Add data rows
    for access in accesses:
        row = [
            access.module.name if hasattr(access.module, 'name') else str(access.module),
            access.role or "N/A",
            access.description or "",
            'Yes' if access.can_access else 'No',
            'Yes' if access.can_add else 'No',
            'Yes' if access.can_edit else 'No',
            'Yes' if access.can_delete else 'No',
        ]
        if hasattr(access, 'created_at'):
            row.append(access.created_at.strftime('%Y-%m-%d %H:%M') if access.created_at else '')
        sheet.append(row)

    # ✅ Prepare response for download
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="user_access_data.xlsx"'
    workbook.save(response)
    return response

from django.shortcuts import redirect
from django.db.models import Q
from django.http import HttpResponse
from .models import DonorVolunteer  # ✅ import your model
def download_filtered_donor_volunteers(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    search = request.GET.get('search', '').strip()

    # ✅ Prevent download if all filters are empty
    if not start_date and not end_date and not search:
        messages.warning(request, "⚠️ Please enter a date range or search term before downloading.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    # ✅ Start with all donor/volunteer records
    donors = DonorVolunteer.objects.all()

    # ✅ Filter by date range (use created_at, date_added, or registration_date)
    if hasattr(DonorVolunteer, 'created_at'):
        if start_date and end_date:
            donors = donors.filter(created_at__range=[start_date, end_date])
        elif start_date:
            donors = donors.filter(created_at__gte=start_date)
        elif end_date:
            donors = donors.filter(created_at__lte=end_date)

    # ✅ Apply search filter (search by name, email, phone, type, etc.)
    if search:
        donors = donors.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(person_type__icontains=search)
        )

    # ✅ Order by latest created
    if hasattr(DonorVolunteer, 'created_at'):
        donors = donors.order_by('-created_at')

    # ✅ If no results found
    if not donors.exists():
        messages.warning(request, "⚠️ No records found for the given filters.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    # ✅ Create Excel workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Donor Volunteer Data"

    # ✅ Headers (you can adjust these depending on your model)
    headers = [
        'First Name', 'Last Name', 'Email', 'Phone Number',
        'Person Type', 'Address', 'City', 'State', 'Pincode'
    ]
    if hasattr(DonorVolunteer, 'created_at'):
        headers.append('Created At')

    sheet.append(headers)

    # ✅ Add donor data rows
    for donor in donors:
        row = [
            donor.first_name or '',
            donor.last_name or '',
            donor.email or '',
            donor.person_type or '',
            getattr(donor, 'address', ''),
            getattr(donor, 'city', ''),
            getattr(donor, 'state', ''),
            getattr(donor, 'pincode', ''),
        ]
        if hasattr(donor, 'created_at'):
            row.append(donor.created_at.strftime('%Y-%m-%d %H:%M') if donor.created_at else '')
        sheet.append(row)

    # ✅ Prepare response for download
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="donor_volunteer_data.xlsx"'
    workbook.save(response)
    return response

# -------------------END Filtered and Download data------------------------

from django.shortcuts import render
from .models import UserRole
def user_access_list(request):
    user_roles = UserRole.objects.select_related('user', 'role__module').all()
    return render(request, 'user_access_list.html', {'user_roles': user_roles})


from django.core.paginator import Paginator
from .models import Donation

def donation_list(request):
    donations = Donation.objects.all().order_by('id')  # Or whatever order you want

    # --- Pagination setup ---
    page = request.GET.get('page', 1)  # get current page number
    paginator = Paginator(donations, 1)  # 1 record per page

    donations_page = paginator.get_page(page)

    return render(request, 'donation_list.html', {'donations': donations_page})


from heart_charity.models import LookupType   # ⬅️ ADD THIS

# def lookup_type_create(request):
#     if request.method == "POST":
#         type_name = request.POST.get("type_name").strip()

#         # --- Check if already exists ---
#         if LookupType.objects.filter(type_name__iexact=type_name).exists():
#             messages.error(
#                 request,
#                 f"Lookup Type '{type_name}' already exists. Please enter a different name."
#             )
#             return render(request, "lookup_type_form.html", {
#                 "lookup_type": None
#             })

#         # --- Create new lookup type ---
#         lookup_type = LookupType(
#             type_name=type_name,
#             created_by=request.user,
#             updated_by=request.user,
#         )
#         lookup_type.save()

#         messages.success(request, "Lookup Type added successfully!")
#         return render(request, "lookup_type_form.html", {
#             "lookup_type": None
#         })

#     return render(request, "lookup_type_form.html", {
#         "lookup_type": None
#     })

def lookup_type_create(request):
    if request.method == "POST":
        type_name = request.POST.get("type_name").strip()

        # --- CASE 1: Active record exists → prevent duplicate ---
        if LookupType.objects.filter(type_name__iexact=type_name, is_deleted=False).exists():
            messages.error(
                request,
                f"Lookup Type '{type_name}' already exists!"
            )
            return render(request, "lookup_type_form.html", {"lookup_type": None})

        # --- CASE 2: Soft-deleted record exists → restore it instead of creating new ---
        deleted_record = LookupType.objects.filter(type_name__iexact=type_name, is_deleted=True).first()
        if deleted_record:
            deleted_record.is_deleted = False
            deleted_record.deleted_at = None
            deleted_record.updated_by = request.user
            deleted_record.save()

            messages.success(request, f"Lookup Type '{type_name}' restored successfully!")
            return render(request, "lookup_type_form.html", {"lookup_type": None})

        # --- CASE 3: No record exists → create a new one ---
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
    lookup_types = LookupType.objects.all()

    if request.method == "POST":
        name = request.POST.get("lookup_name")
        type_id = request.POST.get("lookup_type")

        # Check duplicate entry
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
            return redirect("lookup_create")  # Same page redirect

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
from django.shortcuts import render, get_object_or_404, redirect
from .models import LookupType

def edit_lookup_type(request, id):
    lookup_type = get_object_or_404(LookupType, id=id)

    if request.method == "POST":
        lookup_type.type_name = request.POST.get('type_name')
        lookup_type.updated_by = request.user
        lookup_type.save()
        return redirect('lookup_type_list')

    return render(request, "edit_lookup_type.html", {"lookup_type": lookup_type})

from django.shortcuts import render, get_object_or_404, redirect
from .models import Lookup, LookupType

def edit_lookup(request, id):
    lookup = get_object_or_404(Lookup, id=id)
    types = LookupType.objects.all()

    if request.method == "POST":
        lookup.lookup_name = request.POST.get("lookup_name")
        lookup.lookup_type_id = request.POST.get("lookup_type")
        lookup.updated_by = request.user
        lookup.save()
        return redirect("lookup_list")

    return render(request, "edit_lookup.html", {
        "lookup": lookup,
        "types": types
    })

from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.models import User

def edit_user(request, id):
    user_obj = get_object_or_404(User, id=id)

    if request.method == 'POST':
        user_obj.first_name = request.POST.get('first_name')
        user_obj.last_name = request.POST.get('last_name')
        user_obj.username = request.POST.get('username')
        user_obj.email = request.POST.get('email')
        
        user_obj.save()
        return redirect('welcome')

    return render(request, 'edit_user.html', {'edit_user': user_obj})

from django.shortcuts import render, get_object_or_404, redirect
from .models import UserModuleAccess

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
        return redirect("welcome")  # Change to your module list page

    return render(request, "edit_usermoduleaccess.html", {"access": record})

from .models import DonorVolunteer, Lookup
def edit_donor(request, donor_id):
    donor = get_object_or_404(DonorVolunteer, id=donor_id)
    donors = DonorVolunteer.objects.all()
    person_types = Lookup.objects.filter(lookup_type__type_name="Person Type")
    id_types = Lookup.objects.filter(lookup_type__type_name="ID Type")

    if request.method == "POST":
        donor.first_name = request.POST.get("first_name", donor.first_name)
        donor.middle_name = request.POST.get("middle_name", donor.middle_name)
        donor.last_name = request.POST.get("last_name", donor.last_name)
        donor.person_type_id = request.POST.get("person_type", donor.person_type_id)
        donor.id_type_id = request.POST.get("id_type", donor.id_type_id)
        donor.gender = request.POST.get("gender", donor.gender)
        donor.date_of_birth = request.POST.get("date_of_birth", donor.date_of_birth)
        donor.blood_group = request.POST.get("blood_group", donor.blood_group)
        donor.contact_number = request.POST.get("contact_number", donor.contact_number)
        donor.whatsapp_number = request.POST.get("whatsapp_number", donor.whatsapp_number)
        donor.email = request.POST.get("email", donor.email)
        donor.house_number = request.POST.get("house_number", donor.house_number)
        donor.building_name = request.POST.get("building_name", donor.building_name)
        donor.landmark = request.POST.get("landmark", donor.landmark)
        donor.area = request.POST.get("area", donor.area)
        donor.city = request.POST.get("city", donor.city)
        donor.state = request.POST.get("state", donor.state)
        donor.country = request.POST.get("country", donor.country)
        donor.postal_code = request.POST.get("postal_code", donor.postal_code)
        donor.id_number = request.POST.get("id_number", donor.id_number)
        donor.pan_number = request.POST.get("pan_number", donor.pan_number)
        # handle file uploads if needed

        donor.save()
        return redirect("welcome")

    return render(request, "edit_donor.html", {
        "donors": donors,
        "donor": donor,
        "person_types": person_types,
        "id_types": id_types,
        "blood_groups": DonorVolunteer.BLOOD_GROUP_CHOICES,
    })


from .models import Donation, Lookup, DonorVolunteer
from django.contrib.auth.decorators import login_required

from django.db.models import Q

def edit_donation(request, id):
    donation = get_object_or_404(Donation, id=id)

    # Only Donors
    donors = DonorVolunteer.objects.filter(person_type__lookup_name='Donor-Box-Owner')

    donation_categories = Lookup.objects.filter(lookup_type__type_name="Donation Category")
    donation_modes = Lookup.objects.filter(lookup_type__type_name="Donation Mode")
    payment_methods = Lookup.objects.filter(lookup_type__type_name="Payment Method")
    payment_statuses = Lookup.objects.filter(lookup_type__type_name="Payment Status")

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




def edit_box_payment(request, id):
    payment = get_object_or_404(DonationPaymentBox, id=id)

    if request.method == 'POST':
        payment.address = request.POST.get('address')
        payment.amount = request.POST.get('amount')
        payment.i_witness = request.POST.get('i_witness')
        payment.updated_by = request.user
        payment.save()

        messages.success(request, "Payment updated successfully!")
        return redirect('welcome')   # Or your payment list page

    return render(request, 'BoxPayment.html', {
        'payment': payment
    })



# donationbox eidt view------------------------------



def edit_donation_box(request, id):
    box = get_object_or_404(DonationBox, id=id)

    if request.method == 'POST':
        box.key_id = request.POST.get('key_id')
        box.box_size = request.POST.get('box_size')
        box.location = request.POST.get('location')
        box.status = request.POST.get('status')

        # QR Code update
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
    user_to_delete.is_active = False  # deactivate instead of delete
    user_to_delete.save()
    return redirect('welcome')

from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .models import LookupType

@login_required
def delete_lookup_type(request, lookup_type_id):
    if request.method == "POST":
        lookup_type = get_object_or_404(LookupType, id=lookup_type_id)

        lookup_type.is_deleted = True
        lookup_type.deleted_at = timezone.now()
        lookup_type.updated_by = request.user
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
        lookup.save()
        messages.success(request, f"✅ Lookup '{lookup.lookup_name}' deactivated.")
        page = request.GET.get("lu_page", 1)
        return redirect(reverse("welcome") + f"?lu_page={page}")
    return redirect("welcome")


from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse

@login_required
def delete_user_module_access(request, access_id):
    if request.method == "POST":
        access = get_object_or_404(UserModuleAccess, id=access_id)

        # Soft delete fields update
        access.is_deleted = True
        access.deleted_at = timezone.now()
        access.updated_by = request.user
        access.save()

        messages.success(request, f"🗑️ Role '{access.name}' has been deleted successfully.")

        # Preserve pagination page number if exists
        page = request.GET.get("uma_page", 1)
        return redirect(reverse("welcome") + f"?uma_page={page}")

    return redirect("welcome")

from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required


@login_required
def delete_donor_volunteer(request, donor_id):
    if request.method == "POST":
        donor = get_object_or_404(DonorVolunteer, id=donor_id)

        # Soft delete
        donor.is_deleted = True
        donor.deleted_at = timezone.now()
        donor.updated_by = request.user
        donor.save()

        messages.success(request, f"🗑️ '{donor.first_name} {donor.last_name}' has been deleted successfully.")

        # Maintain pagination position
        page = request.GET.get("dv_page", 1)
        return redirect(reverse("welcome") + f"?dv_page={page}")

    return redirect("welcome")


from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone


@login_required
def delete_donation(request, donation_id):
    if request.method == "POST":
        donation = get_object_or_404(Donation, id=donation_id)

        # Soft Delete Logic
        donation.is_deleted = True
        donation.deleted_at = timezone.now()
        donation.updated_by = request.user
        donation.save()

        messages.success(request, f"🗑 Donation receipt '{donation.receipt_id}' deleted successfully.")

        # Keep pagination position
        page = request.GET.get("donation_page", 1)
        return redirect(reverse("welcome") + f"?donation_page={page}")

    return redirect("welcome")



# DONATIONEDELETE VIEW------------------------------


def delete_box_payment(request, id):
    if request.method == "POST":
        payment = get_object_or_404(DonationPaymentBox, id=id)
        
        # If soft delete:
        # payment.is_active = False
        # payment.save()

        # Hard delete:
        payment.delete()

        messages.success(request, "Donation Box Payment deleted successfully!")
        return redirect('welcome')



def delete_donation_box(request, id):
    if request.method == "POST":
        box = get_object_or_404(DonationBox, id=id)
        box.is_active = False    # ⭐ soft delete
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
        return redirect('welcome')   # Or your payment list page

    return render(request, 'BoxPayment.html', {
        'payment': payment
    })



# donationbox eidt view------------------------------



def edit_donation_box(request, id):
    box = get_object_or_404(DonationBox, id=id)

    if request.method == 'POST':
        box.key_id = request.POST.get('key_id')
        box.box_size = request.POST.get('box_size')
        box.location = request.POST.get('location')
        box.status = request.POST.get('status')

        # QR Code update
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



from django.forms import ValidationError
from django.contrib.auth.decorators import login_required
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth import authenticate, login, logout
import random
from django.shortcuts import render, redirect, get_object_or_404
from requests import request
from .models import DonationBox, DonationPaymentBox, User ,Donation
from heart_charity.models import LookupType,Lookup,UserModuleAccess,Module,UserRole,User, DonationOwner, DonorVolunteer
from django.contrib import messages
import csv
from django.http import HttpResponse
import json
from .utils import generate_receipt_id


def home(req):
    return render(req,'home.html')

def signin_view(request):
    try:
        user = User.objects.get(username="username")
        login(request, user)
        return redirect('welcome') 
    except User.DoesNotExist:
        return render(request, 'signin.html', {"errmsg": """"""})

def access_control(request):
    modules = Module.objects.all()
    if request.method == "POST":
        role_name = request.POST.get("role_name")
        role_desc = request.POST.get("roleDescription")
        module_id = request.POST.get("selected_module")
        can_access = bool(request.POST.get("access_permission"))
        can_add = bool(request.POST.get("add_permission"))
        can_edit = bool(request.POST.get("edit_permission"))
        can_delete = bool(request.POST.get("delete_permission"))
        can_view = bool(request.POST.get("view_permission"))
        if not role_name:
            messages.error(request, "Role name is required.")
            return redirect("access_control")
        if not module_id:
            messages.error(request, "Select a module.")
            return redirect("access_control")
        module = Module.objects.get(id=module_id)
        role_obj, created = UserModuleAccess.objects.get_or_create(name=role_name,module=module)
        role_obj.description = role_desc
        role_obj.can_access = can_access
        role_obj.can_add = can_add
        role_obj.can_edit = can_edit
        role_obj.can_delete = can_delete
        role_obj.can_view = can_view
        role_obj.save()
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
from django.core.paginator import Paginator
from .helpers import get_user_permissions
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

    users = User.objects.all().order_by('id')
    donation_owners = DonationOwner.objects.all()
    roles_qss = UserModuleAccess.objects.values_list("name", flat=True)
    clean_roles = sorted(set(roles_qss))
    roles_qs = UserModuleAccess.objects.all()

    donations = Donation.objects.all().select_related('donor')
    donors = DonorVolunteer.objects.all()
    lookup_types = LookupType.objects.all().order_by("id")
    lookups = Lookup.objects.select_related("lookup_type").order_by("id")
    donation_boxes = DonationBox.objects.all()
    donation_payment = DonationPaymentBox.objects.all().select_related("owner", "donation_box")
    # Pagination
    page_obj = Paginator(donors.order_by('id'), 10).get_page(request.GET.get('donor_page'))
    donation_page_obj = Paginator(donations.order_by('id'), 10).get_page(request.GET.get('donation_page'))
    user_page_obj = Paginator(users, 10).get_page(request.GET.get('user_page'))
    roles_page_obj = Paginator(roles_qs, 10).get_page(request.GET.get('roles_page'))
    lookup_page_obj = Paginator(lookup_types, 5).get_page(request.GET.get("lt_page"))
    lookup_table_obj = Paginator(lookups, 5).get_page(request.GET.get("lu_page"))
    payments_page_obj = Paginator(donation_payment.order_by('id'), 5).get_page(request.GET.get("payments_page"))
    box_page_obj = Paginator(donation_boxes.order_by('id'), 5).get_page(request.GET.get("box_page"))
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
    }
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

def search_lookup_type(request):
    lookup_query = request.GET.get('lookup_query', '').strip()
    active_tab = request.GET.get('active_tab', 'mdm')
    lookup_types = LookupType.objects.all().order_by('id')
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
    paginator = Paginator(lookup_types, 5)
    page_number = request.GET.get("lt_page")
    lookup_types_page = paginator.get_page(page_number)
    permissions = get_user_permissions(request.user)

    return render(request, "welcome.html", {
        "lookup_page_obj": lookup_types_page,
        "lookup_query": lookup_query,
        "active_tab": active_tab,
        "permissions":permissions
    })

def search_lookup_table(request):
    sub_lookup_query = request.GET.get('sub_lookup_query', '').strip()
    active_tab = request.GET.get('active_tab', 'mdm')
    lookups = Lookup.objects.select_related("lookup_type").all().order_by('id')
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
    paginator = Paginator(lookups, 5)
    lookup_table_obj = paginator.get_page(request.GET.get("lookup_table_page"))
    permissions = get_user_permissions(request.user)

    return render(request, "welcome.html", {
        "lookup_table_obj": lookup_table_obj,
        "sub_lookup_query": sub_lookup_query,
        "active_tab": active_tab,
        "permissions":permissions
    })

from django.contrib.auth.models import User

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

    # 🟩 Pagination
    paginator = Paginator(users, 10)
    page = request.GET.get("user_page")
    user_page_obj = paginator.get_page(page)
    permissions = get_user_permissions(request.user)

    return render(request, "welcome.html", {
        "user_page_obj": user_page_obj,
        "user_query": query,
        "active_tab": active_tab,
        "permissions":permissions
    })

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
    role_paginator = Paginator(roles, 10)
    page_number = request.GET.get('roles_page')
    roles_page_obj = role_paginator.get_page(page_number)
    roles_page_obj.query = query1
    permissions = get_user_permissions(request.user)

    return render(request, 'welcome.html', {
        'roles_page_obj': roles_page_obj,
        'query1': query1,
        'active_tab': active_tab,
        "permissions":permissions
    })

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
            try:
                if len(query2) == 4 and query2.isdigit():
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
            'Landmark', 'Area', 'City', 'State', 'Country','Postal Code', 'Native Place', 'Native Postal Code',
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
                dv.occupation_type,
                dv.occupation_nature,
                dv.department,
                dv.position,
                dv.designation,
                dv.business_type,
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

    paginator = Paginator(donorvolunteer, 10)
    page_obj = paginator.get_page(request.GET.get('donor_page'))
    permissions = get_user_permissions(request.user)

    return render(request, "welcome.html", {
        "page_obj": page_obj,
        "query2": query2 if query2 else "",
        "permissions": permissions
    })

from django.db.models import Value
from django.db.models.functions import Concat

def search_donation(request):
    donations = Donation.objects.all()
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

    # ---- PAGINATION ----
    paginator = Paginator(donations, 10)
    donation_page_obj = paginator.get_page(request.GET.get('page'))
    permissions = get_user_permissions(request.user)

    return render(request, 'welcome.html', {
        'donation_page_obj': donation_page_obj,
        'query3': query3,
        'permissions': permissions,
    })

@login_required
def search_donation_payment(request):

    payments_query = request.GET.get("payments_query", "").strip()
    payments = DonationPaymentBox.objects.filter(is_deleted=False)
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

            # 🔹 Donation Box fields
            Q(donation_box__donation_id__icontains=payments_query) |
            Q(donation_box__key_id__icontains=payments_query) |
            Q(donation_box__location__icontains=payments_query) |
            Q(donation_box__box_size__icontains=payments_query) |
            Q(donation_box__status__icontains=payments_query) |

            # 🔹 Regular fields (search related FK name fields)
            Q(opened_by__first_name__icontains=payments_query) |
            Q(opened_by__last_name__icontains=payments_query) |
            Q(opened_by__contact_number__icontains=payments_query) |
            Q(received_by__first_name__icontains=payments_query) |
            Q(received_by__last_name__icontains=payments_query) |
            Q(received_by__contact_number__icontains=payments_query) |
            Q(address__icontains=payments_query) |
            Q(i_witness__icontains=payments_query) |

            # 🔹 Lookup (payment method)

            # 🔹 Users
            Q(owner__username__icontains=payments_query) |
            Q(created_by__username__icontains=payments_query) |
            Q(updated_by__username__icontains=payments_query)
        )

        # Numeric search → amount or ID
        if payments_query.replace('.', '', 1).isdigit():
            # numeric search — match exact id or amount
            try:
                # try to parse decimal amount
                from decimal import Decimal
                amt = Decimal(payments_query)
                filters |= (
                    Q(amount=amt) |
                    Q(id=int(float(payments_query)))
                )
            except Exception:
                # fallback to id-only match
                try:
                    filters |= Q(id=int(float(payments_query)))
                except Exception:
                    pass

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
    # CSV download
    if request.GET.get("download") == "1":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="donation_payments.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "Donation ID",
            "Owner",
            "Opened By",
            "Amount",
            "Payment Method",
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
                p.payment_method.lookup_name if p.payment_method else "",
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
    # Pagination (correct)
    paginator = Paginator(payments, 5)
    page_number = request.GET.get("payments_page")
    payments_page_obj = paginator.get_page(page_number)
    permissions = get_user_permissions(request.user)

    return render(request, "welcome.html", {
        "payments_page_obj": payments_page_obj,
        "payments_query": payments_query,
        "permissions": permissions,
 })

@login_required
def search_donation_box(request):

    box_query = request.GET.get("box_query", "").strip()
    boxes = DonationBox.objects.filter(is_deleted=False).order_by("id")
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
            Q(location__icontains=box_query) |
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
    paginator = Paginator(boxes, 5)
    page_number = request.GET.get("box_page")
    box_page_obj = paginator.get_page(page_number)
    permissions = get_user_permissions(request.user)
    return render(request, "welcome.html", {
        "box_page_obj": box_page_obj,
        "box_query": box_query,
        "permissions": permissions,
    })

#----------------Globle End Search--------------
from django.core.files.storage import default_storage

def add_donor_volunteer(request):
    person_type_options = Lookup.objects.filter(lookup_type__type_name__iexact='Person Type')
    id_type_options = Lookup.objects.filter(lookup_type__type_name__iexact='ID Type')

    occupation_types = Lookup.objects.filter(lookup_type__type_name__iexact="Occupation Type")
    occupation_natures = Lookup.objects.filter(lookup_type__type_name__iexact="Occupation Nature")

    departments = Lookup.objects.filter(lookup_type__type_name__iexact="Department")
    positions = Lookup.objects.filter(lookup_type__type_name__iexact="Position")
    designations = Lookup.objects.filter(lookup_type__type_name__iexact="Designation")

    org_types = Lookup.objects.filter(lookup_type__type_name__iexact="Organization Type")
    business_types = Lookup.objects.filter(lookup_type__type_name__iexact="Business Type")

    donation_boxes = DonationBox.objects.filter(is_deleted=False)
    all_donors = DonorVolunteer.objects.filter(is_deleted=False)

    donor_box_owner = Lookup.objects.filter(lookup_name='Donor-Box-Owner').first()
    donor_box_owner_id = donor_box_owner.id if donor_box_owner else None
    blood_groups = [
        ("A+", "A+"),
        ("A-", "A-"),
        ("B+", "B+"),
        ("B-", "B-"),
        ("AB+", "AB+"),
        ("AB-", "AB-"),
        ("O+", "O+"),
        ("O-", "O-"),
    ]
    def get_lookup(field):
        value = request.POST.get(field)
        return Lookup.objects.get(id=value) if value and value.isdigit() else None

    def get_donor(field):
        value = request.POST.get(field)
        return DonorVolunteer.objects.get(id=value) if value and value.isdigit() else None

    if request.method == "POST":
        email = request.POST.get("email")
        if email and DonorVolunteer.objects.filter(email__iexact=email).exists():
            messages.error(
                request,
                "This email already exists. Please use a different email."
            )
            return redirect("add_donor_volunteer")
        donor = DonorVolunteer.objects.create(
            person_type=get_lookup("person_type"),
            referred_by=get_donor("referred_by"),
            salutation=request.POST.get("salutation"),
            first_name=request.POST.get("first_name"),
            middle_name=request.POST.get("middle_name"),
            last_name=request.POST.get("last_name"),
            gender=request.POST.get("gender"),
            date_of_birth=request.POST.get("date_of_birth") or None,
            age=request.POST.get("age") or None,
            blood_group=request.POST.get("blood_group"),
            contact_number=request.POST.get("contact_number"),
            whatsapp_number=request.POST.get("whatsapp_number"),
            email=request.POST.get("email"),
            donor_box_id=request.POST.get("donor_box") if (
                get_lookup("person_type") and get_lookup("person_type").lookup_name == "Donor-Box-Owner"
            ) else None,
            house_number=request.POST.get("house_number"),
            building_name=request.POST.get("building_name"),
            landmark=request.POST.get("landmark"),
            area=request.POST.get("area"),
            city=request.POST.get("city"),
            state=request.POST.get("state"),
            country=request.POST.get("country"),
            postal_code=request.POST.get("postal_code"),
            native_place=request.POST.get("native_place"),
            native_postal_code=request.POST.get("native_postal_code"),
            occupation_type=get_lookup("occupation_type"),
            occupation_nature=get_lookup("occupation_nature"),
            department=get_lookup("department"),
            position=get_lookup("position"),
            designation=get_lookup("designation"),
            doa=request.POST.get("doa") or None,
            years_to_marriage=request.POST.get("years_to_marriage") or None,
            business_salutation=request.POST.get("business_salutation"),
            business_name=request.POST.get("business_name"),
            business_type=get_lookup("business_type"),
            business_nature=get_lookup("business_nature"),
            org_name=request.POST.get("org_name"),
            org_type=get_lookup("org_type"),
            nature_of_service=get_lookup("nature_of_service"),
            id_type=get_lookup("id_type"),
            id_number=request.POST.get("id_number"),
            pan_number=request.POST.get("pan_number"),
            created_by=request.user,
            updated_by=request.user,
        )
        if request.FILES.get("id_proof_image"):
            donor.id_proof_image.save(
                request.FILES["id_proof_image"].name,
                request.FILES["id_proof_image"]
            )

        if request.FILES.get("pan_card_image"):
            donor.pan_card_image.save(
                request.FILES["pan_card_image"].name,
                request.FILES["pan_card_image"]
            )
        return redirect("welcome")
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
        "business_types": business_types,
        "donor_box_owner_id": donor_box_owner_id,
        "blood_groups": blood_groups,
    })

from django.db import IntegrityError, transaction, DatabaseError
from django.db.models import Sum

def adddonation(request):
    donors = DonorVolunteer.objects.all()
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
            used_categories = previous_donations.values_list(
                "donation_category_id", flat=True
            )
            used_sub_categories = previous_donations.values_list(
                "donation_sub_category_id", flat=True
            )
            totals = previous_donations.aggregate(
                total_declared=Sum("donation_amount_declared"),
                total_paid=Sum("donation_amount_paid")
            )
            remaining = (totals["total_declared"] or 0) - (totals["total_paid"] or 0)
            if remaining > 0 and category_id not in used_categories:
                messages.error(
                    request,
                    "This donation category is not allowed for this donor."
                )
                return redirect("adddonation")
            if remaining > 0 and sub_category_id and sub_category_id not in used_sub_categories:
                messages.error(
                    request,
                    "This donation sub-category is not allowed for this donor."
                )
                return redirect("adddonation")
        if paid_amount > declared_amount:
            messages.error(request, "Paid amount cannot exceed declared amount.")
            return redirect("adddonation")
        donation_date_raw = request.POST.get("donation_date")

        if donation_date_raw:
            donation_date = donation_date_raw
        else:
            donation_date = timezone.now().date()
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
            payment_method_id=fk(request.POST.get("payment_method")),
            payment_status_id=fk(request.POST.get("payment_status")),
            name_of_bank=request.POST.get("name_of_bank"),
            branch=request.POST.get("branch"),
            transaction_id=request.POST.get("transaction_id"),
            check_no=request.POST.get("check_no"),
            created_by=request.user,

        )
        messages.success(request, "Donation added successfully!")
        return redirect("adddonation")

    return render(request, "adddonation.html", {
        "donors": donors,
        "donation_categories": donation_categories,
        "donation_sub_categories": donation_sub_categories,
        "payment_methods": payment_methods,
        "payment_statuses": payment_statuses,
        "today": today
    })

def donation_summary(request, id):
    donation = get_object_or_404(Donation, id=id)
    donors = DonorVolunteer.objects.all()
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
    total_declared = donations.aggregate(total=Sum("donation_amount_declared"))["total"] or 0
    total_paid = donations.aggregate(total=Sum("donation_amount_paid"))["total"] or 0
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
    donation = get_object_or_404(Donation, id=id)
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
    donation = get_object_or_404(Donation, id=id)

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
    payment = get_object_or_404(DonationPaymentBox,id=id,is_deleted=False)
    donor = DonorVolunteer.objects.filter(created_by=payment.owner).first()
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
    payment = get_object_or_404(DonationPaymentBox, id=id, is_deleted=False)
    donor = DonorVolunteer.objects.filter(created_by=payment.owner).first()
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
from django.core.serializers.json import DjangoJSONEncoder
from django.core.mail import send_mail
from django.utils import timezone
# def add_donation_payment(request):
#     donation_boxes = DonationBox.objects.filter(
#         is_deleted=False,
#         donorvolunteer__isnull=False
#     ).distinct()

#     payment_methods = Lookup.objects.filter(
#         lookup_type__type_name__iexact="Payment Method",is_deleted=False
#     ).order_by("lookup_name")
#     donor_volunteers = DonorVolunteer.objects.filter( is_deleted=False,person_type__lookup_name__iexact="Employee")
#     box_owner_map = []
#     donors = DonorVolunteer.objects.filter(is_deleted=False)
#     for d in donors:
#         if d.donor_box:
#             address = ", ".join(filter(None, [
#                 d.house_number,
#                 d.building_name,
#                 d.area,
#                 d.city,
#                 d.state,
#                 d.postal_code
#             ]))

#             box_owner_map.append({
#                 "box_id": d.donor_box.id,
#                 "owner_name": f"{d.first_name} {d.last_name}",
#                 "address": address,
#             })

#     if request.method == "POST":
#         donation_box_id = request.POST.get("donation_box")
#         address = request.POST.get("address")
#         opened_by_id = request.POST.get("opened_by")
#         received_by_id = request.POST.get("received_by")
#         amount = request.POST.get("amount")
#         payment_method_id = request.POST.get("payment_method")
#         date_time = request.POST.get("date_time")
#         i_witness = request.POST.get("i_witness")
#         name_of_bank = request.POST.get("name_of_bank")
#         branch = request.POST.get("branch")
#         transaction_id = request.POST.get("transaction_id")
#         donation_box = get_object_or_404(DonationBox, id=donation_box_id)
#         payment_method = get_object_or_404(Lookup, id=payment_method_id)
#         opened_by = DonorVolunteer.objects.get(id=opened_by_id) if opened_by_id else None
#         received_by = DonorVolunteer.objects.get(id=received_by_id) if received_by_id else None
#         owner = donation_box.donorvolunteer if hasattr(donation_box, "donorvolunteer") else None

#         DonationPaymentBox.objects.create(
#             owner=owner,    
#             donation_box=donation_box,
#             address=address,
#             opened_by=opened_by,
#             received_by=received_by,
#             amount=amount,
#             payment_method=payment_method,
#             date_time=date_time,
#             i_witness=i_witness,
#             name_of_bank=name_of_bank,
#             branch=branch,
#             transaction_id=transaction_id,
#             created_by=request.user,
#             updated_by=request.user,
#         )
#         messages.success(request, "Donation Payment Added Successfully!")
#         return redirect("welcome")
#     context = {
#         "donation_boxes": donation_boxes,
#         "payment_methods": payment_methods,
#         "donor_volunteers": donor_volunteers,
#         "box_owner_map": json.dumps(box_owner_map, cls=DjangoJSONEncoder),
#         "current_time": timezone.now(),
#     }
#     return render(request, "add_donationbox_payment.html", context)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
import json

def add_donation_payment(request):

    # -----------------------------
    # DONATION BOXES (ONLY WITH OWNER)
    # -----------------------------
    donation_boxes = DonationBox.objects.filter(
        is_deleted=False,
        donorvolunteer__isnull=False
    ).distinct()

    # -----------------------------
    # PAYMENT METHODS
    # -----------------------------
    payment_methods = Lookup.objects.filter(
        lookup_type__type_name__iexact="Payment Method",
        is_deleted=False
    ).order_by("lookup_name")

    # -----------------------------
    # EMPLOYEES
    # -----------------------------
    donor_volunteers = DonorVolunteer.objects.filter(
        is_deleted=False,
        person_type__lookup_name__iexact="Employee"
    )

    # -----------------------------
    # BOX → OWNER MAP (FOR JS AUTOFILL)
    # -----------------------------
    box_owner_map = []
    owners = DonorVolunteer.objects.filter(
        is_deleted=False,
        donor_box__isnull=False
    )

    for owner in owners:
        address = ", ".join(filter(None, [
            owner.house_number,
            owner.building_name,
            owner.area,
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

    # -----------------------------
    # SAVE PAYMENT
    # -----------------------------
    if request.method == "POST":

        donation_box = get_object_or_404(
            DonationBox,
            id=request.POST.get("donation_box")
        )

        payment_method = get_object_or_404(
            Lookup,
            id=request.POST.get("payment_method")
        )

        # ✅ SAFE HANDLING (NO EMPTY STRING ERROR)
        opened_by_id = request.POST.get("opened_by")
        received_by_id = request.POST.get("received_by")

        opened_by = (
            DonorVolunteer.objects.filter(id=opened_by_id).first()
            if opened_by_id else None
        )

        received_by = (
            DonorVolunteer.objects.filter(id=received_by_id).first()
            if received_by_id else None
        )

        # ✅ FETCH OWNER FROM DONATION BOX
        owner = DonorVolunteer.objects.filter(
            donor_box=donation_box,
            is_deleted=False
        ).first()

        DonationPaymentBox.objects.create(
            owner=owner,
            donation_box=donation_box,
            address=request.POST.get("address"),
            opened_by=opened_by,
            received_by=received_by,
            amount=request.POST.get("amount"),
            payment_method=payment_method,
            date_time=request.POST.get("date_time"),
            i_witness=request.POST.get("i_witness"),
            name_of_bank=request.POST.get("name_of_bank"),
            branch=request.POST.get("branch"),
            transaction_id=request.POST.get("transaction_id"),
            created_by=request.user,
            updated_by=request.user,
        )

        messages.success(request, "Donation Payment Added Successfully!")
        return redirect("welcome")

    # -----------------------------
    # CONTEXT
    # -----------------------------
    context = {
        "donation_boxes": donation_boxes,
        "payment_methods": payment_methods,
        "donor_volunteers": donor_volunteers,
        "box_owner_map": json.dumps(box_owner_map, cls=DjangoJSONEncoder),
        "current_time": timezone.now(),
    }

    return render(request, "add_donationbox_payment.html", context)


@login_required
def add_donation_box(request):
    if request.method == "POST":
        key_id = request.POST.get("key_id")
        box_size = request.POST.get("box_size")  
        status = request.POST.get("status")
        qr_code = request.FILES.get("qr_code")  
        box = DonationBox(
            key_id=key_id,
            box_size=box_size,
            status=status,
            qr_code=qr_code if qr_code else None,
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

    # If no results found
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
        return redirect("lookup_type_list")
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
    roles = UserModuleAccess.objects.all()
    if request.method == 'POST':
        new_username = request.POST.get('username')
        if User.objects.filter(username=new_username).exclude(id=user_obj.id).exists():
            messages.error(
                request,
                "Username already exists! Please choose a different one."
            )
            return redirect(request.path)
        user_obj.first_name = request.POST.get('first_name')
        user_obj.last_name  = request.POST.get('last_name')
        user_obj.username   = new_username
        user_obj.email      = request.POST.get('email')
        role_id = request.POST.get('role')
        if role_id:
            if not request.user.is_superuser:
                messages.error(
                    request,
                    "❌ You are not allowed to assign roles."
                )
                return redirect("welcome")

            selected_role = get_object_or_404(UserModuleAccess, id=role_id)
            user_role_obj.role = selected_role
            user_role_obj.save()

        user_obj.save()
        messages.success(request, "User updated successfully!")
        return redirect('welcome')
    if request.user.is_superuser:
        allowed_modules = list(
            Module.objects.all().values_list('module_name', flat=True)
        )
    else:
        current_user_role = (
            UserRole.objects
            .filter(user=request.user)
            .select_related('role')
            .first()
        )
        if current_user_role and current_user_role.role:
            allowed_modules = list(
                UserModuleAccess.objects.filter(
                    name=current_user_role.role.name,
                    can_access=True
                )
                .select_related('module')
                .values_list('module__module_name', flat=True)
            )
        else:
            allowed_modules = []
            messages.warning(
                request,
                "⚠️ You do not have permission to access this module.")

    return render(
        request,
        'edit_user.html',
        {
            'edit_user': user_obj,
            'roles': roles,
            'user_role': user_role_obj,
            'allowed_modules': allowed_modules,
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

@login_required
def edit_donor(request, donor_id):
    donor = get_object_or_404(DonorVolunteer, id=donor_id)
    donors = DonorVolunteer.objects.filter(is_deleted=False)
    person_type_options = Lookup.objects.filter(lookup_type__type_name__iexact='Person Type')
    id_types = Lookup.objects.filter(
        lookup_type__type_name="ID Type",
        is_deleted=False
    )

    occupation_types = Lookup.objects.filter(
        lookup_type__type_name="Occupation Type",
        is_deleted=False
    )

    occupation_natures = Lookup.objects.filter(
        lookup_type__type_name="Occupation Nature",
        is_deleted=False
    )

    departments = Lookup.objects.filter(
        lookup_type__type_name="Department",
        is_deleted=False
    )

    positions = Lookup.objects.filter(
        lookup_type__type_name="Position",
        is_deleted=False
    )

    designations = Lookup.objects.filter(
        lookup_type__type_name="Designation",
        is_deleted=False
    )

    business_types = Lookup.objects.filter(
        lookup_type__type_name="Business Type",
        is_deleted=False
    )

    business_natures = Lookup.objects.filter(
        lookup_type__type_name="Business Nature",
        is_deleted=False
    )

    org_types = Lookup.objects.filter(
        lookup_type__type_name="Organization Type",
        is_deleted=False
    )

    nature_of_services = Lookup.objects.filter(
        lookup_type__type_name="Nature of Service",
        is_deleted=False
    )
    person_type_id = request.POST.get("person_type")

    person_type = Lookup.objects.filter(id=person_type_id).first()

    donor_box_id = (
    request.POST.get("donor_box")
    if person_type and person_type.lookup_name == "Donor-Box-Owner"
    else None
)
    donation_boxes = DonationBox.objects.filter(is_deleted=False)

    # ---------------- SAVE ----------------
    if request.method == "POST":
        donor.person_type_id = request.POST.get("person_type") or None
        donor.referred_by_id = request.POST.get("referred_by") or None
        donor.salutation = request.POST.get("salutation")
        donor.first_name = request.POST.get("first_name")
        donor.middle_name = request.POST.get("middle_name")
        donor.last_name = request.POST.get("last_name")
        donor.gender = request.POST.get("gender")
        donor.date_of_birth = request.POST.get("date_of_birth") or None
        donor.age = request.POST.get("age") or None
        donor.blood_group = request.POST.get("blood_group")
        donor.contact_number = request.POST.get("contact_number")
        donor.whatsapp_number = request.POST.get("whatsapp_number")
        donor.email = request.POST.get("email")
        donor.doa = request.POST.get("doa") or None
        donor.years_to_marriage = request.POST.get("years_to_marriage") or None
        donor.house_number = request.POST.get("house_number")
        donor.building_name = request.POST.get("building_name")
        donor.landmark = request.POST.get("landmark")
        donor.area = request.POST.get("area")
        donor.city = request.POST.get("city")
        donor.state = request.POST.get("state")
        donor.country = request.POST.get("country")
        donor.postal_code = request.POST.get("postal_code")
        donor.native_place = request.POST.get("native_place")
        donor.native_postal_code = request.POST.get("native_postal_code")
        donor.occupation_type_id = request.POST.get("occupation_type") or None
        donor.occupation_nature_id = request.POST.get("occupation_nature") or None
        donor.department_id = request.POST.get("department") or None
        donor.position_id = request.POST.get("position") or None
        donor.designation_id = request.POST.get("designation") or None
        donor.business_type_id = request.POST.get("business_type") or None
        donor.business_salutation = request.POST.get("business_salutation")
        donor.business_name = request.POST.get("business_name")
        donor.business_nature_id = request.POST.get("business_nature") or None
        donor.org_name = request.POST.get("org_name")
        donor.org_type_id = request.POST.get("org_type") or None
        donor.nature_of_service_id = request.POST.get("nature_of_service") or None
        donor.id_type_id = request.POST.get("id_type") or None
        donor.id_number = request.POST.get("id_number")
        donor.pan_number = request.POST.get("pan_number")

        if request.FILES.get("id_proof_image"):
            donor.id_proof_image = request.FILES["id_proof_image"]

        if request.FILES.get("pan_card_image"):
            donor.pan_card_image = request.FILES["pan_card_image"]

        donor.updated_by = request.user
        donor.donor_box_id = donor_box_id
        donor.save()
        return redirect("welcome")

    # ---------------- RENDER ----------------
    return render(request, "edit_donor.html", {
        "donor": donor,
        "donors": donors,
        "donor_box_id":donor_box_id,
        "person_type_options": person_type_options,
        "id_types": id_types,
        "donation_boxes": donation_boxes,
        "occupation_types": occupation_types,
        "occupation_natures": occupation_natures,
        "departments": departments,
        "positions": positions,
        "designations": designations,
        "business_types": business_types,
        "business_natures": business_natures,
        "org_types": org_types,
        "nature_of_services": nature_of_services,
        "blood_groups": DonorVolunteer.BLOOD_GROUP_CHOICES,
    })

def edit_donation(request, id):
    donation = get_object_or_404(Donation, id=id)
    donors = DonorVolunteer.objects.filter(
        person_type__lookup_name__icontains='donor'
    )
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

# def edit_box_payment(request, id):
#     payment = get_object_or_404(DonationPaymentBox, id=id)
#     if request.method == 'POST':
#         payment.address = request.POST.get('address')
#         payment.amount = request.POST.get('amount')
#         payment.i_witness = request.POST.get('i_witness')
#         payment.updated_by = request.user
#         payment.save()
#         messages.success(request, "Payment updated successfully!")
#         return redirect('welcome') 
#     return render(request, 'BoxPayment.html', {
#         'payment': payment
#     })
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
        'donors': DonorVolunteer.objects.filter(is_deleted=False)
    })

def edit_donation_box(request, id):
    box = get_object_or_404(DonationBox, id=id)
    if request.method == 'POST':
        box.key_id = request.POST.get('key_id')
        box.box_size = request.POST.get('box_size')
        box.location = request.POST.get('location')
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

# DONATIONEDELETE VIEW------------------------------
from .models import DonationPaymentBox

@login_required
def delete_box_payment(request, id):
    if request.method == "POST":
        payment = get_object_or_404(
            DonationPaymentBox,id=id,is_deleted=False)
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

def edit_donation_box(request, id):
    box = get_object_or_404(DonationBox, id=id)
    if request.method == 'POST':
        box.key_id = request.POST.get('key_id')
        box.box_size = request.POST.get('box_size')
        box.location = request.POST.get('location')
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
                request,
                "Please scan the QR code or enter a valid Donation Box ID."
            )
            return redirect("select_donation_box")

        try:
            donation_box = DonationBox.objects.get(
                donation_id__iexact=donation_box_id,
                is_deleted=False
            )

            request.session["selected_donation_box_id"] = donation_box.id

            messages.success(
                request,
                f"Donation Box '{donation_box.donation_id}' selected successfully."
            )
            return redirect("add_donation_payment")

        except DonationBox.DoesNotExist:
            messages.error(
                request,
                "Invalid Donation Box ID. Please scan the correct QR code or re-enter the ID."
            )
            return redirect("select_donation_box")

    return render(request, "donation_box_input.html")

# ✅ AJAX ENDPOINTS FOR PAYMENT MODAL AUTO-FILL
from django.http import JsonResponse

def get_donation_boxes_data(request):
    """Returns all donation boxes for the modal dropdown"""
    boxes = DonationBox.objects.filter(is_deleted=False).values(
        'id', 'donation_id', 'location', 'box_size'
    ).order_by('-created_at')
    
    return JsonResponse({
        'boxes': list(boxes)
    })

def get_donation_box_details(request, box_id):
    """Returns auto-fill data for a selected donation box"""
    try:
        box = DonationBox.objects.get(id=box_id, is_deleted=False)
        
        # Get last payment for this box to auto-fill payment method & status
        last_payment = DonationPaymentBox.objects.filter(
            donation_box=box,
            is_deleted=False
        ).order_by('-created_at').first()
        
        # Get last donation for payment method preferences
        last_donation = Donation.objects.filter(
            is_deleted=False
        ).order_by('-created_at').first()
        
        data = {
            'donation_id': box.donation_id,
            'location': box.location,
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
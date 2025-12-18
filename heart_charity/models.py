from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings  # make sure you import this

class Module(models.Model):
    module_name = models.CharField(max_length=100, unique=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='Module_created')
    created_date = models.DateTimeField(auto_now_add=True)
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")
    def __str__(self):
        return self.module_name

class UserModuleAccess(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    can_access = models.BooleanField(default=False)
    can_add = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_view = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='UserModuleAccess_created')
    created_date = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='UserModuleAccess_updated')
    updated_date = models.DateTimeField(auto_now=True)
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")
    class Meta:
        unique_together = ("module", "name")
        ordering = ("module", "name")

    def __str__(self):
        return f"{self.module.module_name} — {self.name}"


class UserRole(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.ForeignKey(UserModuleAccess, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_users")
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='UserRole_created')
    created_date = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='UserRole_updated')
    updated_date = models.DateTimeField(auto_now=True)
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")
    def __str__(self):
        return f"{self.user.username} - {self.role.name if self.role else 'No Role'}"

class DonationBox(models.Model):
    donation_id = models.CharField(max_length=10, unique=True, editable=False)
    qr_code = models.ImageField(upload_to='qr_images/', blank=True, null=True)
    location = models.CharField(max_length=255)
    key_id = models.CharField(max_length=50, null=True, blank=True)
    BOX_SIZES = [
        ('small', 'Small'),
        ('medium', 'Medium'),
        ('large', 'Large'),
    ]
    box_size = models.CharField(max_length=20, choices=BOX_SIZES, default='medium')
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='uploaded_boxes'
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_boxes'
    )
    status_choices = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
        ('return', 'Return')
    ]
    status = models.CharField(max_length=20, choices=status_choices, default='Active')
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)  # auto update time
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")

    def save(self, *args, **kwargs):
        if not self.donation_id:
            last_box = DonationBox.objects.all().order_by('id').last()
            if last_box:
                last_id = int(last_box.donation_id.split('_')[1])
                new_id = f"DO_{last_id + 1:04d}"
            else:
                new_id = "DO_0001"
            self.donation_id = new_id
        if not self.qr_code:
            qr_data = f"Donation ID: {self.donation_id}\nBox Name: {self.donation_box_name}\nLocation: {self.location}"
            qr_img = qrcode.make(qr_data)
            buffer = BytesIO()
            qr_img.save(buffer, format='PNG')
            self.qr_code.save(f"{self.donation_id}_qr.png", File(buffer), save=False)

        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.donation_box_name} ({self.donation_id})"
gender_choices = [('Male','Male'), ('Female','Female'), ('Other','Other')]

from datetime import date


class DonorVolunteer(models.Model):
    BLOOD_GROUP_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]
    person_type = models.ForeignKey(
        "Lookup",
        on_delete=models.SET_NULL,
        null=True,
        related_name="person_type_lookup"
    )
    referred_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referrals'
    )
    # -------------------- PERSONAL DETAILS --------------------
    salutation = models.CharField(max_length=20, blank=True, null=True)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=10, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    blood_group = models.CharField(
        max_length=5, choices=BLOOD_GROUP_CHOICES,
        blank=True, null=True
    )
    contact_number = models.CharField(max_length=20)
    whatsapp_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(unique=True)
    donor_box = models.ForeignKey(
        DonationBox,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    doa = models.DateField(blank=True, null=True)
    years_to_marriage = models.IntegerField(blank=True, null=True)
    # -------------------- ADDRESS --------------------
    house_number = models.CharField(max_length=50)
    building_name = models.CharField(max_length=100, blank=True, null=True)
    landmark = models.CharField(max_length=100, blank=True, null=True)
    area = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    country = models.CharField(max_length=50, default='India')
    postal_code = models.CharField(max_length=20)
    native_place = models.CharField(max_length=200, blank=True, null=True)
    native_postal_code = models.CharField(max_length=20, blank=True, null=True)
    # -------------------- LOOKUPS --------------------
    id_type = models.ForeignKey(
        "Lookup",
        on_delete=models.SET_NULL,
        null=True,
        related_name="id_type_lookup"
    )
    occupation_type = models.ForeignKey(
        "Lookup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="occupation_type_lookup"
    )
    occupation_nature = models.ForeignKey(
        "Lookup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="occupation_nature_lookup"
    )
    department = models.ForeignKey(
        "Lookup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="department_lookup"
    )
    position = models.ForeignKey(
        "Lookup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="position_lookup"
    )
    designation = models.ForeignKey(
        "Lookup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="designation_lookup"
    )
    business_type = models.ForeignKey(
        "Lookup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="business_type_lookup"
    )

    # -------------------- NEW BUSINESS FIELDS (ADDED) --------------------
    business_salutation = models.CharField(max_length=50, null=True, blank=True)
    business_name = models.CharField(max_length=200, null=True, blank=True)
    business_nature = models.ForeignKey(
        "Lookup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="business_nature_lookup"
    )
    org_name = models.CharField(max_length=200, null=True, blank=True)
    org_type = models.ForeignKey(
        "Lookup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="org_type_lookup"
    )
    nature_of_service = models.ForeignKey("Lookup",null=True,blank=True,on_delete=models.SET_NULL,related_name="nature_of_service_lookup")
    id_number = models.CharField(max_length=20, blank=True, null=True)
    id_proof_image = models.ImageField(upload_to='id_proofs/', blank=True, null=True)
    pan_number = models.CharField(max_length=20, blank=True, null=True)
    pan_card_image = models.ImageField(upload_to='pan_cards/', blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="donor_created_by")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="donor_updated_by")
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")

    # -------------------- SAVE --------------------
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class LookupType(models.Model):
    type_name = models.CharField(max_length=100, unique=True)
    # Soft Delete Fields
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='lookup_type_created')
    created_date = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='lookup_type_updated')
    updated_date = models.DateTimeField(auto_now=True)
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")

    @property
    def formatted_id(self):
        return f"{self.id:03d}"     # → 001, 002, 010, 123

    def __str__(self):
        return f"{self.formatted_id} - {self.type_name}"

class Lookup(models.Model):
    lookup_name = models.CharField(max_length=100, unique=True)

    lookup_type = models.ForeignKey(
        LookupType,
        on_delete=models.CASCADE,
        related_name="lookups"
    )
# Soft Delete Fields
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="lookup_created"
    )
    created_date = models.DateTimeField(auto_now_add=True)

    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="lookup_updated"
    )
    updated_date = models.DateTimeField(auto_now=True)
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")
    @property
    def formatted_id(self):
        return f"{self.id:03d}"

    def __str__(self):
        return f"{self.lookup_name} ({self.lookup_type.type_name})"

from .models import DonorVolunteer  # assuming same app (heart_charity)
class DonationOwner(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('Cash', 'Cash'),
        ('Online', 'Online'),
        ('Cheque', 'Cheque'),
        ('UPI', 'UPI'),
    ]

    id = models.AutoField(primary_key=True)

    # Foreign key to DonorVolunteer (only Donor-Box-Owner type)
    owner_name = models.ForeignKey(
        DonorVolunteer,
        on_delete=models.CASCADE,
        limit_choices_to={'person_type': 'Donor-Box-Owner'},
        related_name='donation_owners'
    )

    # ✅ Foreign key to DonationBox (linked via donation_id)
    donation_box = models.ForeignKey(
        'DonationBox',
        on_delete=models.CASCADE,
        related_name='donation_owners',
        to_field='donation_id',  # <-- This line makes the foreign key use donation_id instead of the default pk
        db_column='donation_id'  # Optional: sets actual DB column name to 'donation_id'
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="donation_owner_created_by"
    )
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="donation_owner_updated_by"
    )

    # Soft Delete Fields
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")
    def __str__(self):
        return f"{self.owner_name.first_name} {self.owner_name.last_name} - ₹{self.amount} ({self.donation_box.donation_id})"


from django.db import models

class ReceiptSequence(models.Model):
    year = models.PositiveIntegerField(unique=True)
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.year} → {self.last_number}"



from django.utils import timezone
from django.db.models.signals import pre_save
from django.dispatch import receiver

class Donation(models.Model):
    donor = models.ForeignKey('DonorVolunteer',on_delete=models.CASCADE,limit_choices_to={'person_type': 'Donor'},related_name='donations')
    donation_date = models.DateField(default=timezone.now)
    donation_category = models.ForeignKey(Lookup,on_delete=models.SET_NULL,null=True,related_name='donation_categories')
    donation_sub_category = models.ForeignKey(Lookup,on_delete=models.SET_NULL,null=True,related_name='donation_sub_categories')
    payment_method = models.ForeignKey(Lookup,on_delete=models.SET_NULL,null=True,related_name='donation_payment_methods')
    payment_status = models.ForeignKey(Lookup,on_delete=models.SET_NULL,null=True,related_name='payment_statuses')
    transaction_id = models.CharField(max_length=50, blank=True, null=True)
    receipt_id = models.CharField(
    max_length=20,
    unique=True,
    blank=True,
    null=True
)    
    place_of_donation = models.CharField(max_length=200, blank=True, null=True)
    check_no = models.CharField(max_length=50, blank=True, null=True)
    donation_received_by = models.CharField(max_length=150, blank=True, null=True)
    reference_name = models.CharField(max_length=150, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    donation_amount_declared = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    donation_amount_paid = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    created_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,related_name='donation_created')
    updated_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,related_name='donation_updated')

    created_at = models.DateTimeField(auto_now_add=True)  # auto timestamp
    updated_at = models.DateTimeField(auto_now=True)      # auto update timestamp
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")  
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="verified_donations")
    verified_at = models.DateTimeField(null=True, blank=True)
    def __str__(self):
        return f"Donation {self.id}"


class DonationPaymentBox(models.Model):
    id = models.AutoField(primary_key=True)
    receipt_id = models.CharField(
    max_length=20,
    unique=True,
    blank=True,
    null=True
)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='donation_payments')
    donation_box = models.ForeignKey('DonationBox', on_delete=models.CASCADE, related_name='payment')
    address = models.CharField(max_length=255, blank=True, null=True)
    opened_by = models.ForeignKey('heart_charity.DonorVolunteer',related_name='opened_payments',on_delete=models.SET_NULL,null=True,blank=True)
    received_by = models.ForeignKey('heart_charity.DonorVolunteer',related_name='received_payments',on_delete=models.SET_NULL,null=True,blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.ForeignKey(Lookup,on_delete=models.SET_NULL,null=True,related_name='payment_methods_box')
    date_time = models.DateTimeField(default=timezone.now)
    i_witness = models.CharField(max_length=100, blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_donation_payments')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_donation_payments')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL,null=True, blank=True,related_name='verified_donation_payments')
    verified_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")

    def __str__(self):
        return f"{self.donation_box} - ₹{self.amount} by {self.owner}"  

class Donation_Hist(models.Model):
    hist_id = models.AutoField(primary_key=True)
    donation = models.ForeignKey('Donation',on_delete=models.CASCADE,related_name='history' )
    donor = models.ForeignKey('DonorVolunteer', on_delete=models.SET_NULL, null=True)
    donation_date = models.DateField(null=True)
    donation_category = models.ForeignKey(Lookup, on_delete=models.SET_NULL, null=True, related_name='+')
    donation_sub_category = models.ForeignKey(Lookup, on_delete=models.SET_NULL, null=True, related_name='+')
    payment_method = models.ForeignKey(Lookup, on_delete=models.SET_NULL, null=True, related_name='+')
    payment_status = models.ForeignKey(Lookup, on_delete=models.SET_NULL, null=True, related_name='+')
    transaction_id = models.CharField(max_length=50, null=True, blank=True)
    receipt_id = models.CharField(max_length=50, null=True, blank=True)
    place_of_donation = models.CharField(max_length=200, null=True, blank=True)
    check_no = models.CharField(max_length=50, null=True, blank=True)
    donation_received_by = models.CharField(max_length=150, null=True, blank=True)
    reference_name = models.CharField(max_length=150, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    donation_amount_declared = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    donation_amount_paid = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(null=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    action = models.CharField(max_length=20)  # INSERT / UPDATE / DELETE
    action_at = models.DateTimeField(auto_now_add=True)
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")
    def __str__(self):
        return f"History of Donation {self.donation_id} - {self.action}"

class DonationPaymentBox_Hist(models.Model):
    id = models.AutoField(primary_key=True)

    # Link to main Payment record
    payment = models.ForeignKey(
        'DonationPaymentBox',
        on_delete=models.CASCADE,
        related_name='history'
    )

    # Copy ALL fields from the main table
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    donation_box = models.ForeignKey('DonationBox', on_delete=models.SET_NULL, null=True, blank=True)
    address = models.CharField(max_length=255, blank=True, null=True)

    opened_by = models.ForeignKey(
        'heart_charity.DonorVolunteer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )

    received_by = models.ForeignKey(
        'heart_charity.DonorVolunteer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.ForeignKey(
        Lookup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )

    date_time = models.DateTimeField(null=True, blank=True)
    i_witness = models.CharField(max_length=100, blank=True, null=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")

    # Extra fields for tracking what happened
    action = models.CharField(max_length=20)  # INSERT / UPDATE / DELETE
    action_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "DonationPaymentBox_Hist"

    def __str__(self):
        return f"History for Payment {self.payment.id} ({self.action})"

class UserRole_Hist(models.Model):
    # History table primary key
    hist_id = models.AutoField(primary_key=True)

    # Link back to main table
    user_role = models.ForeignKey(
        'UserRole',
        on_delete=models.CASCADE,
        related_name="history"
    )

    # Copy of all fields from main table
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    role = models.ForeignKey(UserModuleAccess, on_delete=models.SET_NULL, null=True, blank=True)

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')
    created_date = models.DateTimeField(null=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')
    updated_date = models.DateTimeField(null=True)
    deleted_by = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="%(class)s_deleted_by")
    # Audit for history
    action = models.CharField(max_length=20)   # INSERT / UPDATE / DELETE
    action_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"History of UserRole {self.user_role_id} - {self.action}"

from django.db import models
from django.contrib.auth.models import User


from django.conf import settings  # make sure you import this

class Module(models.Model):
    module_name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.module_name

from django.db import models
from django.contrib.auth.models import User

class Module(models.Model):
    module_name = models.CharField(max_length=100)
    def __str__(self):
        return self.module_name


class UserModuleAccess(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    role = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    can_access = models.BooleanField(default=False)
    can_add = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_view = models.BooleanField(default=False)

    class Meta:
        unique_together = ('module', 'role')

    def __str__(self):
        return f"{self.role or 'No Role'} - {self.module.module_name}"



from django.contrib.auth.models import User
from django.db import models

class UserRole(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.ForeignKey(UserModuleAccess,on_delete=models.SET_NULL,null=True,blank=True,related_name='user_roles')

    def __str__(self):
        return f"{self.user.username} - {self.role.role.name if self.role and self.role.role else 'No Role'}"

from django.db import models
from django.contrib.auth.models import User
from datetime import datetime, date


class DonorVolunteer(models.Model):

    BLOOD_GROUP_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]

    # Person Type (FK)
    person_type = models.ForeignKey(
    "Lookup",
    on_delete=models.SET_NULL,
    null=True,
    related_name="person_type_lookup"
)


    # Personal Details
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=10)
    date_of_birth = models.DateField()

    # Auto calculated age
    age = models.IntegerField(blank=True, null=True)

    blood_group = models.CharField(
        max_length=5, choices=BLOOD_GROUP_CHOICES, blank=True, null=True
    )

    contact_number = models.CharField(max_length=20)
    whatsapp_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(unique=True)

    # Donor Box ID
    donor_box_id = models.CharField(max_length=50, blank=True, null=True)

    # Address
    house_number = models.CharField(max_length=50)
    building_name = models.CharField(max_length=100, blank=True, null=True)
    landmark = models.CharField(max_length=100, blank=True, null=True)
    area = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    country = models.CharField(max_length=50, default='India')
    postal_code = models.CharField(max_length=20)

    # Native Place
    native_place = models.CharField(max_length=200, blank=True, null=True)
    native_postal_code = models.CharField(max_length=20, blank=True, null=True)

    id_type = models.ForeignKey(
        "Lookup",
        on_delete=models.SET_NULL,
        null=True,
        related_name="id_type_lookup"
)

    id_number = models.CharField( max_length=20 ,blank=True, null=True)
    id_proof_image = models.ImageField(upload_to='id_proofs/', blank=True, null=True)

    # PAN
    pan_number = models.CharField(max_length=20, blank=True, null=True)
    pan_card_image = models.ImageField(upload_to='pan_cards/', blank=True, null=True)

    # Audit Fields
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="donor_created_by"
    )
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="donor_updated_by"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ---------- AGE CALCULATION FIX ----------
    def calculate_age(self):

        # Convert string date to Python date object if required
        if isinstance(self.date_of_birth, str):
            try:
                self.date_of_birth = datetime.strptime(
                    self.date_of_birth, "%Y-%m-%d"
                ).date()
            except:
                return None

        today = date.today()
        return (
            today.year - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )

    def save(self, *args, **kwargs):
        if self.date_of_birth:
            self.age = self.calculate_age()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"



class LookupType(models.Model):
    type_name = models.CharField(max_length=100, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='lookup_type_created')
    created_date = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='lookup_type_updated')
    updated_date = models.DateTimeField(auto_now=True)

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

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="lookup_created"
    )
    created_date = models.DateTimeField(auto_now_add=True)

    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="lookup_updated"
    )
    updated_date = models.DateTimeField(auto_now=True)

    @property
    def formatted_id(self):
        return f"{self.id:03d}"

    def __str__(self):
        return f"{self.lookup_name} ({self.lookup_type.type_name})"












































from django.utils import timezone
from django.db.models.signals import pre_save
from django.dispatch import receiver

class Donation(models.Model):

    # 🔗 Multi-donor support — ManyToMany
    donors = models.ManyToManyField(
        'DonorVolunteer',
        limit_choices_to={'person_type__lookup_name': 'Donor'},
        related_name='donations'
    )

    # 💰 Donation Lookup Fields (NOW FIXED)
    donation_mode = models.ForeignKey(
        Lookup, on_delete=models.SET_NULL, null=True, related_name='donation_modes'
    )
    payment_method = models.ForeignKey(
        Lookup, on_delete=models.SET_NULL, null=True, related_name='payment_methods'
    )
    payment_status = models.ForeignKey(
        Lookup, on_delete=models.SET_NULL, null=True, related_name='payment_statuses'
    )
    donation_category = models.ForeignKey(
        Lookup, on_delete=models.SET_NULL, null=True, related_name='donation_categories'
    )

    # 💳 Payment Info
    transaction_id = models.CharField(max_length=50, blank=True, null=True)

    # 🧾 Receipt
    receipt_id = models.CharField(max_length=50, unique=True, blank=True, null=True)

    def __str__(self):
        donors_list = ", ".join(
            [f"{d.first_name} {d.last_name}" for d in self.donors.all()]
        )
        return f"Donation by {donors_list}"


# 🔹 Auto-generate unique receipt ID before saving
@receiver(pre_save, sender=Donation)
def generate_receipt_id(sender, instance, **kwargs):
    if not instance.receipt_id:
        prefix = "RCPT"
        year = timezone.now().year
        last_entry = Donation.objects.filter(receipt_id__startswith=f"{prefix}-{year}-").order_by('-id').first()

        if last_entry and last_entry.receipt_id:
            last_number = int(last_entry.receipt_id.split('-')[-1])
            new_number = last_number + 1
        else:
            new_number = 1

        instance.receipt_id = f"{prefix}-{year}-{new_number:04d}"




# models.py
# from django.contrib.auth.models import User
# from django.db import models

# class UserProfile(models.Model):
#     user = models.OneToOneField(User, on_delete=models.CASCADE)
#     is_deleted = models.BooleanField(default=False)



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

    def __str__(self):
        return f"{self.owner_name.first_name} {self.owner_name.last_name} - ₹{self.amount} ({self.donation_box.donation_id})"





class DonationBox(models.Model):
    donation_id = models.CharField(max_length=10, unique=True, editable=False)
    donation_box_name = models.CharField(max_length=100)
    qr_code = models.ImageField(upload_to='qr_images/', blank=True, null=True)
    location = models.CharField(max_length=255)
    status_choices = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
        ('Collected', 'Collected'),
        ('Pending', 'Pending'),
    ]
    status = models.CharField(max_length=20, choices=status_choices, default='Active')
    created_at = models.DateTimeField(default=timezone.now)

    def save(self, *args, **kwargs):
        # Auto-generate donation_id if not set
        if not self.donation_id:
            last_box = DonationBox.objects.all().order_by('id').last()
            if last_box:
                last_id = int(last_box.donation_id.split('_')[1])
                new_id = f"DO_{last_id + 1:04d}"
            else:
                new_id = "DO_0001"
            self.donation_id = new_id

        # Generate QR code containing donation details
        qr_data = f"Donation ID: {self.donation_id}\nBox Name: {self.donation_box_name}\nLocation: {self.location}"
        qr_img = qrcode.make(qr_data)
        buffer = BytesIO()
        qr_img.save(buffer, format='PNG')
        self.qr_code.save(f"{self.donation_id}_qr.png", File(buffer), save=False)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.donation_box_name} ({self.donation_id})"




from django.db import models

class Employee(models.Model):
    EMPLOYEE_TYPE_CHOICES = [
        ('permanent', 'Permanent'),
        ('contract', 'Contract'),
        ('intern', 'Intern'),
    ]

    ACCOUNT_TYPE_CHOICES = [
        ('savings', 'Savings'),
        ('current', 'Current'),
        ('salary', 'Salary'),
    ]

    # 🧩 Personal Details
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15)

    # 🏠 Contact Information
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=10)

    # 💼 Job Details
    department = models.CharField(max_length=100)
    designation = models.CharField(max_length=100)
    employee_type = models.CharField(max_length=20, choices=EMPLOYEE_TYPE_CHOICES)
    joining_date = models.DateField()

    # 🏦 Bank Details
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=30)
    ifsc_code = models.CharField(max_length=20)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)

    # 🕒 Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.middle_name or ''} {self.last_name}".strip()

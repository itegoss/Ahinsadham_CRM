from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from heart_charity.models import DonorVolunteer, LookupType, Lookup
from heart_charity.views import apply_column_filters, donor_mapping

class ColumnFilterTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="testuser", password="testpassword")
        
        # Create some LookupTypes
        self.person_type_lookup = LookupType.objects.create(type_name="Person Type")
        
        # Create lookups
        self.donor_type = Lookup.objects.create(lookup_name="Donor", lookup_type=self.person_type_lookup)
        self.volunteer_type = Lookup.objects.create(lookup_name="Volunteer", lookup_type=self.person_type_lookup)
        
        # Create Donor Volunteers
        DonorVolunteer.objects.create(
            first_name="Wagad",
            last_name="Visa",
            contact_number="1234567890",
            person_type=self.donor_type,
            address="Some address",
            city="Mumbai",
            state="Maharashtra",
            country="India",
            postal_code="400001",
        )
        DonorVolunteer.objects.create(
            first_name="Kutch",
            last_name="Visa",
            contact_number="0987654321",
            person_type=self.volunteer_type,
            address="Other address",
            city="Pune",
            state="Maharashtra",
            country="India",
            postal_code="411001",
        )

    def test_apply_column_filters_first_name(self):
        request = self.factory.get('/welcome/?donor_col_4=Wagad')
        queryset = DonorVolunteer.objects.all()
        filtered = apply_column_filters(queryset, request, 'donor', donor_mapping)
        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first().first_name, "Wagad")

    def test_apply_column_filters_person_type(self):
        request = self.factory.get('/welcome/?donor_col_3=Donor')
        queryset = DonorVolunteer.objects.all()
        filtered = apply_column_filters(queryset, request, 'donor', donor_mapping)
        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first().first_name, "Wagad")

    def test_apply_column_filters_combined(self):
        request = self.factory.get('/welcome/?donor_col_4=Wagad&donor_col_6=Visa')
        queryset = DonorVolunteer.objects.all()
        filtered = apply_column_filters(queryset, request, 'donor', donor_mapping)
        self.assertEqual(filtered.count(), 1)
        
        request_mismatch = self.factory.get('/welcome/?donor_col_4=Kutch&donor_col_19=Mumbai') # Mumbai is city (col 19)
        filtered_mismatch = apply_column_filters(queryset, request_mismatch, 'donor', donor_mapping)
        self.assertEqual(filtered_mismatch.count(), 0)

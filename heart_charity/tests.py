from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.urls import reverse
from heart_charity.models import DonorVolunteer, LookupType, Lookup, Donation
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


class UTMTrackingTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="testuser", password="testpassword")
        
        # Ensure we have LookupType and Lookup setup
        self.payment_status_type, _ = LookupType.objects.get_or_create(type_name="Payment Status")
        self.pending_status, _ = Lookup.objects.get_or_create(lookup_name="Pending", lookup_type=self.payment_status_type)

    def test_utm_middleware_saves_params_in_session(self):
        # Create request with UTM parameters
        request = self.factory.get('/schemes/?utm_source=instagram&utm_medium=social&utm_campaign=schemes_promotion&utm_content=reel&utm_term=test_term&utm_id=123')
        
        # We need SessionMiddleware to populate request.session
        middleware = SessionMiddleware(get_response=lambda r: r)
        middleware.process_request(request)
        
        from heart_charity.middleware import UTMAttributionMiddleware
        utm_middleware = UTMAttributionMiddleware(get_response=lambda r: r)
        utm_middleware(request)
        
        self.assertEqual(request.session.get('utm_source'), 'instagram')
        self.assertEqual(request.session.get('utm_medium'), 'social')
        self.assertEqual(request.session.get('utm_campaign'), 'schemes_promotion')
        self.assertEqual(request.session.get('utm_content'), 'reel')
        self.assertEqual(request.session.get('utm_term'), 'test_term')
        self.assertEqual(request.session.get('utm_id'), '123')

    def test_payment_verify_attributes_utm_and_sets_payment_status(self):
        # We will mock the request and session for payment_verify
        # Create a donor, as required by donation creation
        person_type, _ = LookupType.objects.get_or_create(type_name="Person Type")
        donor_type, _ = Lookup.objects.get_or_create(lookup_name="Donor", lookup_type=person_type)
        donor = DonorVolunteer.objects.create(
            first_name="John",
            last_name="Doe",
            contact_number="9876543210",
            email="john@example.com",
            person_type=donor_type
        )
        
        # Mock payment_verify view call
        from django.test import Client
        c = Client()
        session = c.session
        session['donation_data'] = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'mobile_number': '9876543210',
            'donation_amount': '500.00',
        }
        session['razorpay_order'] = {
            'id': 'mock_order_123',
            'amount': 50000,
        }
        # Populate session with UTM parameters
        session['utm_source'] = 'instagram'
        session['utm_medium'] = 'social'
        session['utm_campaign'] = 'schemes_promotion'
        session['utm_content'] = 'reel'
        session.save()
        
        response = c.post(reverse('payment_verify'), {
            'is_mock': 'true',
            'razorpay_payment_id': 'mock_payment_123',
            'razorpay_order_id': 'mock_order_123',
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Verify donation record was created with UTM values in place_of_donation
        donation = Donation.objects.filter(donor=donor).first()
        self.assertIsNotNone(donation)
        self.assertEqual(donation.place_of_donation, 'instagram, social, schemes_promotion, reel')
        
        # Verify payment status is set to Successful lookup
        self.assertEqual(donation.payment_status.lookup_name, 'Successful')
        self.assertEqual(donation.payment_status.lookup_type.type_name, 'Payment Status')
        
        # Verify session has cleared the UTM values
        session_after = c.session
        self.assertNotIn('utm_source', session_after)
        self.assertNotIn('utm_medium', session_after)
        self.assertNotIn('utm_campaign', session_after)
        self.assertNotIn('utm_content', session_after)

    def test_payment_verify_no_utm_params(self):
        # We will mock the request and session for payment_verify without UTM params
        person_type, _ = LookupType.objects.get_or_create(type_name="Person Type")
        donor_type, _ = Lookup.objects.get_or_create(lookup_name="Donor", lookup_type=person_type)
        donor = DonorVolunteer.objects.create(
            first_name="Jane",
            last_name="Doe",
            contact_number="9876543211",
            email="jane@example.com",
            person_type=donor_type
        )
        
        from django.test import Client
        c = Client()
        session = c.session
        session['donation_data'] = {
            'first_name': 'Jane',
            'last_name': 'Doe',
            'email': 'jane@example.com',
            'mobile_number': '9876543211',
            'donation_amount': '500.00',
        }
        session['razorpay_order'] = {
            'id': 'mock_order_456',
            'amount': 50000,
        }
        session.save()
        
        response = c.post(reverse('payment_verify'), {
            'is_mock': 'true',
            'razorpay_payment_id': 'mock_payment_456',
            'razorpay_order_id': 'mock_order_456',
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Verify donation record was created with place_of_donation as None (no UTMs)
        donation = Donation.objects.filter(donor=donor).first()
        self.assertIsNotNone(donation)
        self.assertIsNone(donation.place_of_donation)


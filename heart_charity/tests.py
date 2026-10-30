from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.urls import reverse
from heart_charity.models import DonorVolunteer, LookupType, Lookup, Donation, OwnerDetail
from heart_charity.views import apply_column_filters, donor_mapping, owner_mapping

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

        OwnerDetail.objects.create(
            business_name="Mahavir Emporium",
            gst_number="24AAAAA0000A1Z5",
            salutation="Mr.",
            first_name="Kantilal",
            middle_name="H",
            last_name="Shah",
            gender="Male",
            blood_group="O+",
            contact_number="9876543210",
            whatsapp_number="9876543210",
            email="kantilal@example.com",
            city="Ahmedabad",
            country="India",
            state="Gujarat",
            postal_code="380001",
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

    def test_apply_column_filters_owner_details(self):
        # col 3: business_name, col 6: first_name, col 20: city
        request = self.factory.get('/welcome/?owner_col_3=Mahavir&owner_col_6=Kantilal&owner_col_20=Ahmedabad')
        queryset = OwnerDetail.objects.all()
        filtered = apply_column_filters(queryset, request, 'owner', owner_mapping)
        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first().business_name, "Mahavir Emporium")
        self.assertEqual(filtered.first().city, "Ahmedabad")

        # Mismatch test
        request_mismatch = self.factory.get('/welcome/?owner_col_3=Mahavir&owner_col_20=Surat')
        filtered_mismatch = apply_column_filters(queryset, request_mismatch, 'owner', owner_mapping)
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


from heart_charity.models import DonationBox, Employee, OwnerDetail
from heart_charity.admin import DonationBoxAdmin
from django.contrib.admin.sites import AdminSite
from django.test import override_settings

@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class DonationBoxRelationshipTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="adminuser", password="adminpassword", email="admin@test.com")
        self.client.login(username="adminuser", password="adminpassword")

        # Create employees
        self.emp1 = Employee.objects.create(
            first_name="Ramesh",
            last_name="Kumar",
            contact_number="9820011223"
        )
        self.emp2 = Employee.objects.create(
            first_name="Suresh",
            last_name="Patel",
            contact_number="9820044556"
        )

        # Create owners
        self.owner1 = OwnerDetail.objects.create(
            business_name="Shreeji Sweets",
            first_name="Jay",
            last_name="Shah",
            contact_number="9876501234"
        )
        self.owner2 = OwnerDetail.objects.create(
            business_name="Arihant Enterprises",
            first_name="Bhavin",
            last_name="Mehta",
            contact_number="9876505678"
        )

    def test_create_donation_box_with_collector_and_owner(self):
        response = self.client.post(reverse('add_donation_box'), {
            'key_id': 'KEY_001',
            'box_size': 'medium',
            'status': 'Active',
            'collector': str(self.emp1.id),
            'owner_detail': str(self.owner1.id),
            'box_percentage': '15.00',
        })
        self.assertEqual(response.status_code, 302)

        box = DonationBox.objects.filter(key_id='KEY_001').first()
        self.assertIsNotNone(box)
        self.assertEqual(box.collector_id, self.emp1.id)
        self.assertEqual(box.collector, self.emp1)
        self.assertEqual(box.owner_detail_id, self.owner1.id)
        self.assertEqual(box.owner_detail, self.owner1)
        self.assertEqual(box.collector_display_name, "Ramesh Kumar")
        self.assertIn("Shreeji Sweets", box.owner_display_name)

        # Verify OwnerDetail.donor_box two-way relationship
        self.owner1.refresh_from_db()
        self.assertEqual(self.owner1.donor_box_id, box.id)

    def test_edit_donation_box_updates_relationships_and_syncs_owner(self):
        box = DonationBox.objects.create(
            key_id='KEY_002',
            box_size='small',
            status='Active',
            collector=self.emp1,
            owner_detail=self.owner1,
            box_percentage=10.00,
        )
        self.owner1.donor_box = box
        self.owner1.save()

        # Edit to switch collector to emp2 and owner to owner2
        response = self.client.post(reverse('edit_donation_box', args=[box.id]), {
            'key_id': 'KEY_002_UPDATED',
            'box_size': 'large',
            'status': 'Active',
            'collector': str(self.emp2.id),
            'owner_detail': str(self.owner2.id),
            'box_percentage': '20.00',
        })
        self.assertEqual(response.status_code, 302)

        box.refresh_from_db()
        self.assertEqual(box.key_id, 'KEY_002_UPDATED')
        self.assertEqual(box.collector_id, self.emp2.id)
        self.assertEqual(box.owner_detail_id, self.owner2.id)

        # Verify previous owner unlinked and new owner linked
        self.owner1.refresh_from_db()
        self.owner2.refresh_from_db()
        self.assertIsNone(self.owner1.donor_box)
        self.assertEqual(self.owner2.donor_box_id, box.id)

    def test_existing_unlinked_records_preserve_data(self):
        box = DonationBox.objects.create(
            key_id='KEY_LEGACY',
            box_size='medium',
            status='Active',
            box_owner='vidyaa',
            box_percentage=5.00,
        )
        self.assertIsNone(box.collector_id)
        self.assertIsNone(box.owner_detail_id)
        self.assertEqual(box.box_owner, 'vidyaa')
        self.assertEqual(box.collector_display_name, 'vidyaa')
        self.assertEqual(box.owner_display_name, '')

    def test_admin_display_methods(self):
        site = AdminSite()
        box_admin = DonationBoxAdmin(DonationBox, site)

        # With relationships
        box_with_relations = DonationBox.objects.create(
            key_id='KEY_ADMIN_1',
            box_size='medium',
            status='Active',
            collector=self.emp1,
            owner_detail=self.owner1,
            box_percentage=10.00,
        )
        self.assertEqual(box_admin.get_collector_name(box_with_relations), "Ramesh Kumar")
        self.assertEqual(box_admin.get_owner_name(box_with_relations), "Shreeji Sweets (Jay Shah)")

        # Without relationships but legacy text
        box_legacy = DonationBox.objects.create(
            key_id='KEY_ADMIN_2',
            box_size='medium',
            status='Active',
            box_owner='vidyaa',
            box_percentage=10.00,
        )
        self.assertEqual(box_admin.get_collector_name(box_legacy), "vidyaa")
        self.assertEqual(box_admin.get_owner_name(box_legacy), "—")

    def test_edit_view_get_retains_selection(self):
        box = DonationBox.objects.create(
            key_id='KEY_EDIT_FORM',
            box_size='medium',
            status='Active',
            collector=self.emp1,
            owner_detail=self.owner1,
            box_percentage=12.00,
        )
        response = self.client.get(reverse('edit_donation_box', args=[box.id]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        # Check collector selected
        self.assertIn(f'value="{self.emp1.id}" selected', content)
        # Check owner selected
        self.assertIn(f'value="{self.owner1.id}" selected', content)



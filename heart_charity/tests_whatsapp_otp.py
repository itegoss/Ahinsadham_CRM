import datetime
import hashlib
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone

from heart_charity.models import UserRole, UserModuleAccess, Module, WhatsAppOTP
from heart_charity.views import find_eligible_user_by_mobile
from heart_charity.whatsapp_service import (
    normalize_phone_10_digits,
    validate_and_format_phone,
    send_login_otp_whatsapp,
)


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
)
class WhatsAppOTPLoginTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.test_mobile = "9876543210"

        # Create test user
        self.user = User.objects.create_user(
            username="ahinsa_test_user",
            email="testuser@ahinsadham.org",
            password="SecurePassword@123",
            first_name="Varsha",
            last_name="Tester",
        )

        # Create module & role
        self.module = Module.objects.create(module_name="Donor Management")
        self.role = UserModuleAccess.objects.create(
            module=self.module,
            name="Donor Coordinator",
            can_access=True,
            can_add=True,
            can_edit=True,
        )

        # Create UserRole with assigned mobile_number
        self.user_role = UserRole.objects.create(
            user=self.user,
            role=self.role,
            mobile_number=self.test_mobile,
        )

    # --------------------------------------------------------------------------
    # Helper & Normalization Tests
    # --------------------------------------------------------------------------
    def test_normalize_phone_10_digits(self):
        self.assertEqual(normalize_phone_10_digits("9876543210"), "9876543210")
        self.assertEqual(normalize_phone_10_digits("+91 98765-43210"), "9876543210")
        self.assertEqual(normalize_phone_10_digits("919876543210"), "9876543210")
        self.assertEqual(normalize_phone_10_digits("09876543210"), "9876543210")
        self.assertIsNone(normalize_phone_10_digits("12345"))
        self.assertIsNone(normalize_phone_10_digits(""))

    def test_validate_and_format_phone(self):
        self.assertEqual(validate_and_format_phone("9876543210"), "919876543210")
        self.assertEqual(validate_and_format_phone("+91 98765-43210"), "919876543210")
        self.assertEqual(validate_and_format_phone("919876543210"), "919876543210")

    def test_find_eligible_user_by_mobile(self):
        # 1. Via UserRole mobile_number
        u, p10 = find_eligible_user_by_mobile("9876543210")
        self.assertEqual(u, self.user)
        self.assertEqual(p10, "9876543210")

        # 2. With +91 format
        u, p10 = find_eligible_user_by_mobile("+91 98765 43210")
        self.assertEqual(u, self.user)

        # 3. Via Username directly
        u2 = User.objects.create_user(username="9112233445", password="Pass@123")
        u_found, p_found = find_eligible_user_by_mobile("9112233445")
        self.assertEqual(u_found, u2)

        # 4. Unregistered phone number
        u_none, p_none = find_eligible_user_by_mobile("9999999999")
        self.assertIsNone(u_none)
        self.assertEqual(p_none, "9999999999")

    # --------------------------------------------------------------------------
    # 1. Registered Mobile Receives WhatsApp OTP
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_1_registered_mobile_receives_whatsapp_otp(self, mock_wa):
        mock_wa.return_value = {"success": True, "message_id": "wa_msg_101"}

        response = self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": self.test_mobile},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertTrue(mock_wa.called)

        # Verify arguments passed to WhatsApp service
        args, kwargs = mock_wa.call_args
        phone_arg = args[0]
        otp_arg = args[1]
        self.assertEqual(phone_arg, self.test_mobile)
        self.assertEqual(len(otp_arg), 6)
        self.assertTrue(otp_arg.isdigit())

        # Verify secure OTP hashing in DB
        otp_record = WhatsAppOTP.objects.filter(mobile=self.test_mobile, is_used=False).first()
        self.assertIsNotNone(otp_record)
        self.assertNotEqual(otp_record.otp_hash, otp_arg)
        expected_hash = hashlib.sha256(f"{otp_arg}:{otp_record.otp_salt}".encode()).hexdigest()
        self.assertEqual(otp_record.otp_hash, expected_hash)
        self.assertEqual(otp_record.user, self.user)

    # --------------------------------------------------------------------------
    # 2. Correct OTP Successfully Logs in the User
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_2_correct_otp_successfully_logs_in_user(self, mock_wa):
        mock_wa.return_value = {"success": True, "message_id": "wa_msg_102"}

        # Request OTP
        self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": self.test_mobile},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        otp_record = WhatsAppOTP.objects.filter(mobile=self.test_mobile, is_used=False).first()
        test_plain_otp = "654321"
        salt = otp_record.otp_salt
        otp_record.otp_hash = hashlib.sha256(f"{test_plain_otp}:{salt}".encode()).hexdigest()
        otp_record.save()

        # Submit verification
        res_verify = self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": self.test_mobile, "otp": test_plain_otp},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_verify.status_code, 200)
        data = res_verify.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("redirect_url"), reverse("welcome"))

        # Verify authenticated session
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.id)

    # --------------------------------------------------------------------------
    # 3. Incorrect OTP is Rejected
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_3_incorrect_otp_is_rejected(self, mock_wa):
        mock_wa.return_value = {"success": True}
        self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": self.test_mobile},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        res_wrong = self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": self.test_mobile, "otp": "000000"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_wrong.status_code, 400)
        data = res_wrong.json()
        self.assertFalse(data.get("success"))
        self.assertIn("Invalid verification code", data.get("error"))

        # Verify NOT logged in
        self.assertNotIn("_auth_user_id", self.client.session)

    # --------------------------------------------------------------------------
    # 4. Expired OTP is Rejected
    # --------------------------------------------------------------------------
    def test_4_expired_otp_is_rejected(self):
        otp_val = "123456"
        salt = "testsalt123"
        WhatsAppOTP.objects.create(
            mobile=self.test_mobile,
            otp_hash=hashlib.sha256(f"{otp_val}:{salt}".encode()).hexdigest(),
            otp_salt=salt,
            user=self.user,
            expires_at=timezone.now() - datetime.timedelta(seconds=10),
            is_used=False,
        )

        res_expired = self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": self.test_mobile, "otp": otp_val},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_expired.status_code, 400)
        data = res_expired.json()
        self.assertFalse(data.get("success"))
        self.assertIn("expired", data.get("error").lower())
        self.assertNotIn("_auth_user_id", self.client.session)

    # --------------------------------------------------------------------------
    # 5. Used OTP Cannot be Reused
    # --------------------------------------------------------------------------
    def test_5_used_otp_cannot_be_reused(self):
        otp_val = "123456"
        salt = "testsalt123"
        WhatsAppOTP.objects.create(
            mobile=self.test_mobile,
            otp_hash=hashlib.sha256(f"{otp_val}:{salt}".encode()).hexdigest(),
            otp_salt=salt,
            user=self.user,
            expires_at=timezone.now() + datetime.timedelta(minutes=5),
            is_used=True,  # Already used
        )

        res_reuse = self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": self.test_mobile, "otp": otp_val},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_reuse.status_code, 400)
        data = res_reuse.json()
        self.assertFalse(data.get("success"))
        self.assertIn("No active OTP found", data.get("error"))

    # --------------------------------------------------------------------------
    # 6. Previous OTP Becomes Invalid After Resend
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_6_previous_otp_becomes_invalid_after_resend(self, mock_wa):
        mock_wa.return_value = {"success": True}

        # First request
        self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": self.test_mobile},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        first_record = WhatsAppOTP.objects.filter(mobile=self.test_mobile, is_used=False).first()
        self.assertIsNotNone(first_record)

        # Fast forward time beyond cooldown
        first_record.created_at = timezone.now() - datetime.timedelta(seconds=65)
        first_record.save()

        # Resend OTP
        self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": self.test_mobile},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        # Refresh first record: should now be marked as is_used=True (invalidated)
        first_record.refresh_from_db()
        self.assertTrue(first_record.is_used)

        # Only one active OTP should exist
        active_count = WhatsAppOTP.objects.filter(mobile=self.test_mobile, is_used=False).count()
        self.assertEqual(active_count, 1)

    # --------------------------------------------------------------------------
    # 7. Resend Cooldown Enforced (60 Seconds)
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_7_resend_cooldown_enforced(self, mock_wa):
        mock_wa.return_value = {"success": True}

        # 1st request succeeds
        res1 = self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": self.test_mobile},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(mock_wa.call_count, 1)

        # Immediate 2nd request blocked by cooldown
        res2 = self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": self.test_mobile},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res2.status_code, 429)
        data = res2.json()
        self.assertFalse(data.get("success"))
        self.assertIn("Please wait", data.get("error"))
        # WhatsApp delivery function not called again
        self.assertEqual(mock_wa.call_count, 1)

    # --------------------------------------------------------------------------
    # 8. Incorrect OTP Attempt Limits Work (Max 3)
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_8_incorrect_otp_attempt_limits_work(self, mock_wa):
        mock_wa.return_value = {"success": True}
        self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": self.test_mobile},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        # Attempt 1
        res1 = self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": self.test_mobile, "otp": "111111"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res1.json().get("remaining_attempts"), 2)

        # Attempt 2
        res2 = self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": self.test_mobile, "otp": "222222"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res2.json().get("remaining_attempts"), 1)

        # Attempt 3 (final attempt exceeded)
        res3 = self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": self.test_mobile, "otp": "333333"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res3.json().get("remaining_attempts"), 0)

        # Verify record is invalidated
        otp_rec = WhatsAppOTP.objects.filter(mobile=self.test_mobile).order_by("-id").first()
        self.assertTrue(otp_rec.is_used)

    # --------------------------------------------------------------------------
    # 9. Unregistered Users Cannot Log In (Anti-Enumeration)
    # --------------------------------------------------------------------------
    # 9. New Mobile Auto-Registration and Persistent Login (Scenarios A, B, C, D)
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_9_new_mobile_registration_and_persistent_login(self, mock_wa):
        mock_wa.return_value = {"success": True}
        new_mobile = "9988776655"

        initial_count = User.objects.count()

        # Step 1: Send OTP to new mobile number -> succeeds, but user is NOT created yet
        res = self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": new_mobile},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(mock_wa.called)
        self.assertTrue(WhatsAppOTP.objects.filter(mobile=new_mobile, is_used=False).exists())
        self.assertEqual(User.objects.count(), initial_count)
        self.assertFalse(User.objects.filter(username=new_mobile).exists())

        # Step 2 (Scenario D): Enter incorrect OTP -> rejected, NO user created
        res_fail = self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": new_mobile, "otp": "000000"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_fail.status_code, 400)
        self.assertEqual(User.objects.count(), initial_count)
        self.assertFalse(User.objects.filter(username=new_mobile).exists())

        # Step 3 (Scenario A): Enter correct OTP -> user created, mobile saved in UserRole, logged in
        otp_rec = WhatsAppOTP.objects.filter(mobile=new_mobile, is_used=False).first()
        otp_rec.otp_hash = hashlib.sha256(f"123456:{otp_rec.otp_salt}".encode()).hexdigest()
        otp_rec.save(update_fields=["otp_hash"])

        res_v = self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": new_mobile, "otp": "123456"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_v.status_code, 200)
        self.assertEqual(User.objects.count(), initial_count + 1)
        created_user = User.objects.get(username=new_mobile)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(created_user.id))

        # Check UserRole has mobile_number permanently saved
        self.assertEqual(created_user.userrole.mobile_number, new_mobile)

        # Step 4 (Scenario B & C): Log out, log in again -> existing user used, user count unchanged
        self.client.logout()
        WhatsAppOTP.objects.filter(mobile=new_mobile).delete()

        res_resend = self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": new_mobile},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_resend.status_code, 200)

        otp_rec_2 = WhatsAppOTP.objects.filter(mobile=new_mobile, is_used=False).first()
        otp_rec_2.otp_hash = hashlib.sha256(f"123456:{otp_rec_2.otp_salt}".encode()).hexdigest()
        otp_rec_2.save(update_fields=["otp_hash"])

        res_v2 = self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": new_mobile, "otp": "123456"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_v2.status_code, 200)
        self.assertEqual(User.objects.count(), initial_count + 1)  # Strictly unchanged!
        self.assertEqual(self.client.session.get("_auth_user_id"), str(created_user.id))

    # --------------------------------------------------------------------------
    # 10. WhatsApp API Failures Handled Correctly
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_10_whatsapp_api_failures_handled(self, mock_wa):
        mock_wa.return_value = {"success": False, "error": "11za network failure"}

        res = self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": self.test_mobile},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 502)
        data = res.json()
        self.assertFalse(data.get("success"))
        self.assertIn("11za network failure", data.get("error"))

    # --------------------------------------------------------------------------
    # 11. Existing Roles and Permissions Remain Unchanged
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_11_existing_roles_and_permissions_preserved(self, mock_wa):
        mock_wa.return_value = {"success": True}
        self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": self.test_mobile},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        otp_rec = WhatsAppOTP.objects.filter(mobile=self.test_mobile, is_used=False).first()
        otp_rec.otp_hash = hashlib.sha256(f"123456:{otp_rec.otp_salt}".encode()).hexdigest()
        otp_rec.save()

        self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": self.test_mobile, "otp": "123456"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        logged_user = User.objects.get(id=int(self.client.session["_auth_user_id"]))
        self.assertEqual(logged_user.userrole.role.name, "Donor Coordinator")
        self.assertTrue(logged_user.userrole.role.can_access)
        self.assertTrue(logged_user.userrole.role.can_add)

    # --------------------------------------------------------------------------
    # 12. Existing Password Login Continues Working
    # --------------------------------------------------------------------------
    def test_12_existing_password_login_continues_working(self):
        login_success = self.client.login(username="ahinsa_test_user", password="SecurePassword@123")
        self.assertTrue(login_success)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.id)

    # --------------------------------------------------------------------------
    # 13. Existing Dashboard Redirects Work Correctly
    # --------------------------------------------------------------------------
    def test_13_dashboard_redirects_work(self):
        self.client.login(username="ahinsa_test_user", password="SecurePassword@123")
        # Accessing login page while authenticated redirects to welcome
        res = self.client.get(reverse("login"))
        self.assertEqual(res.status_code, 302)
        self.assertRedirects(res, reverse("welcome"))

    # --------------------------------------------------------------------------
    # 14. Different Mobile Formats Map to the Same User
    # --------------------------------------------------------------------------
    def test_14_different_mobile_formats_map_to_same_user(self):
        formats = [
            f"+91 {self.test_mobile}",
            f"91{self.test_mobile}",
            f"0{self.test_mobile}",
            self.test_mobile,
        ]
        for fmt in formats:
            matched_user, p10 = find_eligible_user_by_mobile(fmt)
            self.assertEqual(matched_user, self.user, f"Failed matching format: {fmt}")
            self.assertEqual(p10, self.test_mobile)


    # --------------------------------------------------------------------------
    # 15. User Requirement Scenario 1: First-time Login Creates Own Account
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_15_scenario_1_first_time_login_creates_own_account(self, mock_wa):
        mock_wa.return_value = {"success": True}
        mobile_1 = "9820000001"
        self.assertFalse(User.objects.filter(username=mobile_1).exists())

        # Send OTP
        res_send = self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": mobile_1},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_send.status_code, 200)

        # Setup OTP hash
        otp_rec = WhatsAppOTP.objects.filter(mobile=mobile_1, is_used=False).first()
        otp_rec.otp_hash = hashlib.sha256(f"123456:{otp_rec.otp_salt}".encode()).hexdigest()
        otp_rec.save()

        # Verify OTP
        res_ver = self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": mobile_1, "otp": "123456"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_ver.status_code, 200)

        # Verify new user created
        new_u = User.objects.filter(username=mobile_1).first()
        self.assertIsNotNone(new_u)
        self.assertEqual(int(self.client.session["_auth_user_id"]), new_u.id)
        # Verify user is NOT superuser or staff
        self.assertFalse(new_u.is_superuser)
        self.assertFalse(new_u.is_staff)
        self.assertTrue(new_u.is_active)
        self.assertEqual(new_u.userrole.mobile_number, mobile_1)

    # --------------------------------------------------------------------------
    # 16. User Requirement Scenario 2: Returning User Authenticates Existing Account
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_16_scenario_2_returning_user_login(self, mock_wa):
        mock_wa.return_value = {"success": True}
        mobile_1 = "9820000001"

        # Create existing user with this mobile
        existing_u = User.objects.create_user(username=mobile_1, is_active=True)
        UserRole.objects.create(user=existing_u, mobile_number=mobile_1, role=self.role)

        initial_user_count = User.objects.count()

        # Send OTP
        res_send = self.client.post(
            reverse("send_whatsapp_login_otp"),
            {"mobile": mobile_1},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_send.status_code, 200)

        # Verify OTP
        otp_rec = WhatsAppOTP.objects.filter(mobile=mobile_1, is_used=False).first()
        otp_rec.otp_hash = hashlib.sha256(f"123456:{otp_rec.otp_salt}".encode()).hexdigest()
        otp_rec.save()

        res_ver = self.client.post(
            reverse("verify_whatsapp_login_otp"),
            {"mobile": mobile_1, "otp": "123456"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_ver.status_code, 200)

        # User count must NOT change (no duplicate user)
        self.assertEqual(User.objects.count(), initial_user_count)
        self.assertEqual(int(self.client.session["_auth_user_id"]), existing_u.id)
        # Permissions and role preserved
        self.assertEqual(existing_u.userrole.role, self.role)

    # --------------------------------------------------------------------------
    # 17. User Requirement Scenario 3: Different Mobile Gets Separate Account
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_17_scenario_3_different_mobile_gets_separate_account(self, mock_wa):
        mock_wa.return_value = {"success": True}
        mob_a = "9820000011"
        mob_b = "9820000022"

        # User A registers
        self.client.post(reverse("send_whatsapp_login_otp"), {"mobile": mob_a}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        otp_a = WhatsAppOTP.objects.filter(mobile=mob_a, is_used=False).first()
        otp_a.otp_hash = hashlib.sha256(f"111111:{otp_a.otp_salt}".encode()).hexdigest()
        otp_a.save()
        self.client.post(reverse("verify_whatsapp_login_otp"), {"mobile": mob_a, "otp": "111111"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        user_a = User.objects.get(username=mob_a)
        self.client.logout()

        # User B registers
        self.client.post(reverse("send_whatsapp_login_otp"), {"mobile": mob_b}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        otp_b = WhatsAppOTP.objects.filter(mobile=mob_b, is_used=False).first()
        otp_b.otp_hash = hashlib.sha256(f"222222:{otp_b.otp_salt}".encode()).hexdigest()
        otp_b.save()
        self.client.post(reverse("verify_whatsapp_login_otp"), {"mobile": mob_b, "otp": "222222"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        user_b = User.objects.get(username=mob_b)

        # Confirm distinct accounts
        self.assertNotEqual(user_a.id, user_b.id)
        self.assertNotEqual(user_a.username, user_b.username)
        self.assertEqual(user_a.userrole.mobile_number, mob_a)
        self.assertEqual(user_b.userrole.mobile_number, mob_b)

    # --------------------------------------------------------------------------
    # 18. User Requirement Scenario 4: Existing User with Linked Mobile Number
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_18_scenario_4_existing_email_user_with_linked_mobile(self, mock_wa):
        mock_wa.return_value = {"success": True}
        mob_linked = "9820000033"

        # Existing employee/email account
        email_u = User.objects.create_user(
            username="accounts_staff",
            email="staff@ahinsadham.org",
            first_name="Staff",
            last_name="Member"
        )
        UserRole.objects.create(user=email_u, mobile_number=mob_linked)

        total_users = User.objects.count()

        # Login with linked mobile
        self.client.post(reverse("send_whatsapp_login_otp"), {"mobile": mob_linked}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        otp_rec = WhatsAppOTP.objects.filter(mobile=mob_linked, is_used=False).first()
        otp_rec.otp_hash = hashlib.sha256(f"333333:{otp_rec.otp_salt}".encode()).hexdigest()
        otp_rec.save()

        res = self.client.post(reverse("verify_whatsapp_login_otp"), {"mobile": mob_linked, "otp": "333333"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(res.status_code, 200)

        # Must authenticate the existing email account without creating duplicate
        self.assertEqual(User.objects.count(), total_users)
        self.assertEqual(int(self.client.session["_auth_user_id"]), email_u.id)

    # --------------------------------------------------------------------------
    # 19. User Requirement Scenario 5: Superuser Protection
    # --------------------------------------------------------------------------
    @patch("heart_charity.views.send_login_otp_whatsapp")
    def test_19_scenario_5_superuser_protection(self, mock_wa):
        mock_wa.return_value = {"success": True}

        # Existing superuser account
        superuser = User.objects.create_superuser(
            username="sangalevarsha04",
            email="sangalevarsha04@gmail.com",
            password="SuperPassword!123"
        )
        UserRole.objects.create(user=superuser, mobile_number=None)

        # Normal WhatsApp user enters 7798354386
        mob_user = "7798354386"
        self.client.post(reverse("send_whatsapp_login_otp"), {"mobile": mob_user}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        otp_rec = WhatsAppOTP.objects.filter(mobile=mob_user, is_used=False).first()
        otp_rec.otp_hash = hashlib.sha256(f"777777:{otp_rec.otp_salt}".encode()).hexdigest()
        otp_rec.save()

        res = self.client.post(reverse("verify_whatsapp_login_otp"), {"mobile": mob_user, "otp": "777777"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(res.status_code, 200)

        # CONFIRM: Logged in user is NOT the superuser!
        logged_user_id = int(self.client.session["_auth_user_id"])
        self.assertNotEqual(logged_user_id, superuser.id)

        # Superuser account remains unchanged
        superuser.refresh_from_db()
        self.assertTrue(superuser.is_superuser)
        self.assertEqual(superuser.username, "sangalevarsha04")
        self.assertEqual(superuser.email, "sangalevarsha04@gmail.com")

        # The authenticated user has their own separate account
        mobile_auth_user = User.objects.get(id=logged_user_id)
        self.assertFalse(mobile_auth_user.is_superuser)
        self.assertFalse(mobile_auth_user.is_staff)
        self.assertNotEqual(mobile_auth_user.email, "sangalevarsha04@gmail.com")
        self.assertEqual(mobile_auth_user.userrole.mobile_number, mob_user)

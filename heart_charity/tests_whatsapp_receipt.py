import json
import os
import requests
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.files.storage import default_storage
from django.contrib.auth.models import User

from heart_charity.models import (
    Donation,
    DonorVolunteer,
    DonationBox,
    DonationPaymentBox,
    LookupType,
    Lookup,
    DonationWhatsAppReceipt,
)
from heart_charity.whatsapp_service import (
    validate_and_format_phone,
    normalize_phone_10_digits,
    send_donation_receipt_whatsapp,
    send_login_otp_whatsapp,
)
from heart_charity.receipt_service import (
    generate_receipt_pdf_bytes,
    get_or_upload_receipt_pdf,
    get_accessible_gcs_url,
    extract_donor_details,
    deliver_donation_receipt_whatsapp,
    retry_failed_whatsapp_receipt,
)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class WhatsAppReceiptDeliveryTests(TestCase):
    def setUp(self):
        # Create standard lookups
        cat_type, _ = LookupType.objects.get_or_create(type_name="Donation Category")
        self.category, _ = Lookup.objects.get_or_create(lookup_name="General", lookup_type=cat_type)

        method_type, _ = LookupType.objects.get_or_create(type_name="Payment Method")
        self.payment_method, _ = Lookup.objects.get_or_create(lookup_name="Online", lookup_type=method_type)

        status_type, _ = LookupType.objects.get_or_create(type_name="Payment Status")
        self.payment_status, _ = Lookup.objects.get_or_create(lookup_name="Successful", lookup_type=status_type)

        # Create donor
        self.donor = DonorVolunteer.objects.create(
            first_name="Ramesh",
            last_name="Shah",
            pan_number="ABCDE1234F",
            contact_number="9876543210",
            whatsapp_number="9876543210",
            email="ramesh.shah@example.com",
            city="Mumbai",
            state="Maharashtra",
        )

        # Create verified donation
        self.donation = Donation.objects.create(
            donor=self.donor,
            display_name="Ramesh Shah",
            donation_date=timezone.now().date(),
            donation_amount_paid=2500.00,
            donation_amount_declared=2500.00,
            donation_category=self.category,
            payment_method=self.payment_method,
            payment_status=self.payment_status,
            transaction_id="pay_test_12345",
            receipt_id="ACH-2026-0001",
            verified=True,
        )

    # --------------------------------------------------------------------------
    # 1. Phone Validation & Country Code Tests
    # --------------------------------------------------------------------------
    def test_phone_normalization_and_formatting(self):
        """Test Indian mobile numbers are properly formatted with 91 prefix."""
        self.assertEqual(validate_and_format_phone("9876543210"), "919876543210")
        self.assertEqual(validate_and_format_phone("+919876543210"), "919876543210")
        self.assertEqual(validate_and_format_phone("919876543210"), "919876543210")
        self.assertEqual(validate_and_format_phone("09876543210"), "919876543210")
        self.assertEqual(validate_and_format_phone("+91 98765 43210"), "919876543210")

        # Invalid formats
        self.assertIsNone(validate_and_format_phone("12345"))
        self.assertIsNone(validate_and_format_phone("abcdefghij"))
        self.assertIsNone(validate_and_format_phone(None))
        self.assertIsNone(validate_and_format_phone(""))
        self.assertIsNone(validate_and_format_phone("1234567890"))  # starts with 1

    # --------------------------------------------------------------------------
    # 2. PDF Generation Tests (Existing Template)
    # --------------------------------------------------------------------------
    def test_generate_receipt_pdf_bytes(self):
        """Test PDF is successfully generated using existing donation_receipt.html."""
        pdf_bytes = generate_receipt_pdf_bytes(self.donation)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))

    # --------------------------------------------------------------------------
    # 3. GCS Upload & Accessible URL Tests
    # --------------------------------------------------------------------------
    @patch("heart_charity.receipt_service.get_accessible_gcs_url")
    def test_get_or_upload_receipt_pdf(self, mock_url):
        """Test PDF upload to GCS path and accessible URL resolution."""
        mock_url.return_value = "https://storage.googleapis.com/ahinsadham-bucket/donation_receipts/Donation_Receipt_ACH-2026-0001.pdf"
        gcs_path, doc_url = get_or_upload_receipt_pdf(self.donation)
        self.assertIn("donation_receipts/Donation_Receipt_ACH-2026-0001.pdf", gcs_path)
        self.assertEqual(doc_url, "https://storage.googleapis.com/ahinsadham-bucket/donation_receipts/Donation_Receipt_ACH-2026-0001.pdf")

        # Verify that calling again reuses the existing stored receipt without overwriting
        with patch.object(default_storage, 'save') as mock_save:
            gcs_path2, doc_url2 = get_or_upload_receipt_pdf(self.donation)
            mock_save.assert_not_called()
            self.assertEqual(gcs_path, gcs_path2)

    # --------------------------------------------------------------------------
    # 4. WhatsApp API Payload & Variable Mapping Tests
    # --------------------------------------------------------------------------
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_send_donation_receipt_whatsapp_payload(self, mock_post):
        """Test exact 11za payload structure matching template utility_5671."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Message": "Template Message Sent",
            "Data": {"messageId": "wamid.test_msg_999"},
            "Status": 200,
            "IsSuccess": True,
        }
        mock_post.return_value = mock_resp

        result = send_donation_receipt_whatsapp(
            phone="9876543210",
            donor_name="Ramesh Shah",
            amount="2500",
            donation_date="03-Nov-2026",
            receipt_id="ACH-2026-0001",
            document_url="https://storage.googleapis.com/ahinsadham-bucket/donation_receipts/test.pdf",
            document_filename="Donation_Receipt_ACH-2026-0001.pdf",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"], "wamid.test_msg_999")

        # Verify API call payload
        self.assertEqual(mock_post.call_count, 1)
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]

        self.assertEqual(payload["templateName"], "utility_5671")
        self.assertEqual(payload["language"], "en")
        self.assertEqual(payload["sendto"], "919876543210")
        self.assertEqual(payload["headerdata"], "")
        self.assertEqual(payload["myfile"], "https://storage.googleapis.com/ahinsadham-bucket/donation_receipts/test.pdf")
        self.assertEqual(payload["myfileName"], "Donation_Receipt_ACH-2026-0001.pdf")
        self.assertEqual(payload["tags"], "donation_receipt")

        # Variable mapping:
        # {{1}} = Donor Name, {{2}} = Donation Amount, {{3}} = Donation Date, {{4}} = Receipt Number
        self.assertEqual(payload["data"], ["Ramesh Shah", "2500", "03-Nov-2026", "ACH-2026-0001"])

    # --------------------------------------------------------------------------
    # 5. Full Delivery Orchestration & Status Tracking
    # --------------------------------------------------------------------------
    @patch("heart_charity.receipt_service.get_accessible_gcs_url")
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_deliver_donation_receipt_whatsapp_success(self, mock_post, mock_url):
        """Test successful end-to-end receipt delivery and DB logging."""
        mock_url.return_value = "https://storage.googleapis.com/ahinsadham-bucket/test.pdf"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Message": "Template Message Sent",
            "Data": {"messageId": "wamid.full_success_001"},
            "Status": 200,
            "IsSuccess": True,
        }
        mock_post.return_value = mock_resp

        result = deliver_donation_receipt_whatsapp(self.donation)
        self.assertTrue(result["success"])
        self.assertFalse(result["already_sent"])
        self.assertEqual(result["status"], "SENT")
        self.assertEqual(result["message_id"], "wamid.full_success_001")

        # Verify DB log entry
        log_entry = DonationWhatsAppReceipt.objects.get(receipt_id="ACH-2026-0001")
        self.assertEqual(log_entry.status, "SENT")
        self.assertEqual(log_entry.recipient_phone, "919876543210")
        self.assertEqual(log_entry.donor_name, "Ramesh Shah")
        self.assertEqual(log_entry.amount, "2500")
        self.assertEqual(log_entry.message_id, "wamid.full_success_001")
        self.assertIsNotNone(log_entry.sent_at)

    # --------------------------------------------------------------------------
    # 6. Duplicate Protection Tests
    # --------------------------------------------------------------------------
    @patch("heart_charity.receipt_service.get_accessible_gcs_url")
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_duplicate_prevention_on_repeat_dispatch(self, mock_post, mock_url):
        """Test duplicate message is strictly avoided on repeat dispatch / refresh."""
        mock_url.return_value = "https://storage.googleapis.com/ahinsadham-bucket/test.pdf"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Message": "Template Message Sent",
            "Data": {"messageId": "wamid.dup_check_01"},
            "Status": 200,
            "IsSuccess": True,
        }
        mock_post.return_value = mock_resp

        # First dispatch
        res1 = deliver_donation_receipt_whatsapp(self.donation)
        self.assertTrue(res1["success"])
        self.assertEqual(mock_post.call_count, 1)

        # Second dispatch (repeat callback / page refresh)
        res2 = deliver_donation_receipt_whatsapp(self.donation)
        self.assertTrue(res2["success"])
        self.assertTrue(res2["already_sent"])
        self.assertEqual(res2["status"], "ALREADY_SENT")

        # API should NOT be called a second time
        self.assertEqual(mock_post.call_count, 1)

    # --------------------------------------------------------------------------
    # 7. Missing & Invalid Phone Handling
    # --------------------------------------------------------------------------
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_missing_or_invalid_donor_phone(self, mock_post):
        """Test when donor has no phone number, API call is skipped and logged."""
        self.donor.contact_number = ""
        self.donor.whatsapp_number = ""
        self.donor.save()

        res = deliver_donation_receipt_whatsapp(self.donation)
        self.assertFalse(res["success"])
        self.assertTrue("missing or invalid" in res["error"].lower() or "no registered mobile" in res["error"].lower())
        mock_post.assert_not_called()

        log_entry = DonationWhatsAppReceipt.objects.get(receipt_id="ACH-2026-0001")
        self.assertEqual(log_entry.status, "FAILED")

    # --------------------------------------------------------------------------
    # 8. Unverified Donation Handling
    # --------------------------------------------------------------------------
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_unverified_donation_is_skipped(self, mock_post):
        """Test receipts are never sent for unverified donations."""
        self.donation.verified = False
        self.donation.save()

        res = deliver_donation_receipt_whatsapp(self.donation)
        self.assertFalse(res["success"])
        self.assertTrue(res.get("skipped", False))
        mock_post.assert_not_called()

    # --------------------------------------------------------------------------
    # 9. API Error / Timeout Handling (Non-blocking)
    # --------------------------------------------------------------------------
    @patch("heart_charity.receipt_service.get_accessible_gcs_url")
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_whatsapp_api_failure_does_not_raise(self, mock_post, mock_url):
        """Test WhatsApp API failure logs error gracefully without breaking donation flow."""
        mock_url.return_value = "https://storage.googleapis.com/ahinsadham-bucket/test.pdf"
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"Message": "11za upstream gateway error", "IsSuccess": False}
        mock_post.return_value = mock_resp

        res = deliver_donation_receipt_whatsapp(self.donation)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "FAILED")

        log_entry = DonationWhatsAppReceipt.objects.get(receipt_id="ACH-2026-0001")
        self.assertEqual(log_entry.status, "FAILED")
        self.assertIn("11za upstream gateway error", log_entry.error_message)

    # --------------------------------------------------------------------------
    # 10. Controlled Retry Support
    # --------------------------------------------------------------------------
    @patch("heart_charity.receipt_service.get_accessible_gcs_url")
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_retry_failed_whatsapp_receipt(self, mock_post, mock_url):
        """Test failed delivery can be retried without generating duplicate receipt."""
        mock_url.return_value = "https://storage.googleapis.com/ahinsadham-bucket/test.pdf"

        # 1. First attempt fails
        mock_resp1 = MagicMock()
        mock_resp1.status_code = 502
        mock_resp1.json.return_value = {"Message": "Bad Gateway", "IsSuccess": False}
        mock_post.return_value = mock_resp1

        res1 = deliver_donation_receipt_whatsapp(self.donation)
        self.assertFalse(res1["success"])

        # 2. Retry succeeds
        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = {
            "Message": "Template Message Sent",
            "Data": {"messageId": "wamid.retry_success_456"},
            "IsSuccess": True,
        }
        mock_post.return_value = mock_resp2

        retry_res = retry_failed_whatsapp_receipt("ACH-2026-0001")
        self.assertTrue(retry_res["success"])
        self.assertEqual(retry_res["message_id"], "wamid.retry_success_456")

        log_entry = DonationWhatsAppReceipt.objects.get(receipt_id="ACH-2026-0001")
        self.assertEqual(log_entry.status, "SENT")
        self.assertEqual(log_entry.retry_count, 1)

    # --------------------------------------------------------------------------
    # 11. Regression Check: Existing WhatsApp OTP Login Intact
    # --------------------------------------------------------------------------
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_existing_login_otp_remains_unaffected(self, mock_post):
        """Verify existing WhatsApp OTP login functionality was not modified or broken."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Message": "Template Message Sent",
            "Data": {"messageId": "wamid.otp_123"},
            "IsSuccess": True,
        }
        mock_post.return_value = mock_resp

        otp_res = send_login_otp_whatsapp("9876543210", "123456")
        self.assertTrue(otp_res["success"])
        self.assertEqual(otp_res["message_id"], "wamid.otp_123")

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["templateName"], "otp")
        self.assertEqual(kwargs["json"]["data"], ["123456"])

    # --------------------------------------------------------------------------
    # 12. Other Donation Workflow Test (Creation -> Verification -> Delivery)
    # --------------------------------------------------------------------------
    @patch("heart_charity.receipt_service.get_accessible_gcs_url")
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_other_donation_workflow_verification_triggers_whatsapp(self, mock_post, mock_url):
        """Test Other Donation workflow: unverified on creation, verified later via signal triggers WhatsApp."""
        mock_url.return_value = "https://storage.googleapis.com/ahinsadham-bucket/other_donation.pdf"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Message": "Template Message Sent",
            "Data": {"messageId": "wamid.other_don_001"},
            "Status": 200,
            "IsSuccess": True,
        }
        mock_post.return_value = mock_resp

        # Create unverified Other Donation
        other_don = Donation.objects.create(
            donor=self.donor,
            display_name="Ramesh Shah",
            donation_date=timezone.now().date(),
            donation_amount_paid=1100.00,
            donation_amount_declared=1100.00,
            donation_category=self.category,
            payment_method=self.payment_method,
            payment_status=self.payment_status,
            verified=False,
        )
        self.assertIsNone(other_don.receipt_id)
        mock_post.assert_not_called()

        # Staff verifies donation
        other_don.verified = True
        other_don.save(update_fields=["verified"])
        other_don.refresh_from_db()

        self.assertIsNotNone(other_don.receipt_id)
        self.assertEqual(mock_post.call_count, 1)

        # Verify payload sent to 11za
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["templateName"], "utility_5671")
        self.assertEqual(payload["sendto"], "919876543210")
        self.assertEqual(payload["data"], ["Ramesh Shah", "1100", other_don.donation_date.strftime("%d-%b-%Y"), other_don.receipt_id])

    # --------------------------------------------------------------------------
    # 13. Danpeti Donation Workflow Test (Online / Offline Verification -> Delivery)
    # --------------------------------------------------------------------------
    @patch("heart_charity.receipt_service.get_accessible_gcs_url")
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_danpeti_donation_workflow_verification_triggers_whatsapp(self, mock_post, mock_url):
        """Test Danpeti Donation: verification signal auto-generates receipt and dispatches WhatsApp PDF."""
        mock_url.return_value = "https://storage.googleapis.com/ahinsadham-bucket/danpeti_receipt.pdf"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Message": "Template Message Sent",
            "Data": {"messageId": "wamid.danpeti_msg_001"},
            "Status": 200,
            "IsSuccess": True,
        }
        mock_post.return_value = mock_resp

        # Create box & box owner
        box_owner = DonorVolunteer.objects.create(
            first_name="Prakash",
            last_name="Jain",
            contact_number="9822000000",
            whatsapp_number="9822000000",
        )
        box = DonationBox.objects.create(
            donation_id="BOX-99",
            status="Active",
        )

        # Create Danpeti payment for individual donor
        payment = DonationPaymentBox.objects.create(
            donor_type="Donor",
            first_name="Amit",
            last_name="Mehta",
            mobile_number="9123456780",
            amount=501.00,
            owner=box_owner,
            donation_box=box,
            verified=False,
        )
        self.assertIsNone(payment.receipt_id)
        mock_post.assert_not_called()

        # Verify payment
        payment.verified = True
        payment.save(update_fields=["verified"])
        payment.refresh_from_db()

        self.assertIsNotNone(payment.receipt_id)
        self.assertEqual(mock_post.call_count, 1)

        # Verify WhatsApp recipient was the individual donor's mobile, not the box owner's
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["templateName"], "utility_5671")
        self.assertEqual(payload["sendto"], "919123456780")
        self.assertEqual(payload["data"], ["Amit Mehta", "501", payment.created_at.strftime("%d-%b-%Y"), payment.receipt_id])

    # --------------------------------------------------------------------------
    # 14. Danpeti PDF Generation Test
    # --------------------------------------------------------------------------
    def test_danpeti_pdf_generation(self):
        """Test PDF is successfully rendered using donation_owner_receipt_pdf.html for Danpeti."""
        box = DonationBox.objects.create(donation_id="BOX-PDF", status="Active")
        payment = DonationPaymentBox.objects.create(
            donor_type="Donor",
            first_name="Sunil",
            last_name="Shah",
            mobile_number="9988776655",
            amount=1000.00,
            donation_box=box,
            receipt_id="DP-2026-0001",
            verified=True,
        )
        pdf_bytes = generate_receipt_pdf_bytes(payment)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))

    # --------------------------------------------------------------------------
    # 15. ACH Donation Workflow Test (Online Gateway Payment -> Direct Receipt)
    # --------------------------------------------------------------------------
    @patch("heart_charity.receipt_service.get_accessible_gcs_url")
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_ach_donation_workflow_delivery(self, mock_post, mock_url):
        """Test ACH Donation: Online Razorpay verification directly triggers receipt delivery."""
        mock_url.return_value = "https://storage.googleapis.com/ahinsadham-bucket/ach_receipt.pdf"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Message": "Template Message Sent",
            "Data": {"messageId": "wamid.ach_verified_001"},
            "Status": 200,
            "IsSuccess": True,
        }
        mock_post.return_value = mock_resp

        ach_donation = Donation.objects.create(
            donor=self.donor,
            display_name="Ramesh Shah",
            donation_date=timezone.now().date(),
            donation_amount_paid=5000.00,
            donation_amount_declared=5000.00,
            donation_category=self.category,
            payment_method=self.payment_method,
            payment_status=self.payment_status,
            receipt_id="ACH-2026-9999",
            verified=True,
        )

        result = deliver_donation_receipt_whatsapp(ach_donation)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "SENT")
        self.assertEqual(result["message_id"], "wamid.ach_verified_001")

        log = DonationWhatsAppReceipt.objects.get(receipt_id="ACH-2026-9999")
        self.assertEqual(log.status, "SENT")
        self.assertEqual(log.donation, ach_donation)

    # --------------------------------------------------------------------------
    # 16. Unified Service Test: All 3 Donation Types Use Same Common Service
    # --------------------------------------------------------------------------
    @patch("heart_charity.receipt_service.get_accessible_gcs_url")
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_all_three_donation_types_use_same_common_service(self, mock_post, mock_url):
        """Verify that Other Donation, ACH Donation, and Danpeti Donation all use deliver_donation_receipt_whatsapp."""
        mock_url.return_value = "https://storage.googleapis.com/ahinsadham-bucket/common.pdf"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Message": "Template Message Sent",
            "Data": {"messageId": "wamid.common_service_01"},
            "Status": 200,
            "IsSuccess": True,
        }
        mock_post.return_value = mock_resp

        # 1. Other Donation
        other = Donation.objects.create(
            donor=self.donor,
            donation_amount_paid=100.0,
            donation_category=self.category,
            receipt_id="OD-COMMON-1",
            verified=True,
        )
        res_other = deliver_donation_receipt_whatsapp(other)
        self.assertTrue(res_other["success"])

        # 2. ACH Donation
        ach = Donation.objects.create(
            donor=self.donor,
            donation_amount_paid=200.0,
            donation_category=self.category,
            receipt_id="ACH-COMMON-1",
            verified=True,
        )
        res_ach = deliver_donation_receipt_whatsapp(ach)
        self.assertTrue(res_ach["success"])

        # 3. Danpeti Donation
        box = DonationBox.objects.create(donation_id="BOX-COMMON", status="Active")
        danpeti = DonationPaymentBox.objects.create(
            first_name="Test",
            last_name="Donor",
            mobile_number="9876543210",
            amount=300.0,
            donation_box=box,
            receipt_id="DP-COMMON-1",
            verified=True,
        )
        res_danpeti = deliver_donation_receipt_whatsapp(danpeti)
        self.assertTrue(res_danpeti["success"])

        # Verify all 3 records were recorded in DonationWhatsAppReceipt
        self.assertEqual(DonationWhatsAppReceipt.objects.filter(status="SENT").count(), 3)

    # --------------------------------------------------------------------------
    # 17. Failure Scenario 3: PDF Generation Failure Handling
    # --------------------------------------------------------------------------
    @patch("django.core.files.storage.default_storage.exists", return_value=False)
    @patch("heart_charity.receipt_service.generate_receipt_pdf_bytes", side_effect=RuntimeError("xhtml2pdf engine crash"))
    def test_pdf_generation_failure_is_non_blocking(self, mock_pdf, mock_exists):
        """Test PDF generation failure logs error and does not throw unhandled exception."""
        test_don = Donation.objects.create(
            donor=self.donor,
            receipt_id="ACH-PDF-FAIL-99",
            verified=True,
            donation_amount_paid=100.0,
            donation_category=self.category,
        )
        res = deliver_donation_receipt_whatsapp(test_don)
        self.assertFalse(res["success"])
        self.assertIn("Failed to generate or upload receipt PDF", res["error"])

        log = DonationWhatsAppReceipt.objects.get(receipt_id="ACH-PDF-FAIL-99")
        self.assertEqual(log.status, "FAILED")
        self.assertIn("xhtml2pdf engine crash", log.error_message)

    # --------------------------------------------------------------------------
    # 18. Failure Scenario 4: Google Cloud Storage Upload Failure Handling
    # --------------------------------------------------------------------------
    @patch("django.core.files.storage.default_storage.exists", return_value=False)
    @patch("django.core.files.storage.default_storage.save", side_effect=IOError("GCS storage connection dropped"))
    def test_gcs_upload_failure_is_non_blocking(self, mock_save, mock_exists):
        """Test GCS upload failure logs error and does not throw unhandled exception."""
        res = deliver_donation_receipt_whatsapp(self.donation)
        self.assertFalse(res["success"])
        self.assertIn("GCS storage connection dropped", res["error"])

        log = DonationWhatsAppReceipt.objects.get(receipt_id="ACH-2026-0001")
        self.assertEqual(log.status, "FAILED")

    # --------------------------------------------------------------------------
    # 19. Failure Scenario 6: Missing / Invalid WhatsApp Auth Token Handling
    # --------------------------------------------------------------------------
    def test_missing_auth_token_error_handling(self):
        """Test missing authentication token returns clean error."""
        with patch("heart_charity.whatsapp_service.get_whatsapp_config", return_value={"access_token": ""}):
            res = send_donation_receipt_whatsapp(
                phone="9876543210",
                donor_name="Test Donor",
                amount="500",
                donation_date="03-Nov-2026",
                receipt_id="ACH-TEST-TOKEN",
                document_url="https://storage.googleapis.com/test.pdf",
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["error"], "WHATSAPP_ACCESS_TOKEN is missing")

    # --------------------------------------------------------------------------
    # 20. Failure Scenario 7: Invalid Template Name Rejection Handling
    # --------------------------------------------------------------------------
    @patch("heart_charity.whatsapp_service.requests.post")
    def test_invalid_template_name_rejection(self, mock_post):
        """Test API rejection due to invalid template name returns clear error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "Message": "Template utility_nonexistent not found",
            "IsSuccess": False,
            "Status": 400,
        }
        mock_post.return_value = mock_resp

        res = send_donation_receipt_whatsapp(
            phone="9876543210",
            donor_name="Test Donor",
            amount="500",
            donation_date="03-Nov-2026",
            receipt_id="ACH-TEST-TMPL",
            document_url="https://storage.googleapis.com/test.pdf",
        )
        self.assertFalse(res["success"])
        self.assertIn("Template utility_nonexistent not found", res["error"])

    # --------------------------------------------------------------------------
    # 21. Failure Scenario 9: Missing / Invalid Document URL Handling
    # --------------------------------------------------------------------------
    def test_missing_document_url_error_handling(self):
        """Test missing document URL returns clean validation error without API call."""
        res = send_donation_receipt_whatsapp(
            phone="9876543210",
            donor_name="Test Donor",
            amount="500",
            donation_date="03-Nov-2026",
            receipt_id="ACH-TEST-DOC",
            document_url="",
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "Missing receipt document URL")

    # --------------------------------------------------------------------------
    # 22. Failure Scenario 10: WhatsApp API Timeout Handling
    # --------------------------------------------------------------------------
    @patch("heart_charity.whatsapp_service.requests.post", side_effect=requests.Timeout("11za timeout after 30s"))
    def test_whatsapp_api_timeout_error_handling(self, mock_post):
        """Test WhatsApp API timeout returns clean error without crashing."""
        res = send_donation_receipt_whatsapp(
            phone="9876543210",
            donor_name="Test Donor",
            amount="500",
            donation_date="03-Nov-2026",
            receipt_id="ACH-TEST-TIMEOUT",
            document_url="https://storage.googleapis.com/test.pdf",
        )
        self.assertFalse(res["success"])
        self.assertIn("timed out", res["error"].lower())


    # --------------------------------------------------------------------------
    # 23. Other Donation: Strict PAN and Name Match Verification
    # --------------------------------------------------------------------------
    def test_other_donation_requires_both_pan_and_name_match(self):
        """Test Other Donation strictly requires both valid PAN and matching name in DonorVolunteer."""
        # Case A: Valid PAN and matching name
        valid_donor = DonorVolunteer.objects.create(
            first_name="Kantilal",
            last_name="Gada",
            pan_number="ABCDE1234F",
            contact_number="9820012345",
        )
        other_donation = Donation.objects.create(
            donor=valid_donor,
            display_name="Kantilal Gada",
            donation_date=timezone.now().date(),
            donation_amount_paid=11000.00,
            donation_amount_declared=11000.00,
            donation_category=self.category,
            payment_method=self.payment_method,
            receipt_id="2026-11-0001",  # Other donation receipt format
            verified=True,
        )
        donor_name, amount, date_str, r_id, phone, err = extract_donor_details(other_donation)
        self.assertIsNone(err)
        self.assertEqual(donor_name, "Kantilal Gada")
        self.assertEqual(phone, "9820012345")

        # Case B: Missing PAN on donor
        no_pan_donor = DonorVolunteer.objects.create(
            first_name="Pravin",
            last_name="Patel",
            pan_number="",  # Missing PAN
            contact_number="9820098765",
        )
        other_donation_no_pan = Donation.objects.create(
            donor=no_pan_donor,
            display_name="Pravin Patel",
            donation_date=timezone.now().date(),
            donation_amount_paid=5000.00,
            donation_amount_declared=5000.00,
            donation_category=self.category,
            payment_method=self.payment_method,
            receipt_id="2026-11-0002",
            verified=True,
        )
        _, _, _, _, _, err = extract_donor_details(other_donation_no_pan)
        self.assertIsNotNone(err)
        self.assertIn("no registered PAN Number", err)

        # Case C: Name mismatch with PAN record
        mismatch_donation = Donation.objects.create(
            donor=valid_donor,
            display_name="Unrelated Person Name",
            donation_date=timezone.now().date(),
            donation_amount_paid=3000.00,
            donation_amount_declared=3000.00,
            donation_category=self.category,
            payment_method=self.payment_method,
            receipt_id="2026-11-0003",
            verified=True,
        )
        _, _, _, _, _, err = extract_donor_details(mismatch_donation)
        self.assertIsNotNone(err)
        self.assertIn("Name and PAN do not match", err)

    # --------------------------------------------------------------------------
    # 24. Manual Resend Endpoint via Authenticated POST
    # --------------------------------------------------------------------------
    @patch("heart_charity.receipt_service.get_or_upload_receipt_pdf", return_value=("donation_receipts/Donation_Receipt_ACH-2026-0001.pdf", "https://storage.googleapis.com/test-bucket/receipt.pdf"))
    @patch("heart_charity.receipt_service.get_accessible_gcs_url", return_value="https://storage.googleapis.com/test-bucket/receipt.pdf")
    @patch("heart_charity.receipt_service.send_donation_receipt_whatsapp")
    def test_manual_resend_endpoint_via_post(self, mock_send, mock_url, mock_pdf):
        """Test staff manual resend via authenticated POST with force=true and format=json."""
        mock_send.return_value = {
            "success": True,
            "message_id": "wamid.RESEND12345",
            "phone": "919876543210",
        }
        user = User.objects.create_user(username="teststaff", password="password123", is_staff=True)
        self.client.login(username="teststaff", password="password123")

        # First automatic dispatch creates log with status SENT
        res1 = deliver_donation_receipt_whatsapp(self.donation, force_resend=False)
        self.assertTrue(res1["success"])
        receipt_count_before = Donation.objects.count()

        # Resend via POST to send_receipt_whatsapp endpoint
        from django.urls import reverse
        url = reverse("send_receipt_whatsapp", kwargs={"id": self.donation.id})
        response = self.client.post(
            url,
            data={"force": "true", "format": "json"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["message_id"], "wamid.RESEND12345")

        # Verify no duplicate donation or receipt record created
        self.assertEqual(Donation.objects.count(), receipt_count_before)
        receipt_log = DonationWhatsAppReceipt.objects.get(receipt_id=self.donation.receipt_id)
        self.assertEqual(receipt_log.status, "SENT")
        self.assertGreaterEqual(receipt_log.retry_count, 1)

    # --------------------------------------------------------------------------
    # 25. Daanpeti Manual Resend Endpoint via Authenticated POST
    # --------------------------------------------------------------------------
    @patch("heart_charity.receipt_service.get_or_upload_receipt_pdf", return_value=("donation_receipts/Donation_Receipt_DP-TEST-POST.pdf", "https://storage.googleapis.com/test-bucket/dp_receipt.pdf"))
    @patch("heart_charity.receipt_service.get_accessible_gcs_url", return_value="https://storage.googleapis.com/test-bucket/dp_receipt.pdf")
    @patch("heart_charity.receipt_service.send_donation_receipt_whatsapp")
    def test_danpeti_manual_resend_endpoint_via_post(self, mock_send, mock_url, mock_pdf):
        """Test staff manual resend for Daanpeti donation via authenticated POST."""
        mock_send.return_value = {
            "success": True,
            "message_id": "wamid.DPRESEND789",
            "phone": "919876543210",
        }
        user = User.objects.create_user(username="teststaff2", password="password123", is_staff=True)
        self.client.login(username="teststaff2", password="password123")

        box = DonationBox.objects.create(donation_id="BX-TEST-POST", status="Active")
        payment = DonationPaymentBox.objects.create(
            donation_box=box,
            first_name="Harish",
            last_name="Mehta",
            mobile_number="9876543210",
            amount=1500.00,
            receipt_id="DP-TEST-POST",
            verified=True,
        )

        from django.urls import reverse
        url = reverse("send_danpeti_receipt_whatsapp", kwargs={"id": payment.id})
        response = self.client.post(
            url,
            data={"force": "true", "format": "json"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["message_id"], "wamid.DPRESEND789")

    # --------------------------------------------------------------------------
    # 25a. Unauthenticated AJAX Request Returns 401 JSON (No 302 Login Redirect)
    # --------------------------------------------------------------------------
    def test_manual_resend_endpoint_unauthenticated_ajax_returns_401_json(self):
        """
        Verify that an unauthenticated Fetch / AJAX request to the WhatsApp receipt endpoint
        receives an HTTP 401 Unauthorized JSON response instead of a 302 HTML login redirect.
        """
        self.client.logout()
        from django.urls import reverse
        url = reverse("send_receipt_whatsapp", kwargs={"id": self.donation.id})
        response = self.client.post(
            url,
            data={"force": "true", "format": "json"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.headers.get("Content-Type", "").startswith("application/json"))
        data = response.json()
        self.assertFalse(data["success"])
        self.assertTrue(data.get("session_expired"))
        self.assertIn("login", data.get("login_url", ""))

    # --------------------------------------------------------------------------
    # 25b. Unauthenticated Browser GET Redirects to Login with ?next=
    # --------------------------------------------------------------------------
    def test_manual_resend_endpoint_unauthenticated_browser_returns_302_redirect(self):
        """
        Verify that an unauthenticated standard browser navigation (non-AJAX)
        to the WhatsApp receipt endpoint cleanly redirects to LOGIN_URL with ?next=.
        """
        self.client.logout()
        from django.urls import reverse
        url = reverse("send_receipt_whatsapp", kwargs={"id": self.donation.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/?next=", response.headers.get("Location", ""))

    # --------------------------------------------------------------------------
    # 25c. Daanpeti Unauthenticated AJAX Returns 401 JSON
    # --------------------------------------------------------------------------
    def test_danpeti_manual_resend_endpoint_unauthenticated_ajax_returns_401_json(self):
        """
        Verify that an unauthenticated Fetch / AJAX request to Daanpeti receipt endpoint
        receives an HTTP 401 Unauthorized JSON response instead of a 302 HTML login redirect.
        """
        self.client.logout()
        from django.urls import reverse
        box = DonationBox.objects.create(donation_id="BX-TEST-401", status="Active")
        payment = DonationPaymentBox.objects.create(
            donation_box=box,
            first_name="Harish",
            last_name="Mehta",
            mobile_number="9876543210",
            amount=500.00,
            receipt_id="DP-TEST-401",
            verified=True,
        )
        url = reverse("send_danpeti_receipt_whatsapp", kwargs={"id": payment.id})
        response = self.client.post(
            url,
            data={"force": "true", "format": "json"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.headers.get("Content-Type", "").startswith("application/json"))
        data = response.json()
        self.assertFalse(data["success"])
        self.assertTrue(data.get("session_expired"))

    # --------------------------------------------------------------------------
    # 26. Exact User Case: Dropdown Display "abc xyz - ABCDE1234F" with DB "abc xyz"
    # --------------------------------------------------------------------------
    @patch("heart_charity.receipt_service.get_or_upload_receipt_pdf", return_value=("donation_receipts/Donation_Receipt_OD-ABC-51.pdf", "https://storage.googleapis.com/test-bucket/receipt51.pdf"))
    @patch("heart_charity.receipt_service.get_accessible_gcs_url", return_value="https://storage.googleapis.com/test-bucket/receipt51.pdf")
    @patch("heart_charity.receipt_service.send_donation_receipt_whatsapp")
    def test_other_donation_dropdown_display_format_abc_xyz_pan_succeeds(self, mock_send, mock_url, mock_pdf):
        """
        Exact user scenario:
        Selected dropdown display: 'abc xyz - ABCDE1234F'
        Database donor name: 'abc xyz'
        Database PAN: 'ABCDE1234F'
        Expected:
        - Donor verification succeeds
        - Correct DonorVolunteer is identified
        - Correct registered mobile number is fetched
        - Receipt PDF is uploaded / retrieved
        - WhatsApp payload constructed with clean donor name 'abc xyz'
        """
        mock_send.return_value = {
            "success": True,
            "message_id": "wamid.ABCXYZ51",
            "phone": "917798354386",
        }

        donor_abc = DonorVolunteer.objects.create(
            first_name="abc",
            last_name="xyz",
            pan_number="ABCDE1234F",
            whatsapp_number="7798354386",
            contact_number="7798354386",
        )

        donation_51 = Donation.objects.create(
            donor=donor_abc,
            display_name="abc xyz - ABCDE1234F",  # Raw string from dropdown display label
            donation_date=timezone.now().date(),
            donation_amount_paid=5000.00,
            donation_amount_declared=5000.00,
            donation_category=self.category,
            payment_method=self.payment_method,
            receipt_id="OD-ABC-51",
            verified=True,
        )

        # 1. extract_donor_details verification
        donor_name, amount, date_str, r_id, phone, err = extract_donor_details(donation_51)
        self.assertIsNone(err)
        self.assertEqual(donor_name, "abc xyz")  # Must be stripped of ' - ABCDE1234F'
        self.assertEqual(phone, "7798354386")
        self.assertEqual(r_id, "OD-ABC-51")

        # 2. deliver_donation_receipt_whatsapp execution
        res = deliver_donation_receipt_whatsapp(donation_51)
        self.assertTrue(res["success"])
        self.assertEqual(res["message_id"], "wamid.ABCXYZ51")

        # 3. Verify send_donation_receipt_whatsapp was called with pure donor name 'abc xyz'
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        self.assertEqual(call_kwargs["donor_name"], "abc xyz")
        self.assertEqual(call_kwargs["amount"], "5000")
        self.assertEqual(call_kwargs["receipt_id"], "OD-ABC-51")
        self.assertEqual(call_kwargs["document_url"], "https://storage.googleapis.com/test-bucket/receipt51.pdf")

    # --------------------------------------------------------------------------
    # 27. Dropdown Autocomplete AJAX Endpoint Returns Structured Data
    # --------------------------------------------------------------------------
    def test_donor_autocomplete_ajax_returns_structured_donor_data(self):
        """Test donor_autocomplete_ajax returns id, text, donor_id, donor_name, pan_number, display_label."""
        donor_auto = DonorVolunteer.objects.create(
            first_name="Suresh",
            middle_name="K",
            last_name="Jain",
            pan_number="XYZAB5678C",
            contact_number="9820011223",
        )

        from django.urls import reverse
        url = reverse("donor_autocomplete_ajax") + "?person_type=donor&q=Suresh"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)
        self.assertTrue(len(data["results"]) >= 1)

        result_item = [r for r in data["results"] if r["id"] == donor_auto.id][0]
        self.assertEqual(result_item["donor_id"], donor_auto.id)
        self.assertEqual(result_item["donor_name"], "Suresh K Jain")
        self.assertEqual(result_item["pan_number"], "XYZAB5678C")
        self.assertEqual(result_item["text"], "Suresh K Jain - XYZAB5678C")
        self.assertEqual(result_item["display_label"], "Suresh K Jain - XYZAB5678C")

    # --------------------------------------------------------------------------
    # 28. Add Donation View Cleans Dropdown Label from display_name
    # --------------------------------------------------------------------------
    def test_adddonation_view_sanitizes_dropdown_pan_suffix(self):
        """Test POSTing adddonation with display_name='Suresh Jain - XYZAB5678C' saves clean display_name."""
        user = User.objects.create_user(username="donoradmin", password="password123", is_staff=True)
        self.client.login(username="donoradmin", password="password123")

        donor_clean = DonorVolunteer.objects.create(
            first_name="Suresh",
            last_name="Jain",
            pan_number="XYZAB5678C",
            contact_number="9820011223",
        )

        from django.urls import reverse
        url = reverse("adddonation")
        post_data = {
            "donor": str(donor_clean.id),
            "display_name": "Suresh Jain - XYZAB5678C",  # Submitting dropdown label
            "donation_category": str(self.category.id),
            "donation_amount_declared": "2000",
            "donation_amount_paid": "2000",
            "payment_method": str(self.payment_method.id),
            "payment_status": str(self.payment_status.id),
            "transaction_id": "txn_test_suresh_123",
        }
        resp = self.client.post(url, data=post_data)
        self.assertEqual(resp.status_code, 302)

        saved_donation = Donation.objects.filter(donor=donor_clean).order_by("-id").first()
        self.assertIsNotNone(saved_donation)
        self.assertEqual(saved_donation.display_name, "Suresh Jain")

"""Financial-critical tests: settlement idempotency and balance integrity."""

import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

from credit.models import CreditAssessment
from customers.models import CustomerProfile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from loans.models import Loan
from loans.services import create_loan
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User
from vehicles.models import Vehicle

from .models import Payment, WebhookEvent
from .providers import get_provider
from .services import _apply_failure, _apply_success, handle_webhook, initialize_payment


def sign_paystack(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()


def sign_momo(body: bytes) -> str:
    from django.conf import settings

    return hmac.new(settings.MOCK_MOMO_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


class PaymentFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user(username="pay_operator", role=User.Role.OPERATIONS)
        cls.admin = User.objects.create_user(username="pay_admin", role=User.Role.ADMIN)
        cls.customer = User.objects.create_user(username="pay_customer")
        cls.profile = CustomerProfile.objects.create(
            user=cls.customer,
            full_name="Pay Customer",
            phone="+233201234567",
            monthly_income="65000.00",
            employment_status="EMPLOYED",
            employment_duration_months=24,
        )
        cls.vehicle = Vehicle.objects.create(
            registration_number="PAY-000",
            vin="1HGCM82633A004352",
            make="Toyota",
            model_name="Corolla",
            year=2020,
            customer=cls.profile,
        )
        snapshot = {
            "currency": cls.profile.currency,
            "employment_status": cls.profile.employment_status,
            "employment_duration_months": cls.profile.employment_duration_months,
            "monthly_income": "65000.00",
            "existing_debt": "0.00",
            "monthly_debt_repayment": "0.00",
            "profile_updated_at": cls.profile.updated_at.isoformat(),
            "data_source": "self_reported_demo",
            "repayment_history": None,
            "transaction_history": None,
        }
        cls.assessment = CreditAssessment.objects.create(
            customer=cls.profile,
            rules_version="demo-v1",
            rules_snapshot={},
            input_snapshot=snapshot,
            score=700,
            risk_band=CreditAssessment.RiskBand.LOW,
            decision=CreditAssessment.Decision.APPROVED,
            factors=[],
            ratios={},
        )

    @classmethod
    def activate(cls, loan):
        loan.status = Loan.Status.ACTIVE
        loan.outstanding_balance = loan.total_repayable
        loan.activated_at = timezone.now()
        loan.save()
        return loan


class PaymentServiceTests(PaymentFixtureMixin, APITestCase):
    def make_loan(self, index):
        vehicle = Vehicle.objects.create(
            registration_number=f"PAY-{index:03d}",
            vin=f"1HGCM82633A00{index:04d}",
            make="Toyota",
            model_name="Corolla",
            year=2020,
            customer=self.profile,
        )
        loan = create_loan(
            actor=self.operator,
            customer=self.profile,
            vehicle=vehicle,
            credit_assessment=self.assessment,
            principal_amount=Decimal("12000.00"),
            annual_interest_rate=Decimal("10.00"),
            duration_months=12,
            first_repayment_date=timezone.localdate() + timedelta(days=7),
        )
        loan.status = Loan.Status.ACTIVE
        loan.outstanding_balance = loan.total_repayable
        loan.activated_at = timezone.now()
        loan.save()
        return loan

    def test_initialize_creates_pending_payment_and_default_amount(self):
        loan = self.make_loan(1)
        payment, result = initialize_payment(
            actor=self.operator, loan_id=loan.pk, provider_name="MOCK_MOMO"
        )
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.amount, loan.outstanding_balance)
        self.assertEqual(payment.currency, loan.currency)
        self.assertTrue(payment.reference.startswith("MOMO-"))
        self.assertIn("initialization", payment.raw_event)

    def test_initialize_rejects_inactive_loan_and_bad_amount(self):
        loan = self.make_loan(2)
        with self.assertRaises(ValidationError):
            initialize_payment(
                actor=self.operator,
                loan_id=loan.pk,
                provider_name="MOCK_MOMO",
                amount=Decimal("999999.00"),
            )
        other = self.make_loan(3)
        # The database forbids PENDING with a nonzero balance, so reset both.
        other.status = Loan.Status.PENDING
        other.outstanding_balance = Decimal("0.00")
        other.save()
        with self.assertRaises(ValidationError):
            initialize_payment(actor=self.operator, loan_id=other.pk, provider_name="MOCK_MOMO")

    def test_success_settles_once_and_updates_balance(self):
        loan = self.make_loan(4)
        payment, _ = initialize_payment(
            actor=self.operator, loan_id=loan.pk, provider_name="MOCK_MOMO"
        )
        verified = {
            "status": "success",
            "provider_transaction_id": "T-123",
            "amount": str(payment.amount),
            "currency": payment.currency,
            "raw": {},
        }
        self.assertEqual(_apply_success(payment, verified), "processed")
        loan.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        # The default initialize amount is the full outstanding balance, so this
        # single settlement retires the demo loan entirely.
        self.assertEqual(loan.outstanding_balance, Decimal("0.00"))
        self.assertEqual(loan.status, Loan.Status.COMPLETED)
        # Redelivery of the same settlement must not reduce the balance twice.
        self.assertEqual(_apply_success(payment, verified), "already processed")
        loan.refresh_from_db()
        self.assertEqual(loan.outstanding_balance, Decimal("0.00"))
        self.assertEqual(loan.status, Loan.Status.COMPLETED)

    def test_success_marks_completed_loan_when_fully_paid(self):
        loan = self.make_loan(5)
        payment, _ = initialize_payment(
            actor=self.operator, loan_id=loan.pk, provider_name="MOCK_MOMO"
        )
        payment.amount = loan.outstanding_balance
        payment.save()
        verified = {
            "status": "success",
            "provider_transaction_id": "T-124",
            "amount": str(payment.amount),
            "currency": payment.currency,
            "raw": {},
        }
        _apply_success(payment, verified)
        loan.refresh_from_db()
        self.assertEqual(loan.outstanding_balance, Decimal("0.00"))
        self.assertEqual(loan.status, Loan.Status.COMPLETED)

    def test_amount_mismatch_is_recorded_as_failure(self):
        loan = self.make_loan(6)
        payment, _ = initialize_payment(
            actor=self.operator, loan_id=loan.pk, provider_name="MOCK_MOMO"
        )
        verified = {
            "status": "success",
            "provider_transaction_id": "T-125",
            "amount": "0.01",
            "currency": payment.currency,
            "raw": {},
        }
        self.assertEqual(_apply_success(payment, verified), "processed")
        payment.refresh_from_db()
        loan.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertIn("amount", payment.failure_reason.lower())
        self.assertEqual(loan.outstanding_balance, loan.total_repayable)

    def test_failure_leaves_balance_untouched(self):
        loan = self.make_loan(7)
        payment, _ = initialize_payment(
            actor=self.operator, loan_id=loan.pk, provider_name="MOCK_MOMO"
        )
        self.assertEqual(_apply_failure(payment, "insufficient funds"), "processed")
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        loan.refresh_from_db()
        self.assertEqual(loan.outstanding_balance, loan.total_repayable)
        self.assertEqual(_apply_failure(payment, "retry"), "already processed")


class MockMomoTests(PaymentFixtureMixin, APITestCase):
    def make_loan(self, index):
        vehicle = Vehicle.objects.create(
            registration_number=f"MOMO-{index:03d}",
            vin=f"1HGCM82633A00{index:04d}",
            make="Toyota",
            model_name="Corolla",
            year=2020,
            customer=self.profile,
        )
        loan = create_loan(
            actor=self.operator,
            customer=self.profile,
            vehicle=vehicle,
            credit_assessment=self.assessment,
            principal_amount=Decimal("12000.00"),
            annual_interest_rate=Decimal("10.00"),
            duration_months=12,
            first_repayment_date=timezone.localdate() + timedelta(days=7),
        )
        loan.status = Loan.Status.ACTIVE
        loan.outstanding_balance = loan.total_repayable
        loan.activated_at = timezone.now()
        loan.save()
        return loan

    def test_simulated_lifecycle_success(self):
        loan = self.make_loan(1)
        payment, _ = initialize_payment(
            actor=self.operator, loan_id=loan.pk, provider_name="MOCK_MOMO"
        )
        provider = get_provider("MOCK_MOMO")
        self.assertEqual(provider.verify_payment(payment.reference)["status"], "pending")
        provider.resolve(payment.reference, "success")
        verified = provider.verify_payment(payment.reference)
        self.assertEqual(verified["status"], "success")
        self.assertEqual(_apply_success(payment, verified), "processed")
        loan.refresh_from_db()
        self.assertEqual(loan.outstanding_balance, loan.total_repayable - payment.amount)

    def test_simulated_lifecycle_failed(self):
        loan = self.make_loan(2)
        payment, _ = initialize_payment(
            actor=self.operator, loan_id=loan.pk, provider_name="MOCK_MOMO"
        )
        provider = get_provider("MOCK_MOMO")
        provider.resolve(payment.reference, "failed")
        verified = provider.verify_payment(payment.reference)
        self.assertEqual(verified["status"], "failed")
        self.assertEqual(
            _apply_failure(payment, "Provider reported the payment failed."), "processed"
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)

    def test_duplicate_callback_is_ignored(self):
        loan = self.make_loan(3)
        payment, _ = initialize_payment(
            actor=self.operator, loan_id=loan.pk, provider_name="MOCK_MOMO"
        )
        provider = get_provider("MOCK_MOMO")
        provider.resolve(payment.reference, "success")
        body = json.dumps(
            {"event": "charge.success", "data": {"reference": payment.reference}}
        ).encode()
        first = handle_webhook(provider_name="MOCK_MOMO", body=body, signature=sign_momo(body))
        self.assertEqual(first["outcome"], "processed")
        loan.refresh_from_db()
        balance_after_first = loan.outstanding_balance
        second = handle_webhook(provider_name="MOCK_MOMO", body=body, signature=sign_momo(body))
        self.assertEqual(second["outcome"], "ignored")
        self.assertIn("duplicate", second["note"])
        loan.refresh_from_db()
        self.assertEqual(loan.outstanding_balance, balance_after_first)
        self.assertEqual(Payment.objects.filter(reference=payment.reference).count(), 1)


class PaystackWebhookTests(PaymentFixtureMixin, APITestCase):
    def make_loan(self, index):
        vehicle = Vehicle.objects.create(
            registration_number=f"PSK-{index:03d}",
            vin=f"1HGCM82633A00{index:04d}",
            make="Toyota",
            model_name="Corolla",
            year=2020,
            customer=self.profile,
        )
        loan = create_loan(
            actor=self.operator,
            customer=self.profile,
            vehicle=vehicle,
            credit_assessment=self.assessment,
            principal_amount=Decimal("12000.00"),
            annual_interest_rate=Decimal("10.00"),
            duration_months=12,
            first_repayment_date=timezone.localdate() + timedelta(days=7),
        )
        loan.status = Loan.Status.ACTIVE
        loan.outstanding_balance = loan.total_repayable
        loan.activated_at = timezone.now()
        loan.save()
        return loan

    def setUp(self):
        # A dedicated HTTP client: webhook requests are unauthenticated by design.
        self.webhook_client = Client()

    def test_invalid_signature_is_rejected_and_audited(self):
        loan = self.make_loan(1)
        payment, _ = initialize_payment(
            actor=self.operator, loan_id=loan.pk, provider_name="PAYSTACK"
        )
        body = json.dumps(
            {"event": "charge.success", "data": {"reference": payment.reference}}
        ).encode()
        response = self.webhook_client.post(
            reverse("payments:paystack-webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE="deadbeef",
        )
        self.assertEqual(response.status_code, 401)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(
            WebhookEvent.objects.filter(
                provider="PAYSTACK", status=WebhookEvent.Status.IGNORED
            ).count(),
            1,
        )

    def test_valid_signature_with_unknown_reference_is_ignored(self):
        self.make_loan(2)
        body = json.dumps(
            {"event": "charge.success", "data": {"reference": "PSK-DOES-NOT-EXIST"}}
        ).encode()
        secret = "test-paystack-secret"
        with self.settings(PAYSTACK_SECRET_KEY=secret):
            response = self.webhook_client.post(
                reverse("payments:paystack-webhook"),
                data=body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE=sign_paystack(body, secret),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            WebhookEvent.objects.filter(provider="PAYSTACK", note="unknown reference").count(),
            1,
        )

    def test_duplicate_delivery_applies_balance_once(self):
        loan = self.make_loan(3)
        payment, _ = initialize_payment(
            actor=self.operator, loan_id=loan.pk, provider_name="PAYSTACK"
        )
        verified = {
            "status": "success",
            "provider_transaction_id": "T-900",
            "amount": str(payment.amount),
            "currency": payment.currency,
            "raw": {},
        }
        self.assertEqual(_apply_success(payment, verified), "processed")
        loan.refresh_from_db()
        expected = loan.outstanding_balance
        secret = "test-paystack-secret"
        body = json.dumps(
            {"event": "charge.success", "data": {"reference": payment.reference}}
        ).encode()
        with self.settings(PAYSTACK_SECRET_KEY=secret):
            for _ in range(2):
                response = self.webhook_client.post(
                    reverse("payments:paystack-webhook"),
                    data=body,
                    content_type="application/json",
                    HTTP_X_PAYSTACK_SIGNATURE=sign_paystack(body, secret),
                )
                self.assertEqual(response.status_code, 200)
        loan.refresh_from_db()
        self.assertEqual(loan.outstanding_balance, expected)
        # Both deliveries arrive after the direct settlement, so both are audited
        # as duplicates and neither touches the balance again.
        notes = list(
            WebhookEvent.objects.filter(provider="PAYSTACK").values_list("note", flat=True)
        )
        self.assertEqual(notes.count("duplicate delivery; payment already SUCCESS"), 2)


class PaymentAPITests(PaymentFixtureMixin, APITestCase):
    def make_loan(self, index):
        vehicle = Vehicle.objects.create(
            registration_number=f"API-{index:03d}",
            vin=f"1HGCM82633A00{index:04d}",
            make="Toyota",
            model_name="Corolla",
            year=2020,
            customer=self.profile,
        )
        loan = create_loan(
            actor=self.operator,
            customer=self.profile,
            vehicle=vehicle,
            credit_assessment=self.assessment,
            principal_amount=Decimal("12000.00"),
            annual_interest_rate=Decimal("10.00"),
            duration_months=12,
            first_repayment_date=timezone.localdate() + timedelta(days=7),
        )
        loan.status = Loan.Status.ACTIVE
        loan.outstanding_balance = loan.total_repayable
        loan.activated_at = timezone.now()
        loan.save()
        return loan

    def setUp(self):
        self.customer.refresh_from_db()

    def authenticate(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
        )

    def test_authentication_required(self):
        loan = self.make_loan(1)
        self.assertEqual(
            self.client.post(
                reverse("payments:initialize"),
                {"loan_id": str(loan.pk), "provider": "MOCK_MOMO"},
                format="json",
                secure=True,
            ).status_code,
            401,
        )

    def test_operations_can_initialize_and_list(self):
        loan = self.make_loan(2)
        self.authenticate(self.operator)
        response = self.client.post(
            reverse("payments:initialize"),
            {"loan_id": str(loan.pk), "provider": "MOCK_MOMO"},
            format="json",
            secure=True,
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(response.data["provider"], "MOCK_MOMO")
        listing = self.client.get(reverse("payments:list"), secure=True)
        self.assertEqual(listing.data["count"], 1)

    def test_customer_can_read_own_payment_but_not_initialize(self):
        loan = self.make_loan(3)
        self.authenticate(self.operator)
        payment = self.client.post(
            reverse("payments:initialize"),
            {"loan_id": str(loan.pk), "provider": "MOCK_MOMO"},
            format="json",
            secure=True,
        ).data
        self.authenticate(self.customer)
        self.assertEqual(
            self.client.post(
                reverse("payments:initialize"),
                {"loan_id": str(loan.pk), "provider": "MOCK_MOMO"},
                format="json",
                secure=True,
            ).status_code,
            403,
        )
        listing = self.client.get(reverse("payments:list"), secure=True)
        self.assertEqual(listing.data["count"], 1)
        verify = self.client.get(
            reverse("payments:verify", kwargs={"reference": payment["reference"]}),
            secure=True,
        )
        self.assertEqual(verify.status_code, 200)
        self.assertIn("detail", verify.data)

    def test_customer_cannot_see_webhook_events(self):
        self.authenticate(self.customer)
        response = self.client.get(reverse("payments:webhook-events"), secure=True)
        self.assertEqual(response.data["count"], 0)

    def test_admin_sees_webhook_events(self):
        WebhookEvent.objects.create(
            provider="PAYSTACK",
            event_type="charge.success",
            payload={},
        )
        self.authenticate(self.admin)
        response = self.client.get(reverse("payments:webhook-events"), secure=True)
        self.assertEqual(response.data["count"], 1)

    def test_momo_simulate_requires_staff_session(self):
        loan = self.make_loan(4)
        self.authenticate(self.operator)
        payment = self.client.post(
            reverse("payments:initialize"),
            {"loan_id": str(loan.pk), "provider": "MOCK_MOMO"},
            format="json",
            secure=True,
        ).data
        # JWT-authenticated staff is not a staff *session*; the simulator must
        # refuse so a leaked access token cannot resolve simulated charges.
        response = self.client.post(
            reverse("payments:momo-simulate"),
            {"reference": payment["reference"], "outcome": "success"},
            format="json",
            secure=True,
        )
        self.assertEqual(response.status_code, 403)
        staff_session_client = Client()
        staff_user = User.objects.create_user(
            username="pay_staff", role=User.Role.ADMIN, is_staff=True
        )
        staff_session_client.force_login(staff_user)
        response = staff_session_client.post(
            reverse("payments:momo-simulate"),
            {"reference": payment["reference"], "outcome": "success"},
            format="json",
            secure=True,
        )
        self.assertEqual(response.status_code, 200, response.data)
        payment_row = Payment.objects.get(reference=payment["reference"])
        self.assertEqual(payment_row.status, Payment.Status.SUCCESS)
        loan.refresh_from_db()
        self.assertEqual(loan.outstanding_balance, loan.total_repayable - payment_row.amount)

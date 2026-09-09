from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from credit.models import CreditAssessment
from customers.models import CustomerProfile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User
from vehicles.models import Vehicle

from .calculations import calculate_terms, monthly_due_date
from .models import Loan, RepaymentInstallment
from .services import check_affordability, check_eligibility, create_loan, transition_loan

CENT = Decimal("0.01")


class LoanFixtureMixin:
    """Shared factories. Tests that mutate a profile/vehicle create their own fixtures."""

    @classmethod
    def make_customer(cls, username, **profile_overrides):
        user = User.objects.create_user(username=username)
        fields = {
            "full_name": username.replace("_", " ").title(),
            "phone": "+233201234567",
            "monthly_income": "6500.00",
            "employment_status": "EMPLOYED",
            "employment_duration_months": 24,
        }
        fields.update(profile_overrides)
        profile = CustomerProfile.objects.create(user=user, **fields)
        return user, profile

    @classmethod
    def make_vehicle(cls, index, customer=None, status=Vehicle.Status.ACTIVE):
        return Vehicle.objects.create(
            registration_number=f"LOAN-{index:03d}",
            vin=f"1HGCM82633A00{index:04d}",
            make="Toyota",
            model_name="Corolla",
            year=2020,
            customer=customer,
            status=status,
        )

    @staticmethod
    def make_assessment(customer, decision=CreditAssessment.Decision.APPROVED):
        # Mirrors the snapshot keys saved by credit.services.assess_customer, whose
        # json.dumps(default=str) renders Decimal columns with two decimal places.
        snapshot = {
            "currency": customer.currency,
            "employment_status": customer.employment_status,
            "employment_duration_months": customer.employment_duration_months,
            "monthly_income": f"{Decimal(customer.monthly_income):.2f}",
            "existing_debt": f"{Decimal(customer.existing_debt):.2f}",
            "monthly_debt_repayment": f"{Decimal(customer.monthly_debt_repayment):.2f}",
            "profile_updated_at": customer.updated_at.isoformat(),
            "data_source": "self_reported_demo",
            "repayment_history": None,
            "transaction_history": None,
        }
        return CreditAssessment.objects.create(
            customer=customer,
            rules_version="demo-v1",
            rules_snapshot={},
            input_snapshot=snapshot,
            score=700,
            risk_band=CreditAssessment.RiskBand.LOW,
            decision=decision,
            factors=[],
            ratios={},
        )

    @staticmethod
    def make_loan(customer, vehicle, assessment, actor, **overrides):
        payload = {
            "principal_amount": Decimal("12000.00"),
            "annual_interest_rate": Decimal("10.00"),
            "duration_months": 12,
            "first_repayment_date": timezone.localdate() + timedelta(days=7),
        }
        payload.update(overrides)
        return create_loan(
            actor=actor,
            customer=customer,
            vehicle=vehicle,
            credit_assessment=assessment,
            **payload,
        )


class LoanCalculationTests(LoanFixtureMixin):
    def test_flat_interest_terms_and_even_schedule(self):
        terms = calculate_terms(
            principal=Decimal("12000.00"),
            annual_rate=Decimal("10.00"),
            months=12,
            first_due_date=date(2026, 9, 15),
        )
        self.assertEqual(terms["total_interest"], Decimal("1200.00"))
        self.assertEqual(terms["total_repayable"], Decimal("13200.00"))
        self.assertEqual(terms["monthly_repayment"], Decimal("1100.00"))
        self.assertEqual(terms["final_repayment"], Decimal("1100.00"))
        self.assertEqual(len(terms["installments"]), 12)
        for index, installment in enumerate(terms["installments"]):
            self.assertEqual(installment["number"], index + 1)
            self.assertEqual(installment["amount_due"], Decimal("1100.00"))
        first = terms["installments"][0]
        self.assertEqual(first["principal_due"], Decimal("1000.00"))
        self.assertEqual(first["interest_due"], Decimal("100.00"))
        self.assertEqual(first["due_date"], date(2026, 9, 15))

    def test_rounding_residual_lands_on_final_installment(self):
        terms = calculate_terms(
            principal=Decimal("10000.01"),
            annual_rate=Decimal("12.34"),
            months=3,
            first_due_date=date(2026, 9, 15),
        )
        self.assertEqual(terms["total_interest"], Decimal("308.50"))
        self.assertEqual(terms["total_repayable"], Decimal("10308.51"))
        regular = Decimal("3333.33") + Decimal("102.83")
        self.assertEqual(terms["monthly_repayment"], regular)
        final = terms["installments"][-1]
        self.assertEqual(final["principal_due"], Decimal("3333.35"))
        self.assertEqual(final["interest_due"], Decimal("102.84"))
        self.assertEqual(terms["final_repayment"], Decimal("3436.19"))
        total = sum(item["amount_due"] for item in terms["installments"])
        self.assertEqual(total, terms["total_repayable"])

    def test_due_dates_clamp_to_month_end(self):
        self.assertEqual(monthly_due_date(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(monthly_due_date(date(2026, 11, 30), 3), date(2027, 2, 28))
        self.assertEqual(monthly_due_date(date(2026, 9, 15), 12), date(2027, 9, 15))

    def test_invalid_terms_are_rejected(self):
        with self.assertRaises(ValueError):
            calculate_terms(
                principal=Decimal("100.00"),
                annual_rate=Decimal("10.00"),
                months=0,
                first_due_date=date(2026, 9, 15),
            )
        with self.assertRaises(ValueError):
            calculate_terms(
                principal=2 * CENT,
                annual_rate=Decimal("10.00"),
                months=3,
                first_due_date=date(2026, 9, 15),
            )
        with self.assertRaises(ValueError):
            calculate_terms(
                principal=Decimal("100.00"),
                annual_rate=Decimal("-1.00"),
                months=3,
                first_due_date=date(2026, 9, 15),
            )


class LoanServiceTests(LoanFixtureMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer, cls.profile = cls.make_customer("loan_service_customer")
        cls.operator = User.objects.create_user(
            username="loan_service_operator", role=User.Role.OPERATIONS
        )
        cls.vehicle = cls.make_vehicle(1, customer=cls.profile)
        cls.assessment = cls.make_assessment(cls.profile)

    def setUp(self):
        self.customer.refresh_from_db()
        self.vehicle.refresh_from_db()
        self.assessment.refresh_from_db()

    def create_loan(self, **overrides):
        return self.make_loan(
            self.profile, self.vehicle, self.assessment, self.operator, **overrides
        )

    def test_create_loan_persists_terms_schedule_and_snapshot(self):
        loan = self.create_loan()
        self.assertEqual(loan.status, Loan.Status.PENDING)
        self.assertEqual(loan.currency, "GHS")
        self.assertEqual(loan.principal_amount, Decimal("12000.00"))
        self.assertEqual(loan.total_interest, Decimal("1200.00"))
        self.assertEqual(loan.total_repayable, Decimal("13200.00"))
        self.assertEqual(loan.monthly_repayment, Decimal("1100.00"))
        self.assertEqual(loan.outstanding_balance, Decimal("0.00"))
        self.assertEqual(loan.policy_version, "demo-flat-v1")
        self.assertEqual(loan.installments.count(), 12)
        self.assertEqual(loan.origination_snapshot["combined_monthly_obligation"], "1100.00")
        self.assertEqual(loan.installments.first().due_date, loan.first_repayment_date)

    def test_create_loan_rejects_second_open_loan_on_vehicle(self):
        self.create_loan()
        with self.assertRaises(ValidationError) as context:
            self.create_loan()
        self.assertIn("vehicle", context.exception.detail)

    def test_one_open_loan_per_vehicle_database_constraint(self):
        loan = self.create_loan()
        clone = Loan.objects.get(pk=loan.pk)
        clone.id = None
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                clone.save()

    def test_create_loan_rejects_unapproved_or_foreign_assessment(self):
        review = self.make_assessment(self.profile, decision=CreditAssessment.Decision.REVIEW)
        with self.assertRaises(ValidationError):
            self.make_loan(self.profile, self.vehicle, review, self.operator)
        _, other_profile = self.make_customer("loan_service_other")
        foreign = self.make_assessment(other_profile)
        with self.assertRaises(ValidationError):
            self.make_loan(self.profile, self.vehicle, foreign, self.operator)

    def test_create_loan_rejects_stale_assessment(self):
        _, profile, vehicle, assessment = self.private_fixture("loan_service_stale")
        CreditAssessment.objects.filter(pk=assessment.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )
        assessment.refresh_from_db()
        with self.assertRaises(ValidationError) as context:
            self.make_loan(profile, vehicle, assessment, self.operator)
        self.assertIn("credit_assessment", context.exception.detail)

    def test_create_loan_rejects_changed_financial_inputs(self):
        _, profile, vehicle, assessment = self.private_fixture("loan_service_mutated")
        CustomerProfile.objects.filter(pk=profile.pk).update(monthly_income="7000.00")
        profile.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.make_loan(profile, vehicle, assessment, self.operator)

    def test_create_loan_rejects_unaffordable_combination(self):
        second_vehicle = self.make_vehicle(2, customer=self.profile)
        self.create_loan()
        assessment = self.make_assessment(self.profile)
        with self.assertRaises(ValidationError) as context:
            self.make_loan(
                self.profile,
                second_vehicle,
                assessment,
                self.operator,
                principal_amount=Decimal("31000.00"),
            )
        self.assertIn("principal_amount", context.exception.detail)

    def test_check_affordability_rejects_currency_mismatch(self):
        loan = self.create_loan()
        CustomerProfile.objects.filter(pk=self.profile.pk).update(currency="NGN")
        self.profile.refresh_from_db()
        terms = {
            "monthly_repayment": loan.monthly_repayment,
            "final_repayment": loan.final_repayment,
        }
        with self.assertRaises(ValidationError):
            check_affordability(self.profile, terms)

    def test_eligibility_requires_customer_role_and_active_vehicle(self):
        staff, profile = self.make_customer("loan_service_staffrole")
        User.objects.filter(pk=staff.pk).update(role=User.Role.OPERATIONS)
        staff.refresh_from_db()
        assessment = self.make_assessment(profile)
        vehicle = self.make_vehicle(3, customer=profile)
        with self.assertRaises(ValidationError):
            check_eligibility(
                profile, vehicle, assessment, timezone.localdate() + timedelta(days=7)
            )
        Vehicle.objects.filter(pk=vehicle.pk).update(status=Vehicle.Status.MAINTENANCE)
        vehicle.refresh_from_db()
        with self.assertRaises(ValidationError):
            check_eligibility(
                self.profile,
                self.vehicle,
                self.assessment,
                timezone.localdate() + timedelta(days=7),
            )

    def test_first_repayment_window_is_enforced(self):
        with self.assertRaises(ValidationError):
            check_eligibility(self.profile, self.vehicle, self.assessment, timezone.localdate())
        with self.assertRaises(ValidationError):
            check_eligibility(
                self.profile,
                self.vehicle,
                self.assessment,
                timezone.localdate() + timedelta(days=91),
            )

    def private_fixture(self, username):
        user, profile = self.make_customer(username)
        return user, profile, self.make_vehicle(90, customer=profile), self.make_assessment(profile)

    def test_activate_sets_outstanding_balance(self):
        loan = self.create_loan()
        updated = transition_loan(loan_id=loan.pk, action="activate")
        self.assertEqual(updated.status, Loan.Status.ACTIVE)
        self.assertEqual(updated.outstanding_balance, loan.total_repayable)
        self.assertIsNotNone(updated.activated_at)

    def test_cancel_and_unknown_action(self):
        loan = self.create_loan()
        cancelled = transition_loan(loan_id=loan.pk, action="cancel")
        self.assertEqual(cancelled.status, Loan.Status.CANCELLED)
        self.assertIsNotNone(cancelled.cancelled_at)
        with self.assertRaises(ValidationError):
            transition_loan(loan_id=cancelled.pk, action="cancel")
        # Unknown actions are rejected before the status guard, so use a pending loan.
        _, profile, vehicle, assessment = self.private_fixture("loan_service_unknown")
        pending = self.make_loan(profile, vehicle, assessment, self.operator)
        with self.assertRaises(ValueError):
            transition_loan(loan_id=pending.pk, action="explode")

    def test_status_balance_consistency_constraint(self):
        loan = self.create_loan()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Loan.objects.filter(pk=loan.pk).update(outstanding_balance=loan.total_repayable)

    def test_positive_principal_constraint(self):
        loan = self.create_loan()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Loan.objects.filter(pk=loan.pk).update(principal_amount=Decimal("0.00"))

    def test_installment_amount_consistency_constraint(self):
        loan = self.create_loan()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RepaymentInstallment.objects.filter(loan=loan, number=1).update(
                    amount_due=Decimal("1.00")
                )


class LoanAPITests(LoanFixtureMixin, APITestCase):
    vehicle_index = 10

    @classmethod
    def setUpTestData(cls):
        # High reported income keeps affordability from masking the behaviour under test.
        cls.customer, cls.profile = cls.make_customer(
            "loan_api_customer", monthly_income="65000.00"
        )
        cls.other, cls.other_profile = cls.make_customer("loan_api_other")
        cls.operator = User.objects.create_user(
            username="loan_api_operator", role=User.Role.OPERATIONS
        )
        cls.admin = User.objects.create_user(username="loan_api_admin", role=User.Role.ADMIN)

    def setUp(self):
        # A vehicle may hold only one open loan, so each test gets fresh related rows.
        type(self).vehicle_index += 1
        self.vehicle = self.make_vehicle(self.vehicle_index, customer=self.profile)
        self.assessment = self.make_assessment(self.profile)
        self.customer.refresh_from_db()

    def authenticate(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
        )

    def payload(self, **overrides):
        return {
            "customer": str(self.profile.pk),
            "vehicle": str(self.vehicle.pk),
            "credit_assessment": str(self.assessment.pk),
            "principal_amount": "12000.00",
            "annual_interest_rate": "10.00",
            "duration_months": 12,
            "first_repayment_date": str(timezone.localdate() + timedelta(days=7)),
            **overrides,
        }

    def create_loan(self, **overrides):
        return self.client.post(
            reverse("loans:list"), self.payload(**overrides), format="json", secure=True
        )

    def test_authentication_required(self):
        self.assertEqual(self.create_loan().status_code, 401)
        self.assertEqual(self.client.get(reverse("loans:list"), secure=True).status_code, 401)

    def test_operations_and_admin_can_create_loans(self):
        pairs = [
            (self.operator, self.vehicle),
            (self.admin, self.make_vehicle(99, customer=self.profile)),
        ]
        for actor, vehicle in pairs:
            self.authenticate(actor)
            response = self.create_loan(vehicle=str(vehicle.pk))
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(UUID(response.data["id"]).version, 4)
            self.assertEqual(response.data["status"], "PENDING")
            self.assertEqual(response.data["outstanding_balance"], "0.00")
            self.assertEqual(response.data["total_repayable"], "13200.00")

    def test_customer_cannot_create_but_can_read_own_loan(self):
        self.authenticate(self.operator)
        loan = self.create_loan().data
        self.authenticate(self.customer)
        self.assertEqual(self.create_loan().status_code, 403)
        list_response = self.client.get(reverse("loans:list"), secure=True)
        self.assertEqual(list_response.data["count"], 1)
        self.assertEqual(list_response.data["results"][0]["id"], loan["id"])
        detail = reverse("loans:detail", kwargs={"pk": loan["id"]})
        self.assertEqual(self.client.get(detail, secure=True).status_code, 200)

    def test_customer_scope_hides_other_customers_loans(self):
        self.authenticate(self.operator)
        loan = self.create_loan().data
        self.authenticate(self.other)
        detail = reverse("loans:detail", kwargs={"pk": loan["id"]})
        self.assertEqual(self.client.get(detail, secure=True).status_code, 404)
        schedule = reverse("loans:installments", kwargs={"pk": loan["id"]})
        self.assertEqual(self.client.get(schedule, secure=True).status_code, 404)

    def test_installments_are_exposed_in_order(self):
        self.authenticate(self.operator)
        loan = self.create_loan().data
        schedule = reverse("loans:installments", kwargs={"pk": loan["id"]})
        response = self.client.get(schedule, secure=True)
        self.assertEqual(response.status_code, 200)
        numbers = [row["number"] for row in response.data["results"]]
        self.assertEqual(numbers, list(range(1, 13)))
        self.assertEqual(response.data["results"][0]["amount_due"], "1100.00")

    def test_create_rejects_invalid_payloads(self):
        self.authenticate(self.operator)
        with_unknown = self.create_loan(monthly_repayment="1.00")
        self.assertEqual(with_unknown.status_code, 400)
        past_due = self.create_loan(
            first_repayment_date=str(timezone.localdate() - timedelta(days=1))
        )
        self.assertEqual(past_due.status_code, 400)
        zero_principal = self.create_loan(principal_amount="0.00")
        self.assertEqual(zero_principal.status_code, 400)

    def test_activate_and_cancel_endpoints(self):
        self.authenticate(self.operator)
        loan = self.create_loan().data
        activate = reverse("loans:activate", kwargs={"pk": loan["id"]})
        response = self.client.post(activate, {}, format="json", secure=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "ACTIVE")
        self.assertEqual(response.data["outstanding_balance"], "13200.00")
        cancel = reverse("loans:cancel", kwargs={"pk": loan["id"]})
        self.assertEqual(self.client.post(cancel, {}, format="json", secure=True).status_code, 400)

    def test_activate_rechecks_changed_financial_inputs(self):
        vehicle = self.make_vehicle(98, customer=self.profile)
        loan = self.make_loan(self.profile, vehicle, self.assessment, self.operator)
        CustomerProfile.objects.filter(pk=self.profile.pk).update(monthly_income="9999.00")
        self.authenticate(self.operator)
        activate = reverse("loans:activate", kwargs={"pk": loan.pk})
        response = self.client.post(activate, {}, format="json", secure=True)
        self.assertEqual(response.status_code, 400)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.PENDING)

    def test_customer_cannot_transition_loans(self):
        self.authenticate(self.operator)
        loan = self.create_loan().data
        self.authenticate(self.customer)
        activate = reverse("loans:activate", kwargs={"pk": loan["id"]})
        self.assertEqual(
            self.client.post(activate, {}, format="json", secure=True).status_code, 403
        )

    def test_actions_reject_request_body(self):
        self.authenticate(self.operator)
        loan = self.create_loan().data
        activate = reverse("loans:activate", kwargs={"pk": loan["id"]})
        response = self.client.post(
            activate, {"outstanding_balance": "0.00"}, format="json", secure=True
        )
        self.assertEqual(response.status_code, 400)

from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4

from customers.models import CustomerProfile
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User

from .models import CreditAssessment
from .rules import RULES
from .scoring import CreditInputs, score_customer


class CreditScoringTests(SimpleTestCase):
    def inputs(self, **changes):
        return replace(
            CreditInputs(
                currency="GHS",
                monthly_income=Decimal("6500"),
                existing_debt=Decimal("2000"),
                monthly_debt_repayment=Decimal("250"),
                employment_status="EMPLOYED",
                employment_duration_months=24,
            ),
            **changes,
        )

    def points(self, result, code):
        return next(f["points"] for f in result["factors"] if f["code"] == code)

    def test_demo_profile_is_explainable_and_deterministic(self):
        result = score_customer(self.inputs())
        self.assertEqual(result, score_customer(self.inputs()))
        self.assertEqual(
            (result["score"], result["risk_band"], result["decision"]), (850, "LOW", "APPROVED")
        )
        self.assertEqual(result["score"], sum(f["points"] for f in result["factors"]))
        self.assertEqual(result["ratios"]["debt_to_income"], "0.0385")

    def test_zero_income_has_no_division_and_is_rejected(self):
        result = score_customer(self.inputs(monthly_income=Decimal("0")))
        self.assertEqual(result["score"], 300)
        self.assertEqual(result["decision"], "REJECTED")
        self.assertIsNone(result["ratios"]["debt_to_income"])

    def test_dti_boundaries_compare_unrounded_values(self):
        for payment, points in [
            ("200", 200),
            ("200.01", 125),
            ("400", 125),
            ("400.01", 50),
            ("600", 50),
            ("600.01", 0),
        ]:
            with self.subTest(payment=payment):
                result = score_customer(
                    self.inputs(
                        monthly_income=Decimal("1000"), monthly_debt_repayment=Decimal(payment)
                    )
                )
                self.assertEqual(self.points(result, "DEBT_TO_INCOME"), points)

    def test_high_dti_overrides_score_based_decision(self):
        result = score_customer(self.inputs(monthly_debt_repayment=Decimal("4000")))
        self.assertGreaterEqual(result["score"], RULES.medium_risk_minimum)
        self.assertEqual((result["risk_band"], result["decision"]), ("HIGH", "REJECTED"))

    def test_outstanding_debt_boundaries(self):
        for debt, points in [("1000", 100), ("1000.01", 50), ("3000", 50), ("3000.01", 0)]:
            with self.subTest(debt=debt):
                result = score_customer(
                    self.inputs(monthly_income=Decimal("1000"), existing_debt=Decimal(debt))
                )
                self.assertEqual(self.points(result, "DEBT_BALANCE"), points)

    def test_employment_duration_only_counts_current_employment(self):
        for duration, points in [(5, 0), (6, 40), (23, 40), (24, 75)]:
            result = score_customer(self.inputs(employment_duration_months=duration))
            self.assertEqual(self.points(result, "EMPLOYMENT_DURATION"), points)
        result = score_customer(self.inputs(employment_status="UNEMPLOYED"))
        self.assertEqual(self.points(result, "EMPLOYMENT_DURATION"), 0)

    def test_missing_monthly_payment_requires_review(self):
        result = score_customer(self.inputs(monthly_debt_repayment=Decimal("0")))
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("DEBT_PAYMENT_MISSING", [f["code"] for f in result["factors"]])

    def test_medium_and_high_risk_score_bands(self):
        medium = score_customer(
            self.inputs(
                monthly_income=Decimal("1000"),
                existing_debt=Decimal("1000"),
                monthly_debt_repayment=Decimal("500"),
                employment_status="UNEMPLOYED",
            )
        )
        high = score_customer(
            self.inputs(
                monthly_income=Decimal("1000"),
                existing_debt=Decimal("4000"),
                monthly_debt_repayment=Decimal("500"),
                employment_status="UNEMPLOYED",
            )
        )
        self.assertEqual((medium["score"], medium["decision"]), (550, "REVIEW"))
        self.assertEqual((high["score"], high["decision"]), (450, "REJECTED"))

    def test_currency_and_proportional_amounts_do_not_change_score(self):
        original = score_customer(self.inputs())
        scaled = score_customer(
            self.inputs(
                currency="NGN",
                monthly_income=Decimal("650000"),
                existing_debt=Decimal("200000"),
                monthly_debt_repayment=Decimal("25000"),
            )
        )
        self.assertEqual(original, scaled)

    def test_unavailable_history_is_not_fabricated(self):
        result = score_customer(self.inputs())
        self.assertEqual(self.points(result, "REPAYMENT_HISTORY_UNAVAILABLE"), 0)
        self.assertEqual(self.points(result, "TRANSACTION_HISTORY_UNAVAILABLE"), 0)

    def test_rules_are_injectable_and_inputs_are_unchanged(self):
        inputs = self.inputs()
        result = score_customer(inputs, replace(RULES, version="test-v2", income_points=50))
        self.assertEqual(result["score"], 800)
        self.assertEqual(inputs, self.inputs())

    def test_negative_inputs_are_rejected(self):
        for field in ["monthly_income", "existing_debt", "monthly_debt_repayment"]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                score_customer(self.inputs(**{field: Decimal("-1")}))


class CreditAssessmentAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="credit_customer")
        cls.other = User.objects.create_user(username="credit_other")
        cls.operator = User.objects.create_user(
            username="credit_operator", role=User.Role.OPERATIONS
        )
        cls.admin = User.objects.create_user(username="credit_admin", role=User.Role.ADMIN)
        cls.profile = CustomerProfile.objects.create(
            user=cls.customer,
            full_name="Demo Customer",
            phone="+233201234567",
            employment_status="EMPLOYED",
            employment_duration_months=24,
            monthly_income="6500",
            existing_debt="2000",
            monthly_debt_repayment="250",
        )

    def authenticate(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
        )

    def url(self, pk=None):
        return reverse("customers:assessments", kwargs={"customer_id": pk or self.profile.pk})

    def create(self, data=None):
        return self.client.post(
            self.url(), {} if data is None else data, format="json", secure=True
        )

    def test_assessment_persists_uuid_and_reproducible_snapshots(self):
        self.authenticate(self.customer)
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(UUID(str(response.data["id"])).version, 4)
        assessment = CreditAssessment.objects.get(pk=response.data["id"])
        self.assertEqual(assessment.created_by, self.customer)
        self.assertEqual(assessment.rules_version, "demo-v1")
        self.assertEqual(assessment.rules_snapshot["version"], assessment.rules_version)
        snapshot = assessment.input_snapshot
        self.assertEqual(snapshot["monthly_income"], "6500.00")
        self.assertIsNone(snapshot["repayment_history"])
        self.assertEqual(assessment.score, 850)

    def test_profile_edits_do_not_change_saved_assessments(self):
        self.authenticate(self.customer)
        original = self.create().data
        CustomerProfile.objects.filter(pk=self.profile.pk).update(monthly_income=0)
        new = self.create().data
        self.assertEqual(new["decision"], "REJECTED")
        response = self.client.get(
            reverse("credit:detail", kwargs={"pk": original["id"]}), secure=True
        )
        self.assertEqual(response.data, original)
        self.assertNotEqual(original["id"], new["id"])
        self.assertEqual(self.client.get(self.url(), secure=True).data["count"], 2)

    def test_anonymous_and_other_customers_are_denied(self):
        self.assertEqual(self.create().status_code, 401)
        self.authenticate(self.customer)
        assessment = self.create().data
        self.authenticate(self.other)
        self.assertEqual(self.create().status_code, 404)
        self.assertEqual(self.client.get(self.url(), secure=True).status_code, 404)
        url = reverse("credit:detail", kwargs={"pk": assessment["id"]})
        self.assertEqual(self.client.get(url, secure=True).status_code, 404)

    def test_operations_and_admin_can_assess_and_read_customer(self):
        for actor in [self.operator, self.admin]:
            with self.subTest(role=actor.role):
                self.authenticate(actor)
                response = self.create()
                self.assertEqual(response.status_code, 201)
                self.assertEqual(str(response.data["created_by"]), str(actor.pk))
                url = reverse("credit:detail", kwargs={"pk": response.data["id"]})
                self.assertEqual(self.client.get(url, secure=True).status_code, 200)

    def test_clients_cannot_override_scoring_inputs(self):
        self.authenticate(self.customer)
        for payload in [{"score": 850}, {"monthly_income": "999999"}, {"rules_version": "other"}]:
            self.assertEqual(self.create(payload).status_code, 400)
        self.assertFalse(CreditAssessment.objects.exists())

    def test_assessments_are_read_only_and_missing_profiles_return_404(self):
        self.authenticate(self.customer)
        assessment = self.create().data
        url = reverse("credit:detail", kwargs={"pk": assessment["id"]})
        self.assertEqual(self.client.patch(url, {"score": 300}, secure=True).status_code, 405)
        self.assertEqual(self.client.delete(url, secure=True).status_code, 405)
        self.assertEqual(
            self.client.post(self.url(uuid4()), {}, format="json", secure=True).status_code, 404
        )

    def test_database_checks_score_and_outcome_values(self):
        self.authenticate(self.customer)
        assessment = self.create().data
        for fields in [
            {"score": 299},
            {"score": 851},
            {"decision": "INVALID"},
            {"risk_band": "OTHER"},
        ]:
            with (
                self.subTest(fields=fields),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                CreditAssessment.objects.filter(pk=assessment["id"]).update(**fields)

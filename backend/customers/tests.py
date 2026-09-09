from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User

from .models import CustomerProfile
from .serializers import CustomerProfileSerializer


class CustomerProfileTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="customer", email="demo@example.com")
        cls.other = User.objects.create_user(username="other")
        cls.operator = User.objects.create_user(username="operator", role=User.Role.OPERATIONS)
        cls.admin = User.objects.create_user(username="admin", role=User.Role.ADMIN)

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def payload(self, **overrides):
        return {
            "full_name": "Demo Customer",
            "phone": "+233201234567",
            "employment_status": "EMPLOYED",
            "employment_duration_months": 24,
            "monthly_income": "6500.00",
            "existing_debt": "2000.00",
            "monthly_debt_repayment": "250.00",
            "currency": "GHS",
            **overrides,
        }

    def create(self, **overrides):
        return self.client.post(
            reverse("customers:list"), self.payload(**overrides), format="json", secure=True
        )

    def profile(self, user):
        return CustomerProfile.objects.create(user=user, **self.payload())

    def detail(self, profile):
        return reverse("customers:detail", kwargs={"pk": profile.pk})

    def test_unauthenticated_requests_are_rejected(self):
        self.assertEqual(self.create().status_code, 401)
        self.assertEqual(self.client.get(reverse("customers:list"), secure=True).status_code, 401)

    def test_customer_creates_own_profile_with_uuid_and_decimal_amounts(self):
        self.authenticate(self.customer)
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(UUID(response.data["id"]).version, 4)
        self.assertEqual(response.data["user"], str(self.customer.pk))
        self.assertEqual(response.data["email"], self.customer.email)
        profile = CustomerProfile.objects.get(pk=response.data["id"])
        self.assertEqual(profile.monthly_income, Decimal("6500.00"))

    def test_customer_cannot_create_profile_for_another_user(self):
        self.authenticate(self.customer)
        self.assertEqual(self.create(user=str(self.other.pk)).status_code, 403)
        self.assertFalse(CustomerProfile.objects.exists())

    def test_customer_list_and_detail_hide_other_profiles(self):
        own, other = self.profile(self.customer), self.profile(self.other)
        self.authenticate(self.customer)
        response = self.client.get(reverse("customers:list"), secure=True)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(own.pk))
        self.assertEqual(self.client.get(self.detail(own), secure=True).status_code, 200)
        self.assertEqual(self.client.get(self.detail(other), secure=True).status_code, 404)
        self.assertEqual(
            self.client.patch(
                self.detail(other), {"monthly_income": "999"}, secure=True
            ).status_code,
            404,
        )

    def test_customer_can_patch_own_profile_but_not_ownership(self):
        profile = self.profile(self.customer)
        self.authenticate(self.customer)
        response = self.client.patch(
            self.detail(profile), {"monthly_income": "7000.25"}, format="json", secure=True
        )
        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.monthly_income, Decimal("7000.25"))
        response = self.client.patch(
            self.detail(profile), {"user": str(self.other.pk)}, format="json", secure=True
        )
        self.assertEqual(response.status_code, 400)

    def test_privileged_roles_can_list_and_update_all_profiles(self):
        profile = self.profile(self.customer)
        self.profile(self.other)
        for actor in [self.operator, self.admin]:
            with self.subTest(role=actor.role):
                self.authenticate(actor)
                response = self.client.get(reverse("customers:list"), secure=True)
                self.assertEqual(response.data["count"], 2)
                response = self.client.patch(
                    self.detail(profile), {"full_name": "Updated Name"}, format="json", secure=True
                )
                self.assertEqual(response.status_code, 200)
                response = self.client.patch(
                    self.detail(profile), {"user": str(self.other.pk)}, format="json", secure=True
                )
                self.assertEqual(response.status_code, 400)

    def test_operator_creates_only_for_selected_customer_account(self):
        self.authenticate(self.operator)
        self.assertEqual(self.create().status_code, 400)
        self.assertEqual(self.create(user=str(self.operator.pk)).status_code, 400)
        self.assertEqual(self.create(user=str(uuid4())).status_code, 400)
        self.assertEqual(self.create(user=str(self.customer.pk)).status_code, 201)

    def test_duplicate_profiles_are_rejected(self):
        self.authenticate(self.customer)
        self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.create().status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.profile(self.customer)

    def test_duplicate_created_after_validation_returns_validation_error(self):
        context = {"request": SimpleNamespace(user=self.customer)}
        first = CustomerProfileSerializer(data=self.payload(), context=context)
        second = CustomerProfileSerializer(data=self.payload(), context=context)
        self.assertTrue(first.is_valid(), first.errors)
        self.assertTrue(second.is_valid(), second.errors)
        first.save()
        with self.assertRaises(ValidationError):
            second.save()
        self.assertEqual(CustomerProfile.objects.count(), 1)

    def test_invalid_profile_inputs_are_rejected(self):
        self.authenticate(self.customer)
        invalid = [
            {"monthly_income": "-1"},
            {"existing_debt": "-1"},
            {"monthly_debt_repayment": "-1"},
            {"monthly_income": "1.234"},
            {"monthly_income": "NaN"},
            {"phone": "12345"},
            {"full_name": " "},
            {"employment_status": "UNKNOWN"},
            {"employment_duration_months": -1},
            {"currency": "INVALID"},
            {"email": "spoof@example.com"},
            {"id": str(uuid4())},
            {"repayment_history": "perfect"},
        ]
        for fields in invalid:
            with self.subTest(fields=fields):
                self.assertEqual(self.create(**fields).status_code, 400)
        self.assertFalse(CustomerProfile.objects.exists())

    def test_database_enforces_financial_and_choice_constraints(self):
        for fields in [
            {"monthly_income": "-1"},
            {"existing_debt": "-1"},
            {"monthly_debt_repayment": "-1"},
            {"currency": "XYZ"},
            {"employment_status": "UNKNOWN"},
            {"employment_duration_months": -1},
        ]:
            with self.subTest(fields=fields):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    CustomerProfile.objects.create(user=self.customer, **self.payload(**fields))

    def test_zero_income_is_valid_and_delete_is_not_exposed(self):
        self.authenticate(self.customer)
        response = self.create(monthly_income="0.00", employment_status="UNEMPLOYED")
        self.assertEqual(response.status_code, 201)
        profile = CustomerProfile.objects.get(pk=response.data["id"])
        self.assertEqual(self.client.delete(self.detail(profile), secure=True).status_code, 405)

    def test_swagger_documents_uuid_ids_and_protected_customer_routes(self):
        response = self.client.get("/api/schema/?format=json", secure=True)
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        profile = schema["components"]["schemas"]["CustomerProfile"]
        self.assertEqual(profile["properties"]["id"]["format"], "uuid")
        self.assertEqual(profile["properties"]["user"]["format"], "uuid")
        detail = schema["paths"]["/api/v1/customers/{id}/"]
        self.assertEqual(set(detail), {"get", "patch"})
        self.assertEqual(detail["get"]["security"], [{"jwtAuth": []}])

from datetime import timedelta
from uuid import UUID

from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .models import User


class AuthenticationTests(APITestCase):
    password = "Demo-only!CorrectHorse7492"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="customer", email="customer@example.com", password=cls.password
        )

    def setUp(self):
        cache.clear()

    def post(self, endpoint, data):
        return self.client.post(reverse(f"users:{endpoint}"), data, format="json", secure=True)

    def register(self, **overrides):
        return self.post(
            "register",
            {
                "username": "newcustomer",
                "email": "newcustomer@example.com",
                "password": self.password,
                **overrides,
            },
        )

    def login(self):
        response = self.post("login", {"username": "customer", "password": self.password})
        self.assertEqual(response.status_code, 200)
        return response.data

    def authorize(self, access):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def me(self):
        return self.client.get(reverse("users:me"), secure=True)

    def test_registration_hashes_password_and_creates_customer(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(UUID(response.data["id"]).version, 4)
        self.assertNotIn("password", response.data)
        user = User.objects.get(username="newcustomer")
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_registration_rejects_privilege_fields(self):
        for field, value in [("role", "ADMIN"), ("is_staff", True), ("is_superuser", True)]:
            with self.subTest(field=field):
                response = self.register(**{field: value})
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
        self.assertFalse(User.objects.filter(username="newcustomer").exists())

    def test_registration_rejects_weak_and_user_similar_passwords(self):
        for password in ["123", "password", "newcustomer"]:
            with self.subTest(password=password):
                response = self.register(password=password)
                self.assertEqual(response.status_code, 400)
                self.assertIn("password", response.data)

    def test_registration_rejects_duplicate_username_and_invalid_email(self):
        self.assertEqual(self.register(username="customer").status_code, 400)
        self.assertEqual(self.register(email="not-an-email").status_code, 400)

    def test_login_and_me_return_only_the_authenticated_user(self):
        tokens = self.login()
        self.assertEqual(set(tokens), {"access", "refresh"})
        self.authorize(tokens["access"])
        response = self.me()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(self.user.pk))
        self.assertEqual(AccessToken(tokens["access"])["user_uuid"], str(self.user.pk))
        self.assertEqual(
            set(response.data), {"id", "username", "email", "first_name", "last_name", "role"}
        )

    def test_me_rejects_anonymous_and_invalid_tokens(self):
        self.assertEqual(self.me().status_code, 401)
        self.authorize("invalid-token")
        self.assertEqual(self.me().status_code, 401)

    def test_me_does_not_accept_session_authentication(self):
        self.client.force_login(self.user)
        self.assertEqual(self.me().status_code, 401)

    def test_me_cannot_change_role(self):
        self.authorize(self.login()["access"])
        response = self.client.patch(
            reverse("users:me"), {"role": "ADMIN"}, format="json", secure=True
        )
        self.assertEqual(response.status_code, 405)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, User.Role.CUSTOMER)

    def test_bad_credentials_and_inactive_user_cannot_login(self):
        response = self.post("login", {"username": "customer", "password": "incorrect"})
        self.assertEqual(response.status_code, 401)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.post("login", {"username": "customer", "password": self.password})
        self.assertEqual(response.status_code, 401)

    def test_refresh_rotates_token_and_rejects_reuse(self):
        original = self.login()["refresh"]
        response = self.post("refresh", {"refresh": original})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["refresh"], original)
        self.authorize(response.data["access"])
        self.assertEqual(self.me().status_code, 200)
        self.assertEqual(self.post("refresh", {"refresh": original}).status_code, 401)
        self.assertEqual(
            self.post("refresh", {"refresh": response.data["refresh"]}).status_code, 200
        )

    def test_logout_revokes_only_the_supplied_refresh_token(self):
        tokens = self.login()
        other_session = self.login()
        self.assertEqual(self.post("logout", {"refresh": tokens["refresh"]}).status_code, 200)
        self.assertEqual(self.post("refresh", {"refresh": tokens["refresh"]}).status_code, 401)
        self.assertEqual(
            self.post("refresh", {"refresh": other_session["refresh"]}).status_code, 200
        )
        # Logout does not revoke an access token already issued for this session.
        self.authorize(tokens["access"])
        self.assertEqual(self.me().status_code, 200)

    def test_invalid_refresh_and_logout_payloads_are_rejected(self):
        access = self.login()["access"]
        for endpoint in ["refresh", "logout"]:
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.post(endpoint, {}).status_code, 400)
                self.assertEqual(self.post(endpoint, {"refresh": "invalid"}).status_code, 401)
                self.assertEqual(self.post(endpoint, {"refresh": access}).status_code, 401)

    def test_expired_tokens_are_rejected(self):
        access = AccessToken.for_user(self.user)
        access.set_exp(lifetime=timedelta(seconds=-1))
        self.authorize(str(access))
        self.assertEqual(self.me().status_code, 401)
        refresh = RefreshToken.for_user(self.user)
        refresh.set_exp(lifetime=timedelta(seconds=-1))
        self.assertEqual(self.post("refresh", {"refresh": str(refresh)}).status_code, 401)

    def test_deactivated_user_cannot_use_access_or_refresh_tokens(self):
        tokens = self.login()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.authorize(tokens["access"])
        self.assertEqual(self.me().status_code, 401)
        self.assertEqual(self.post("refresh", {"refresh": tokens["refresh"]}).status_code, 401)

    def test_deleted_user_cannot_refresh(self):
        tokens = self.login()
        self.user.delete()
        self.assertEqual(self.post("refresh", {"refresh": tokens["refresh"]}).status_code, 401)

    def test_pre_uuid_tokens_require_a_fresh_login(self):
        refresh = RefreshToken.for_user(self.user)
        del refresh["user_uuid"]
        refresh["user_id"] = "1"
        self.authorize(str(refresh.access_token))
        self.assertEqual(self.me().status_code, 401)
        self.assertEqual(self.post("refresh", {"refresh": str(refresh)}).status_code, 401)

    def test_repeated_auth_requests_are_throttled(self):
        for _ in range(20):
            self.assertEqual(self.post("login", {}).status_code, 400)
        self.assertEqual(self.post("login", {}).status_code, 429)

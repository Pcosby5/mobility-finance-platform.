from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import User


class UserTests(TestCase):
    def test_new_user_defaults_to_unprivileged_customer(self):
        user = User.objects.create_user(username="customer", password="demo-test-password")
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotEqual(user.password, "demo-test-password")
        self.assertTrue(user.check_password("demo-test-password"))

    def test_database_rejects_unknown_role(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(username="invalid", role="UNKNOWN")

    def test_operations_role_does_not_grant_admin_site_access(self):
        user = User.objects.create_user(username="operator", role=User.Role.OPERATIONS)
        self.client.force_login(user)
        response = self.client.get("/admin/", secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

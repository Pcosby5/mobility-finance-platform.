import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Business roles are separate from Django's staff/admin-site permissions."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        CUSTOMER = "CUSTOMER", "Customer"
        OPERATIONS = "OPERATIONS", "Operations"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CUSTOMER)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["ADMIN", "CUSTOMER", "OPERATIONS"]),
                name="users_user_valid_role",
            ),
        ]

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models


class CustomerProfile(models.Model):
    class EmploymentStatus(models.TextChoices):
        EMPLOYED = "EMPLOYED", "Employed"
        SELF_EMPLOYED = "SELF_EMPLOYED", "Self-employed"
        UNEMPLOYED = "UNEMPLOYED", "Unemployed"
        STUDENT = "STUDENT", "Student"
        RETIRED = "RETIRED", "Retired"

    class Currency(models.TextChoices):
        GHS = "GHS", "Ghanaian cedi"
        NGN = "NGN", "Nigerian naira"
        USD = "USD", "US dollar"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="customer_profile"
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(
        max_length=16,
        validators=[RegexValidator(r"^\+[1-9][0-9]{7,14}$", "Use + and 8–15 digits.")],
    )
    employment_status = models.CharField(max_length=16, choices=EmploymentStatus.choices)
    employment_duration_months = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.GHS)
    monthly_income = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    existing_debt = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))]
    )
    monthly_debt_repayment = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(monthly_income__gte=0), name="customer_income_nonnegative"
            ),
            models.CheckConstraint(
                condition=models.Q(existing_debt__gte=0), name="customer_debt_nonnegative"
            ),
            models.CheckConstraint(
                condition=models.Q(monthly_debt_repayment__gte=0),
                name="customer_repayment_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=["GHS", "NGN", "USD"]),
                name="customer_valid_currency",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    employment_status__in=[
                        "EMPLOYED",
                        "SELF_EMPLOYED",
                        "UNEMPLOYED",
                        "STUDENT",
                        "RETIRED",
                    ]
                ),
                name="customer_valid_employment",
            ),
        ]

    def __str__(self):
        return self.full_name

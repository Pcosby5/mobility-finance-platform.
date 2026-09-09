import uuid

from django.conf import settings
from django.db import models

from .policy import OPEN_STATUSES


class Loan(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        DEFAULTED = "DEFAULTED", "Defaulted"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        "customers.CustomerProfile", on_delete=models.PROTECT, related_name="loans"
    )
    vehicle = models.ForeignKey("vehicles.Vehicle", on_delete=models.PROTECT, related_name="loans")
    credit_assessment = models.ForeignKey(
        "credit.CreditAssessment", on_delete=models.PROTECT, related_name="loans"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    currency = models.CharField(max_length=3)
    principal_amount = models.DecimalField(max_digits=14, decimal_places=2)
    annual_interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    duration_months = models.PositiveSmallIntegerField()
    first_repayment_date = models.DateField()
    total_interest = models.DecimalField(max_digits=14, decimal_places=2)
    total_repayable = models.DecimalField(max_digits=14, decimal_places=2)
    monthly_repayment = models.DecimalField(max_digits=14, decimal_places=2)
    final_repayment = models.DecimalField(max_digits=14, decimal_places=2)
    outstanding_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.PENDING)
    policy_version = models.CharField(max_length=32)
    origination_snapshot = models.JSONField()
    activated_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["vehicle"],
                condition=models.Q(status__in=OPEN_STATUSES),
                name="loan_one_open_per_vehicle",
            ),
            models.CheckConstraint(
                condition=models.Q(principal_amount__gt=0), name="loan_positive_principal"
            ),
            models.CheckConstraint(
                condition=models.Q(annual_interest_rate__gte=0, annual_interest_rate__lte=100),
                name="loan_valid_rate",
            ),
            models.CheckConstraint(
                condition=models.Q(duration_months__gte=1, duration_months__lte=120),
                name="loan_valid_duration",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    total_interest__gte=0,
                    total_repayable=models.F("principal_amount") + models.F("total_interest"),
                ),
                name="loan_total_matches_components",
            ),
            models.CheckConstraint(
                condition=models.Q(monthly_repayment__gt=0, final_repayment__gt=0),
                name="loan_positive_repayments",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    outstanding_balance__gte=0, outstanding_balance__lte=models.F("total_repayable")
                ),
                name="loan_balance_range",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=["GHS", "NGN", "USD"]), name="loan_valid_currency"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=["PENDING", "CANCELLED", "COMPLETED"], outstanding_balance=0
                    )
                    | models.Q(status__in=["ACTIVE", "DEFAULTED"], outstanding_balance__gt=0)
                ),
                name="loan_status_balance_consistent",
            ),
        ]


class RepaymentInstallment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, related_name="installments")
    number = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    principal_due = models.DecimalField(max_digits=14, decimal_places=2)
    interest_due = models.DecimalField(max_digits=14, decimal_places=2)
    amount_due = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["loan", "number"], name="installment_unique_number"),
            models.CheckConstraint(
                condition=models.Q(number__gte=1), name="installment_positive_number"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    principal_due__gt=0,
                    interest_due__gte=0,
                    amount_due=models.F("principal_due") + models.F("interest_due"),
                ),
                name="installment_valid_amounts",
            ),
        ]

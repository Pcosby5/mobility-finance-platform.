"""Demo payment records.

A Payment is an immutable ledger row: initialization creates it PENDING and the
verified webhook/verify flow is the only writer of terminal statuses. Amounts and
balances are Decimal; outstanding balances are only reduced inside the same
transaction that marks a payment SUCCESS, so a crash cannot split the pair.

Idempotency has two layers: the unique reference stops duplicate payments, and
conditional updates (``filter(...).update(...)``) make terminal transitions
single-winner under concurrent webhook redelivery. WebhookEvent keeps an audit
trail of every delivery, including ones ignored as duplicates or invalid.
No real financial transactions are processed; Paystack must run in test mode.
"""

import uuid

from django.db import models


class Payment(models.Model):
    class Provider(models.TextChoices):
        PAYSTACK = "PAYSTACK", "Paystack (test mode)"
        MOCK_MOMO = "MOCK_MOMO", "Simulated mobile money"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loan = models.ForeignKey("loans.Loan", on_delete=models.PROTECT, related_name="payments")
    customer = models.ForeignKey(
        "customers.CustomerProfile", on_delete=models.PROTECT, related_name="payments"
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    reference = models.CharField(max_length=64, unique=True)
    currency = models.CharField(max_length=3)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider_transaction_id = models.CharField(max_length=100, null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    raw_event = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["loan", "-created_at"], name="payment_loan_created_idx")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="payment_positive_amount"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["PENDING", "SUCCESS", "FAILED", "CANCELLED"]),
                name="payment_valid_status",
            ),
            models.CheckConstraint(
                condition=models.Q(provider__in=["PAYSTACK", "MOCK_MOMO"]),
                name="payment_valid_provider",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=["GHS", "NGN", "USD"]),
                name="payment_valid_currency",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="SUCCESS", provider_transaction_id__isnull=False)
                    | models.Q(status__in=["PENDING", "FAILED", "CANCELLED"])
                ),
                name="payment_success_has_provider_transaction",
            ),
        ]

    def __str__(self):
        return f"{self.provider}:{self.reference} {self.status}"


class WebhookEvent(models.Model):
    """Audit trail of raw webhook deliveries, written before any processing."""

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        PROCESSED = "PROCESSED", "Processed"
        IGNORED = "IGNORED", "Ignored"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=20, choices=Payment.Provider.choices)
    event_type = models.CharField(max_length=50)
    signature = models.CharField(max_length=255, blank=True)
    payload = models.JSONField()
    delivery_reference = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RECEIVED)
    note = models.CharField(max_length=255, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at", "id"]
        indexes = [models.Index(fields=["provider", "-received_at"], name="webhook_provider_idx")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["RECEIVED", "PROCESSED", "IGNORED"]),
                name="webhookevent_valid_status",
            ),
        ]

    def __str__(self):
        return f"{self.provider} {self.event_type} {self.status}"

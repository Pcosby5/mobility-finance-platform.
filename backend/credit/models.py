import uuid

from django.conf import settings
from django.db import models


class CreditAssessment(models.Model):
    class RiskBand(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    class Decision(models.TextChoices):
        APPROVED = "APPROVED", "Demo approved"
        REVIEW = "REVIEW", "Review required"
        REJECTED = "REJECTED", "Demo rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        "customers.CustomerProfile", on_delete=models.PROTECT, related_name="credit_assessments"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    rules_version = models.CharField(max_length=32)
    rules_snapshot = models.JSONField()
    input_snapshot = models.JSONField()
    score = models.PositiveSmallIntegerField()
    risk_band = models.CharField(max_length=6, choices=RiskBand.choices)
    decision = models.CharField(max_length=8, choices=Decision.choices)
    factors = models.JSONField()
    ratios = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["customer", "-created_at"], name="credit_customer_created_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(score__gte=300, score__lte=850), name="credit_score_range"
            ),
            models.CheckConstraint(
                condition=models.Q(risk_band__in=["LOW", "MEDIUM", "HIGH"]),
                name="credit_valid_risk_band",
            ),
            models.CheckConstraint(
                condition=models.Q(decision__in=["APPROVED", "REVIEW", "REJECTED"]),
                name="credit_valid_decision",
            ),
        ]

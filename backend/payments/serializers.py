"""Serializers reject anything a client must never set: computed amounts,
statuses, references and provider results are server-generated or read-only."""

from decimal import Decimal

from loans.models import Loan
from rest_framework import serializers

from .models import Payment, WebhookEvent


class PaymentInitializeSerializer(serializers.Serializer):
    loan_id = serializers.PrimaryKeyRelatedField(
        queryset=Loan.objects.all(), pk_field=serializers.UUIDField()
    )
    provider = serializers.ChoiceField(choices=Payment.Provider.choices)
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False
    )

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: "This field cannot be set." for key in sorted(unknown)}
            )
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id",
            "loan",
            "customer",
            "provider",
            "reference",
            "currency",
            "amount",
            "status",
            "provider_transaction_id",
            "failure_reason",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class MockMomoCallbackSerializer(serializers.Serializer):
    """Development-only body for triggering a simulated MoMo callback."""

    reference = serializers.CharField(max_length=64)
    outcome = serializers.ChoiceField(choices=["success", "failed"])


class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEvent
        fields = (
            "id",
            "provider",
            "event_type",
            "delivery_reference",
            "status",
            "note",
            "received_at",
            "processed_at",
        )
        read_only_fields = fields

from decimal import Decimal

from credit.models import CreditAssessment
from customers.models import CustomerProfile
from rest_framework import serializers
from vehicles.models import Vehicle

from .models import Loan, RepaymentInstallment
from .policy import MAX_ANNUAL_RATE, MAX_DURATION_MONTHS, MAX_PRINCIPAL


class LoanCreateSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(
        queryset=CustomerProfile.objects.all(), pk_field=serializers.UUIDField()
    )
    vehicle = serializers.PrimaryKeyRelatedField(
        queryset=Vehicle.objects.all(), pk_field=serializers.UUIDField()
    )
    credit_assessment = serializers.PrimaryKeyRelatedField(
        queryset=CreditAssessment.objects.all(), pk_field=serializers.UUIDField()
    )
    principal_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01"), max_value=MAX_PRINCIPAL
    )
    annual_interest_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=MAX_ANNUAL_RATE
    )
    duration_months = serializers.IntegerField(min_value=1, max_value=MAX_DURATION_MONTHS)
    first_repayment_date = serializers.DateField()

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: "This field cannot be set." for key in sorted(unknown)}
            )
        return attrs


class LoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = (
            "id",
            "customer",
            "vehicle",
            "credit_assessment",
            "created_by",
            "currency",
            "principal_amount",
            "annual_interest_rate",
            "duration_months",
            "first_repayment_date",
            "total_interest",
            "total_repayable",
            "monthly_repayment",
            "final_repayment",
            "outstanding_balance",
            "status",
            "policy_version",
            "origination_snapshot",
            "activated_at",
            "cancelled_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class InstallmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepaymentInstallment
        fields = ("id", "loan", "number", "due_date", "principal_due", "interest_due", "amount_due")
        read_only_fields = fields


class LoanActionSerializer(serializers.Serializer):
    def validate(self, attrs):
        if self.initial_data:
            raise serializers.ValidationError("Send an empty object for this action.")
        return attrs

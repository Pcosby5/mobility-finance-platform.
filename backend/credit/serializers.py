from rest_framework import serializers

from .models import CreditAssessment


class AssessmentRequestSerializer(serializers.Serializer):
    def validate(self, attrs):
        if self.initial_data:
            raise serializers.ValidationError(
                "Send an empty object; inputs come from the saved profile."
            )
        return attrs


class CreditAssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditAssessment
        fields = (
            "id",
            "customer",
            "created_by",
            "rules_version",
            "rules_snapshot",
            "input_snapshot",
            "score",
            "risk_band",
            "decision",
            "factors",
            "ratios",
            "created_at",
        )
        read_only_fields = fields

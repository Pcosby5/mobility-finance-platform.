from rest_framework import serializers

from .alerts import Alert
from .models import TelemetryRecord


class TelemetryRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelemetryRecord
        fields = (
            "id",
            "vehicle",
            "device_id",
            "recorded_at",
            "latitude",
            "longitude",
            "speed_kph",
            "heading_degrees",
            "battery_percent",
            "ignition",
            "created_at",
        )
        read_only_fields = fields


class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = (
            "id",
            "vehicle",
            "type",
            "severity",
            "message",
            "resolved_at",
            "resolved_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AlertResolveSerializer(serializers.Serializer):
    """Empty body by convention; rejects anything a client tries to set."""

    def validate(self, attrs):
        if self.initial_data:
            raise serializers.ValidationError("Send an empty object for this action.")
        return attrs

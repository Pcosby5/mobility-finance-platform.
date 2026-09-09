from rest_framework import serializers

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

from customers.models import CustomerProfile
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from .models import Device, Vehicle
from .policy import GEOFENCE_MAX_RADIUS_M, GEOFENCE_MIN_RADIUS_M


class InventorySerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        writable = {name for name, field in self.fields.items() if not field.read_only}
        rejected = set(self.initial_data) - writable
        if rejected:
            raise serializers.ValidationError(
                {name: "This field cannot be set." for name in sorted(rejected)}
            )
        return attrs

    def save(self, **kwargs):
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except IntegrityError as exc:
            if getattr(exc.__cause__, "sqlstate", None) == "23505":
                raise serializers.ValidationError(
                    "An identifier or vehicle assignment is already in use."
                ) from exc
            raise


class DeviceSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ("id", "device_id", "enabled")
        read_only_fields = fields


class VehicleSerializer(InventorySerializer):
    customer = serializers.PrimaryKeyRelatedField(
        queryset=CustomerProfile.objects.filter(user__is_active=True, user__role="CUSTOMER"),
        required=False,
        allow_null=True,
        pk_field=serializers.UUIDField(),
    )
    device = DeviceSummarySerializer(read_only=True, allow_null=True)

    class Meta:
        model = Vehicle
        fields = (
            "id",
            "registration_number",
            "vin",
            "make",
            "model_name",
            "year",
            "customer",
            "status",
            "connectivity_status",
            "movement_status",
            "last_latitude",
            "last_longitude",
            "last_telemetry_at",
            "geofence_latitude",
            "geofence_longitude",
            "geofence_radius_m",
            "device",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "connectivity_status",
            "movement_status",
            "last_latitude",
            "last_longitude",
            "last_telemetry_at",
            "created_at",
            "updated_at",
        )

    def to_internal_value(self, data):
        # Normalize before DRF's uniqueness checks so differently cased identifiers collide.
        if isinstance(data, dict) or hasattr(data, "getlist"):
            data = data.copy()
            for field in ("registration_number", "vin"):
                if isinstance(data.get(field), str):
                    data[field] = data[field].strip().upper()
        return super().to_internal_value(data)

    def validate_year(self, value):
        if value > timezone.now().year + 1:
            raise serializers.ValidationError("Year cannot be later than next year.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # The geofence is set, changed or cleared as one unit; vehicles are
        # created without one by default. The database enforces the same rule.
        geofence_keys = ("geofence_latitude", "geofence_longitude", "geofence_radius_m")
        provided = [key for key in geofence_keys if key in attrs]
        if provided and len(provided) != 3:
            raise serializers.ValidationError(
                "Provide geofence_latitude, geofence_longitude and geofence_radius_m together "
                "(or none of them to leave the geofence unset)."
            )
        radius = attrs.get("geofence_radius_m")
        if (
            provided
            and radius is not None
            and not (GEOFENCE_MIN_RADIUS_M <= radius <= GEOFENCE_MAX_RADIUS_M)
        ):
            raise serializers.ValidationError(
                {
                    "geofence_radius_m": f"Radius must be between {GEOFENCE_MIN_RADIUS_M} "
                    f"and {GEOFENCE_MAX_RADIUS_M} meters."
                }
            )
        return attrs

    def update(self, instance, validated_data):
        from loans.policy import OPEN_STATUSES

        # InventorySerializer.save holds the transaction; share the vehicle lock with loan creation.
        instance = Vehicle.objects.select_for_update().get(pk=instance.pk)
        identity_changed = (
            "customer" in validated_data
            and getattr(validated_data["customer"], "pk", None) != instance.customer_id
        ) or ("vin" in validated_data and validated_data["vin"] != instance.vin)
        retiring = validated_data.get("status") == Vehicle.Status.RETIRED
        if (identity_changed or retiring) and instance.loans.filter(
            status__in=OPEN_STATUSES
        ).exists():
            raise serializers.ValidationError(
                "An open loan prevents reassignment, VIN changes or vehicle retirement."
            )
        return super().update(instance, validated_data)


class DeviceSerializer(InventorySerializer):
    class Meta:
        model = Device
        fields = ("id", "device_id", "vehicle", "enabled", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance and "device_id" in attrs:
            raise serializers.ValidationError({"device_id": "Device identity cannot be changed."})
        return attrs

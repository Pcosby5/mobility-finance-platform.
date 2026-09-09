import uuid

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Upper

from .policy import GEOFENCE_MAX_RADIUS_M, GEOFENCE_MIN_RADIUS_M


class Vehicle(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        MAINTENANCE = "MAINTENANCE", "Maintenance"
        RETIRED = "RETIRED", "Retired"

    class Connectivity(models.TextChoices):
        UNKNOWN = "UNKNOWN", "Unknown"
        ONLINE = "ONLINE", "Online"
        OFFLINE = "OFFLINE", "Offline"

    class Movement(models.TextChoices):
        UNKNOWN = "UNKNOWN", "Unknown"
        MOVING = "MOVING", "Moving"
        PARKED = "PARKED", "Parked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration_number = models.CharField(max_length=32, unique=True)
    vin = models.CharField(
        max_length=17,
        unique=True,
        validators=[
            RegexValidator(r"^[A-HJ-NPR-Z0-9]{17}$", "Use a 17-character VIN without I, O or Q.")
        ],
    )
    make = models.CharField(max_length=80)
    model_name = models.CharField(max_length=80)
    year = models.PositiveSmallIntegerField(validators=[MinValueValidator(1900)])
    customer = models.ForeignKey(
        "customers.CustomerProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="vehicles",
    )
    status = models.CharField(max_length=11, choices=Status.choices, default=Status.ACTIVE)
    connectivity_status = models.CharField(
        max_length=7, choices=Connectivity.choices, default=Connectivity.UNKNOWN
    )
    movement_status = models.CharField(
        max_length=7, choices=Movement.choices, default=Movement.UNKNOWN
    )
    last_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_telemetry_at = models.DateTimeField(null=True, blank=True)
    # Simple radius-based geofence (demo): a center plus radius in meters.
    # All three fields are set together or not at all.
    geofence_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_radius_m = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(year__gte=1900), name="vehicle_year_minimum"),
            models.CheckConstraint(
                condition=models.Q(vin=Upper("vin")), name="vehicle_vin_uppercase"
            ),
            models.CheckConstraint(
                condition=models.Q(registration_number=Upper("registration_number")),
                name="vehicle_registration_uppercase",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "MAINTENANCE", "RETIRED"]),
                name="vehicle_valid_status",
            ),
            models.CheckConstraint(
                condition=models.Q(connectivity_status__in=["UNKNOWN", "ONLINE", "OFFLINE"]),
                name="vehicle_valid_connectivity",
            ),
            models.CheckConstraint(
                condition=models.Q(movement_status__in=["UNKNOWN", "MOVING", "PARKED"]),
                name="vehicle_valid_movement",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(last_latitude__isnull=True, last_longitude__isnull=True)
                    | models.Q(
                        last_latitude__isnull=False,
                        last_longitude__isnull=False,
                        last_latitude__gte=-90,
                        last_latitude__lte=90,
                        last_longitude__gte=-180,
                        last_longitude__lte=180,
                    )
                ),
                name="vehicle_valid_coordinates",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        geofence_latitude__isnull=True,
                        geofence_longitude__isnull=True,
                        geofence_radius_m__isnull=True,
                    )
                    | models.Q(
                        geofence_latitude__isnull=False,
                        geofence_longitude__isnull=False,
                        geofence_radius_m__isnull=False,
                    )
                ),
                name="vehicle_geofence_all_or_nothing",
            ),
            models.CheckConstraint(
                condition=models.Q(geofence_radius_m__isnull=True)
                | models.Q(
                    geofence_radius_m__gte=GEOFENCE_MIN_RADIUS_M,
                    geofence_radius_m__lte=GEOFENCE_MAX_RADIUS_M,
                ),
                name="vehicle_geofence_radius_range",
            ),
        ]

    def __str__(self):
        return self.registration_number


class Device(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_id = models.CharField(
        max_length=64,
        unique=True,
        validators=[
            RegexValidator(r"^[A-Za-z0-9_-]+$", "Use letters, digits, underscores or hyphens.")
        ],
    )
    vehicle = models.OneToOneField(
        Vehicle, on_delete=models.PROTECT, related_name="device", null=True, blank=True
    )
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self):
        return self.device_id

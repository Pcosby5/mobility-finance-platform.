"""Telemetry records ingested from the MQTT pipeline.

A record is one GPS/telemetry message from one device at one time. The unique
(device_id, recorded_at) constraint makes ingestion idempotent: QoS 1 brokers
redeliver, and the consumer may also be restarted mid-stream, so the database —
not the transport — guarantees a duplicate message is stored once.

The device_id is the vehicle's immutable MQTT routing identity registered on
the Device model; vehicle resolution happens in the ingest service, never in
the model. Vehicle denormalized state (last position, connectivity) lives on
the Vehicle row and is updated by the same ingest transaction.
"""

import uuid

from django.db import models

# The Alert model lives in alerts.py beside its raise/clear rules; importing it
# here registers it with the app registry so migrations and relations resolve.
from .alerts import Alert  # noqa: F401


class TelemetryRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicle = models.ForeignKey(
        "vehicles.Vehicle", on_delete=models.CASCADE, related_name="telemetry_records"
    )
    device_id = models.CharField(max_length=64)
    recorded_at = models.DateTimeField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    speed_kph = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    heading_degrees = models.PositiveSmallIntegerField(null=True, blank=True)
    battery_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    ignition = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "id"]
        indexes = [
            models.Index(fields=["vehicle", "-recorded_at"], name="telemetry_vehicle_recorded_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["device_id", "recorded_at"], name="telemetry_unique_device_time"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    latitude__gte=-90, latitude__lte=90, longitude__gte=-180, longitude__lte=180
                ),
                name="telemetry_valid_coordinates",
            ),
            models.CheckConstraint(
                condition=models.Q(speed_kph__gte=0), name="telemetry_nonnegative_speed"
            ),
            models.CheckConstraint(
                condition=models.Q(heading_degrees__gte=0, heading_degrees__lte=360),
                name="telemetry_valid_heading",
            ),
            models.CheckConstraint(
                condition=models.Q(battery_percent__gte=0, battery_percent__lte=100),
                name="telemetry_valid_battery",
            ),
        ]

    def __str__(self):
        return f"{self.device_id} @ {self.recorded_at:%Y-%m-%d %H:%M:%S}"

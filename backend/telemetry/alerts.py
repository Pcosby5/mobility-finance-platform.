"""Operational alerts raised by the telemetry pipeline.

Alert rules (demo):

* GEOFENCE_EXIT — vehicle's last known position is outside its geofence.
* SPEEDING — a telemetry message exceeds the speed threshold.
* LOW_BATTERY — device battery drops to or below the threshold.
* OFFLINE — no telemetry for longer than the offline window (raised by the
  ``check_offline_vehicles`` command, which can be scheduled via cron or a
  container sidecar; production would use Celery beat).

One open alert per (vehicle, type), enforced by a partial unique constraint in
the database — the hard guarantee that concurrent ingest workers cannot stack
duplicates. ``raise_or_refresh`` creates-or-refreshes within that constraint;
resolving is explicit via the API (operations/admin, which records the actor)
or automatic when the condition clears during ingestion — auto-resolve has no
actor, which is why actor presence is an API-level rule, not a DB constraint.
"""

import uuid

from django.db import IntegrityError, models, transaction
from django.utils import timezone


class Alert(models.Model):
    class Type(models.TextChoices):
        GEOFENCE_EXIT = "GEOFENCE_EXIT", "Vehicle left its geofence"
        SPEEDING = "SPEEDING", "Speed above threshold"
        LOW_BATTERY = "LOW_BATTERY", "Device battery low"
        OFFLINE = "OFFLINE", "Vehicle offline"

    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicle = models.ForeignKey("vehicles.Vehicle", on_delete=models.CASCADE, related_name="alerts")
    type = models.CharField(max_length=16, choices=Type.choices)
    severity = models.CharField(max_length=8, choices=Severity.choices)
    message = models.CharField(max_length=255)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_alerts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["vehicle", "-created_at"], name="alert_vehicle_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["vehicle", "type"],
                condition=models.Q(resolved_at__isnull=True),
                name="alert_one_open_per_vehicle_type",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    type__in=["GEOFENCE_EXIT", "SPEEDING", "LOW_BATTERY", "OFFLINE"]
                ),
                name="alert_valid_type",
            ),
            models.CheckConstraint(
                condition=models.Q(severity__in=["LOW", "MEDIUM", "HIGH"]),
                name="alert_valid_severity",
            ),
        ]

    def __str__(self):
        return f"{self.type} {self.severity} {self.vehicle_id}"

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None

    @classmethod
    def raise_or_refresh(cls, *, vehicle, alert_type, severity, message):
        """Create or refresh the one open alert of this type for the vehicle.

        Returns (alert, created). A uniqueness race falls back to a refresh of
        the winning row, so callers never need to handle IntegrityError.
        """
        with transaction.atomic():
            existing = cls.objects.filter(
                vehicle=vehicle, type=alert_type, resolved_at__isnull=True
            ).first()
            if existing is not None:
                cls.objects.filter(pk=existing.pk).update(
                    severity=severity, message=message[:255], updated_at=timezone.now()
                )
                existing.refresh_from_db()
                return existing, False
            try:
                alert = cls.objects.create(
                    vehicle=vehicle, type=alert_type, severity=severity, message=message
                )
                return alert, True
            except IntegrityError:
                # Another worker opened this alert first; refresh theirs.
                existing = cls.objects.get(
                    vehicle=vehicle, type=alert_type, resolved_at__isnull=True
                )
                cls.objects.filter(pk=existing.pk).update(
                    severity=severity, message=message[:255], updated_at=timezone.now()
                )
                existing.refresh_from_db()
                return existing, False

    @classmethod
    def clear(cls, *, vehicle, alert_type) -> bool:
        """Auto-resolve the open alert of this type, if any. Returns True if cleared."""
        return bool(
            cls.objects.filter(vehicle=vehicle, type=alert_type, resolved_at__isnull=True).update(
                resolved_at=timezone.now()
            )
        )

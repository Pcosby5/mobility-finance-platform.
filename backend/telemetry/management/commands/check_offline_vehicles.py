"""Raise OFFLINE alerts for vehicles silent longer than the policy window.

Runs as its own process (cron, container sidecar, or later Celery beat):
``python manage.py check_offline_vehicles``. Only vehicles with an assigned,
enabled device and at least one telemetry record are evaluated — a vehicle that
has never reported is "not yet tracking", not "offline", which keeps the demo
alerts meaningful. Messages are refreshed on every run so timestamps stay
current while the condition holds.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from vehicles.models import Vehicle

from telemetry.alerts import Alert
from telemetry.policy import OFFLINE_AFTER_MINUTES


class Command(BaseCommand):
    help = "Raise OFFLINE alerts for vehicles with stale telemetry."

    def handle(self, *args, **options):
        now = timezone.now()
        window_start = now - timedelta(minutes=OFFLINE_AFTER_MINUTES)
        stale = (
            Vehicle.objects.filter(
                connectivity_status__in=[
                    Vehicle.Connectivity.UNKNOWN,
                    Vehicle.Connectivity.ONLINE,
                ],
                last_telemetry_at__lt=window_start,
            )
            .exclude(device__isnull=True)
            .exclude(device__enabled=False)
            .select_related("device")
        )
        raised = refreshed = 0
        for vehicle in stale:
            minutes = int((now - vehicle.last_telemetry_at).total_seconds() // 60)
            message = (
                f"No telemetry from {vehicle.registration_number} for {minutes} minutes "
                f"(device {vehicle.device.device_id})."
            )
            _, created = Alert.raise_or_refresh(
                vehicle=vehicle,
                alert_type=Alert.Type.OFFLINE,
                severity=Alert.Severity.MEDIUM,
                message=message,
            )
            raised += created
            refreshed += not created
            if vehicle.connectivity_status == Vehicle.Connectivity.ONLINE:
                Vehicle.objects.filter(pk=vehicle.pk).update(
                    connectivity_status=Vehicle.Connectivity.OFFLINE
                )
                vehicle.connectivity_status = Vehicle.Connectivity.OFFLINE
        self.stdout.write(
            f"Offline check complete: {raised} raised, {refreshed} refreshed, "
            f"{stale.count()} stale vehicles."
        )
        return "Done."

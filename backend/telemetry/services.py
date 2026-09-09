"""Ingest one telemetry message: parse → resolve → persist → update vehicle.

This service is transport-agnostic. The MQTT consumer calls it for every
message, but a REST ingestion endpoint or an AWS IoT Core rule target could
call the same function later without changes.

Idempotency lives in the database: TelemetryRecord has a unique
(device_id, recorded_at) constraint, so a broker redelivery (QoS 1) or a
consumer restart mid-stream is stored once. The vehicle row is locked while
its denormalized position is updated, and the update is skipped entirely when
the record already existed (the winning delivery already applied it).
"""

import json
import logging
from datetime import UTC, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from vehicles.models import Device, Vehicle

from . import geo
from .alerts import Alert
from .models import TelemetryRecord
from .policy import LOW_BATTERY_PERCENT, SPEEDING_THRESHOLD_KPH

logger = logging.getLogger(__name__)

# Movement threshold in km/h between PARKED and MOVING.
MOVING_SPEED_KPH = Decimal("1.0")
MAX_CLOCK_SKEW = timedelta(minutes=5)

REQUIRED_KEYS = ("device_id", "latitude", "longitude", "recorded_at")


def _to_decimal(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} is not a valid number.") from exc


def parse_payload(payload) -> dict:
    """Validate and normalize one telemetry JSON object. Raises ValueError.

    device_id is the routing identity and must match a registered Device. The
    optional vehicle_id field in the payload is informational only and is never
    trusted for resolution, so a misconfigured device cannot write to another
    vehicle's history.
    """
    if not isinstance(payload, dict):
        raise ValueError("Telemetry payload must be a JSON object.")
    missing = [key for key in REQUIRED_KEYS if payload.get(key) in (None, "")]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    device_id = str(payload["device_id"])
    latitude = _to_decimal(payload["latitude"], "latitude")
    longitude = _to_decimal(payload["longitude"], "longitude")
    if not (-90 <= latitude <= 90):
        raise ValueError("latitude must be between -90 and 90.")
    if not (-180 <= longitude <= 180):
        raise ValueError("longitude must be between -180 and 180.")
    recorded_at = parse_datetime(str(payload["recorded_at"]))
    if recorded_at is None:
        raise ValueError("recorded_at must be an ISO-8601 timestamp.")
    if timezone.is_naive(recorded_at):
        recorded_at = timezone.make_aware(recorded_at, UTC)
    if recorded_at > timezone.now() + MAX_CLOCK_SKEW:
        raise ValueError("recorded_at is too far in the future.")
    speed = payload.get("speed")
    speed_kph = _to_decimal(speed, "speed") if speed is not None else None
    if speed_kph is not None and speed_kph < 0:
        raise ValueError("speed must be nonnegative.")
    heading = payload.get("heading")
    heading_degrees = int(heading) if heading is not None else None
    if heading_degrees is not None and not 0 <= heading_degrees <= 360:
        raise ValueError("heading must be between 0 and 360.")
    battery = payload.get("battery")
    battery_percent = int(battery) if battery is not None else None
    if battery_percent is not None and not 0 <= battery_percent <= 100:
        raise ValueError("battery must be between 0 and 100.")
    ignition = payload.get("ignition")
    if ignition is not None:
        ignition = bool(ignition)
    return {
        "device_id": device_id,
        "latitude": latitude,
        "longitude": longitude,
        "recorded_at": recorded_at,
        "speed_kph": speed_kph,
        "heading_degrees": heading_degrees,
        "battery_percent": battery_percent,
        "ignition": ignition,
    }


def resolve_vehicle(device_id: str) -> Vehicle:
    """Resolve the registered device to its vehicle; raises ValueError."""
    try:
        device = Device.objects.select_related("vehicle").get(device_id=device_id)
    except Device.DoesNotExist:
        raise ValueError(f"Unknown device_id: {device_id}") from None
    if not device.enabled:
        raise ValueError(f"Device is disabled: {device_id}")
    if device.vehicle_id is None:
        raise ValueError(f"Device is not assigned to a vehicle: {device_id}")
    return device.vehicle


@transaction.atomic
def ingest_telemetry(payload) -> tuple[TelemetryRecord, bool]:
    """Persist one message and update vehicle state. Returns (record, created).

    Duplicate payloads return the existing record with created=False and leave
    vehicle state untouched, which keeps redeliveries harmless.
    """
    fields = parse_payload(payload)
    # Lock the vehicle row so concurrent messages cannot interleave the
    # denormalized last-position update.
    vehicle = resolve_vehicle(fields["device_id"])
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
    record, created = TelemetryRecord.objects.get_or_create(
        device_id=fields["device_id"],
        recorded_at=fields["recorded_at"],
        defaults={
            "vehicle": vehicle,
            "latitude": fields["latitude"],
            "longitude": fields["longitude"],
            "speed_kph": fields["speed_kph"],
            "heading_degrees": fields["heading_degrees"],
            "battery_percent": fields["battery_percent"],
            "ignition": fields["ignition"],
        },
    )
    if not created:
        return record, False
    vehicle.last_latitude = fields["latitude"]
    vehicle.last_longitude = fields["longitude"]
    vehicle.last_telemetry_at = fields["recorded_at"]
    vehicle.connectivity_status = Vehicle.Connectivity.ONLINE
    if fields["speed_kph"] is not None:
        vehicle.movement_status = (
            Vehicle.Movement.MOVING
            if fields["speed_kph"] >= MOVING_SPEED_KPH
            else Vehicle.Movement.PARKED
        )
    vehicle.save(
        update_fields=[
            "last_latitude",
            "last_longitude",
            "last_telemetry_at",
            "connectivity_status",
            "movement_status",
            "updated_at",
        ]
    )
    _evaluate_alerts(vehicle, fields)
    return record, True


def _evaluate_alerts(vehicle, fields):
    """Raise or clear condition alerts from one telemetry message.

    Runs inside the ingest transaction, so alerts and telemetry commit or roll
    back together. GEOFENCE_EXIT is only evaluated for vehicles with a geofence;
    a returning vehicle auto-clears its open alert, and SPEEDING/LOW_BATTERY
    clear themselves once the condition no longer holds. A fresh message also
    clears OFFLINE (the vehicle is talking again).
    """
    Alert.clear(vehicle=vehicle, alert_type=Alert.Type.OFFLINE)
    if vehicle.geofence_latitude is not None:
        inside = geo.is_within_radius_m(
            float(fields["latitude"]),
            float(fields["longitude"]),
            float(vehicle.geofence_latitude),
            float(vehicle.geofence_longitude),
            vehicle.geofence_radius_m,
        )
        if inside:
            Alert.clear(vehicle=vehicle, alert_type=Alert.Type.GEOFENCE_EXIT)
        else:
            Alert.raise_or_refresh(
                vehicle=vehicle,
                alert_type=Alert.Type.GEOFENCE_EXIT,
                severity=Alert.Severity.HIGH,
                message=(
                    f"Vehicle {vehicle.registration_number} is outside its "
                    f"geofence of {vehicle.geofence_radius_m} m radius."
                ),
            )
    speed = fields["speed_kph"]
    if speed is not None and speed > SPEEDING_THRESHOLD_KPH:
        Alert.raise_or_refresh(
            vehicle=vehicle,
            alert_type=Alert.Type.SPEEDING,
            severity=Alert.Severity.HIGH,
            message=f"Vehicle {vehicle.registration_number} reported {speed} km/h.",
        )
    else:
        Alert.clear(vehicle=vehicle, alert_type=Alert.Type.SPEEDING)
    battery = fields["battery_percent"]
    if battery is not None and battery <= LOW_BATTERY_PERCENT:
        Alert.raise_or_refresh(
            vehicle=vehicle,
            alert_type=Alert.Type.LOW_BATTERY,
            severity=Alert.Severity.MEDIUM,
            message=f"Device battery of {vehicle.registration_number} is at {battery}%.",
        )
    elif battery is not None:
        Alert.clear(vehicle=vehicle, alert_type=Alert.Type.LOW_BATTERY)


def process_message(topic: str, body: bytes) -> dict:
    """Handle one raw broker delivery. Never raises for malformed content.

    Returns {"status": "stored"|"duplicate"|"rejected", ...} so the broker
    adapter only has to log. Malformed payloads are rejected here; a database
    failure still raises and is handled by the adapter's error boundary.
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return {"status": "rejected", "reason": f"invalid json: {exc}"}
    try:
        record, created = ingest_telemetry(payload)
    except ValueError as exc:
        return {"status": "rejected", "reason": str(exc)}
    # The topic advertises a vehicle id (vehicles/{vehicle_id}/telemetry). It is
    # informational only: resolution always follows the device registration, but
    # a mismatch is worth surfacing because it means a misconfigured device.
    segments = topic.split("/") if topic else []
    if len(segments) >= 2 and segments[1] and segments[1] != str(record.vehicle_id):
        logger.warning(
            "Topic vehicle %s does not match device %s (resolved to %s)",
            segments[1],
            record.device_id,
            record.vehicle_id,
        )
    return {
        "status": "stored" if created else "duplicate",
        "record_id": str(record.pk),
        "vehicle_id": str(record.vehicle_id),
    }

"""Telemetry pipeline tests: parsing, idempotent ingestion and the HTTP API."""

import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from customers.models import CustomerProfile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User
from vehicles.models import Device, Vehicle

from .models import TelemetryRecord
from .services import ingest_telemetry, parse_payload, process_message


class TelemetryFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="telemetry_customer")
        cls.other = User.objects.create_user(username="telemetry_other")
        cls.operator = User.objects.create_user(
            username="telemetry_operator", role=User.Role.OPERATIONS
        )
        cls.profile = CustomerProfile.objects.create(
            user=cls.customer,
            full_name="Telemetry Customer",
            phone="+233201234567",
            monthly_income="6500.00",
            employment_status="EMPLOYED",
        )
        cls.vehicle = Vehicle.objects.create(
            registration_number="TEL-001",
            vin="1HGCM82633A004352",
            make="Toyota",
            model_name="Corolla",
            year=2020,
            customer=cls.profile,
        )
        cls.device = Device.objects.create(device_id="GPS-001", vehicle=cls.vehicle)
        cls.other_vehicle = Vehicle.objects.create(
            registration_number="TEL-002",
            vin="1HGCM82633A004353",
            make="Toyota",
            model_name="Corolla",
            year=2020,
        )


class PayloadParsingTests(TelemetryFixtureMixin, APITestCase):
    def base_payload(self, **overrides):
        payload = {
            "device_id": "GPS-001",
            "vehicle_id": str(self.vehicle.pk),
            "latitude": 5.6037,
            "longitude": -0.1870,
            "speed": 43.5,
            "heading": 180,
            "battery": 84,
            "ignition": True,
            "timestamp": "2026-09-09T10:00:00+00:00",
        }
        # The spec's payload uses "timestamp"; ingestion expects "recorded_at".
        payload["recorded_at"] = payload.pop("timestamp")
        payload.update(overrides)
        return payload

    def test_parse_normalizes_fields(self):
        fields = parse_payload(self.base_payload())
        self.assertEqual(fields["device_id"], "GPS-001")
        self.assertEqual(fields["latitude"], Decimal("5.6037"))
        self.assertEqual(fields["speed_kph"], Decimal("43.5"))
        self.assertEqual(fields["heading_degrees"], 180)
        self.assertEqual(fields["battery_percent"], 84)
        self.assertIs(fields["ignition"], True)
        self.assertTrue(timezone.is_aware(fields["recorded_at"]))

    def test_parse_accepts_spec_timestamp_alias(self):
        """The published payload spec uses "timestamp"; ingestion expects
        "recorded_at". The GPS simulator sends "timestamp", so the alias must
        parse — otherwise every simulated message is rejected."""
        fields = parse_payload(self.base_payload(timestamp="2026-09-09T10:00:00+00:00"))
        self.assertTrue(timezone.is_aware(fields["recorded_at"]))
        self.assertEqual(fields["recorded_at"].isoformat(), "2026-09-09T10:00:00+00:00")

    def test_recorded_at_wins_over_timestamp(self):
        fields = parse_payload(
            self.base_payload(
                timestamp="2026-09-09T10:00:00+00:00",
                recorded_at="2026-09-09T11:00:00+00:00",
            )
        )
        self.assertEqual(fields["recorded_at"].isoformat(), "2026-09-09T11:00:00+00:00")

    def test_parse_rejects_missing_or_invalid_values(self):
        with self.assertRaises(ValueError):
            parse_payload({"device_id": "GPS-001"})
        with self.assertRaises(ValueError):
            parse_payload(self.base_payload(latitude=95.0))
        with self.assertRaises(ValueError):
            parse_payload(self.base_payload(longitude=-200.0))
        with self.assertRaises(ValueError):
            parse_payload(self.base_payload(speed=-1))
        with self.assertRaises(ValueError):
            parse_payload(self.base_payload(heading=400))
        with self.assertRaises(ValueError):
            parse_payload(self.base_payload(battery=101))
        with self.assertRaises(ValueError):
            parse_payload(self.base_payload(recorded_at="not-a-date"))
        with self.assertRaises(ValueError):
            parse_payload(self.base_payload(recorded_at="2099-01-01T00:00:00+00:00"))
        with self.assertRaises(ValueError):
            parse_payload("not an object")

    def test_parse_accepts_naive_timestamp_as_utc(self):
        fields = parse_payload(self.base_payload(recorded_at="2026-09-09T10:00:00"))
        self.assertTrue(timezone.is_aware(fields["recorded_at"]))


class IngestionTests(TelemetryFixtureMixin, APITestCase):
    def payload(self, **overrides):
        stamp = (timezone.now() - timedelta(seconds=5)).isoformat()
        base = {
            "device_id": "GPS-001",
            "latitude": 5.6037,
            "longitude": -0.1870,
            "speed": 43.5,
            "heading": 180,
            "battery": 84,
            "ignition": True,
            "recorded_at": stamp,
        }
        base.update(overrides)
        return base

    def test_ingest_persists_record_and_updates_vehicle(self):
        record, created = ingest_telemetry(self.payload())
        self.assertTrue(created)
        self.assertEqual(record.device_id, "GPS-001")
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.last_latitude, Decimal("5.603700"))
        self.assertEqual(self.vehicle.last_longitude, Decimal("-0.187000"))
        self.assertEqual(self.vehicle.connectivity_status, Vehicle.Connectivity.ONLINE)
        self.assertEqual(self.vehicle.movement_status, Vehicle.Movement.MOVING)
        self.assertEqual(record.vehicle_id, self.vehicle.pk)

    def test_ingest_marks_slow_vehicle_parked(self):
        record, created = ingest_telemetry(self.payload(speed=0.5))
        self.assertTrue(created)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.movement_status, Vehicle.Movement.PARKED)

    def test_duplicate_delivery_is_idempotent(self):
        payload = self.payload()
        first, created = ingest_telemetry(payload)
        self.assertTrue(created)
        second, created_again = ingest_telemetry(payload)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(TelemetryRecord.objects.count(), 1)
        # Vehicle state is untouched by the duplicate.
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.last_latitude, Decimal("5.603700"))

    def test_unknown_or_disabled_device_is_rejected(self):
        with self.assertRaises(ValueError):
            ingest_telemetry(self.payload(device_id="GPS-404"))
        Device.objects.filter(pk=self.device.pk).update(enabled=False)
        with self.assertRaises(ValueError):
            ingest_telemetry(self.payload())
        Device.objects.filter(pk=self.device.pk).update(enabled=True)

    def test_payload_vehicle_id_is_not_trusted(self):
        # A misconfigured device cannot write into another vehicle's history.
        with self.assertRaises(ValueError):
            ingest_telemetry(self.payload(device_id="GPS-404", vehicle_id=str(self.vehicle.pk)))

    def test_unassigned_device_is_rejected(self):
        Device.objects.create(device_id="GPS-FLOAT")
        with self.assertRaises(ValueError):
            ingest_telemetry(self.payload(device_id="GPS-FLOAT"))


class ProcessMessageTests(TelemetryFixtureMixin, APITestCase):
    def test_stores_valid_message(self):
        body = json.dumps(
            {
                "device_id": "GPS-001",
                "latitude": 5.6037,
                "longitude": -0.1870,
                "speed": 10,
                "recorded_at": (timezone.now() - timedelta(seconds=5)).isoformat(),
            }
        ).encode()
        result = process_message("vehicles/1/telemetry", body)
        self.assertEqual(result["status"], "stored")
        self.assertEqual(TelemetryRecord.objects.count(), 1)

    def test_rejects_malformed_without_raising(self):
        result = process_message("vehicles/1/telemetry", b"{not json")
        self.assertEqual(result["status"], "rejected")
        result = process_message(
            "vehicles/1/telemetry", json.dumps({"device_id": "GPS-404"}).encode()
        )
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(TelemetryRecord.objects.count(), 0)

    def test_topic_vehicle_mismatch_is_flagged(self):
        body = json.dumps(
            {
                "device_id": "GPS-001",
                "latitude": 5.6037,
                "longitude": -0.1870,
                "recorded_at": (timezone.now() - timedelta(seconds=5)).isoformat(),
            }
        ).encode()
        with mock.patch("telemetry.services.logger") as mock_logger:
            result = process_message(f"vehicles/{self.other_vehicle.pk}/telemetry", body)
        self.assertEqual(result["status"], "stored")
        mock_logger.warning.assert_called_once()

    def test_database_failure_propagates(self):
        body = json.dumps(
            {
                "device_id": "GPS-001",
                "latitude": 5.6037,
                "longitude": -0.1870,
                "recorded_at": (timezone.now() - timedelta(seconds=5)).isoformat(),
            }
        ).encode()
        with mock.patch("telemetry.services.ingest_telemetry", side_effect=RuntimeError("db down")):
            with self.assertRaises(RuntimeError):
                process_message("vehicles/1/telemetry", body)


class TelemetryAPITests(TelemetryFixtureMixin, APITestCase):
    def authenticate(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
        )

    def seed_history(self):
        stamps = [timezone.now() - timedelta(minutes=offset) for offset in (30, 20, 10)]
        for index, stamp in enumerate(stamps):
            TelemetryRecord.objects.create(
                vehicle=self.vehicle,
                device_id="GPS-001",
                recorded_at=stamp,
                latitude=Decimal("5.6037") + Decimal("0.001") * index,
                longitude=Decimal("-0.1870"),
                speed_kph=Decimal("30.00"),
            )
        return stamps

    def url(self, vehicle=None):
        return reverse("telemetry:list", kwargs={"pk": (vehicle or self.vehicle).pk})

    def test_authentication_required(self):
        self.seed_history()
        self.assertEqual(self.client.get(self.url(), secure=True).status_code, 401)

    def test_operator_sees_full_history_newest_first(self):
        self.seed_history()
        self.authenticate(self.operator)
        response = self.client.get(self.url(), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        stamps = [row["recorded_at"] for row in response.data["results"]]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_time_range_and_ordering_filters(self):
        stamps = self.seed_history()
        self.authenticate(self.operator)
        start = timezone.now() - timedelta(minutes=15)
        response = self.client.get(
            self.url(),
            {"start": start.isoformat(), "ordering": "recorded_at"},
            secure=True,
        )
        # Only the newest record is at/after the 15-minute mark.
        self.assertEqual(response.data["count"], 1)
        response = self.client.get(
            self.url(),
            {
                "end": (timezone.now() - timedelta(minutes=15)).isoformat(),
                "ordering": "recorded_at",
            },
            secure=True,
        )
        self.assertEqual(response.data["count"], 2)
        returned = [row["recorded_at"] for row in response.data["results"]]
        self.assertEqual(returned, sorted(returned))
        self.assertNotIn(stamps[-1].isoformat().replace("+00:00", "Z"), returned)

    def test_invalid_filters_fail_loudly(self):
        self.seed_history()
        self.authenticate(self.operator)
        self.assertEqual(
            self.client.get(self.url(), {"start": "nonsense"}, secure=True).status_code, 400
        )
        end = timezone.now() - timedelta(days=1)
        self.assertEqual(
            self.client.get(
                self.url(),
                {"start": timezone.now().isoformat(), "end": end.isoformat()},
                secure=True,
            ).status_code,
            400,
        )

    def test_customer_scoped_to_own_vehicles(self):
        self.seed_history()
        self.authenticate(self.customer)
        self.assertEqual(self.client.get(self.url(), secure=True).status_code, 200)
        # Unassigned vehicles are invisible to customers.
        other_url = self.url(self.other_vehicle)
        self.assertEqual(self.client.get(other_url, secure=True).status_code, 404)
        self.authenticate(self.other)
        self.assertEqual(self.client.get(self.url(), secure=True).status_code, 404)

    def test_admin_can_read_all_vehicles(self):
        self.seed_history()
        admin = User.objects.create_user(username="telemetry_admin", role=User.Role.ADMIN)
        self.authenticate(admin)
        self.assertEqual(self.client.get(self.url(), secure=True).status_code, 200)
        self.assertEqual(
            self.client.get(self.url(self.other_vehicle), secure=True).data["count"], 0
        )

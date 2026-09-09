"""Phase 5 tests: geofence evaluation, alerts, offline check and the alerts API."""

from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User
from vehicles.models import Device, Vehicle

from .alerts import Alert
from .geo import haversine_distance_m
from .services import ingest_telemetry

# A geofence around Accra centre with a 2 km radius.
CENTER = (5.6037, -0.1870)
RADIUS_M = 2000
# About 30 m north of the center: inside.
INSIDE = (5.60397, -0.187)
# About 2.2 km north: outside a 2 km radius.
OUTSIDE = (5.6235, -0.187)


def payload_for(device_id, lat, lon, **overrides):
    payload = {
        "device_id": device_id,
        "latitude": lat,
        "longitude": lon,
        "speed": 45,
        "battery": 80,
        "recorded_at": (timezone.now() - timedelta(seconds=5)).isoformat(),
    }
    payload.update(overrides)
    return payload


class GeoTests(APITestCase):
    def test_haversine_known_distances(self):
        accra = (5.6037, -0.1870)
        kumasi = (6.6886, -1.6244)
        distance = haversine_distance_m(*accra, *kumasi)
        # Great-circle distance Accra–Kumasi is roughly 190 km.
        self.assertGreater(distance, 180_000)
        self.assertLess(distance, 200_000)
        # Zero distance to itself.
        self.assertEqual(haversine_distance_m(*accra, *accra), 0.0)

    def test_small_offsets(self):
        # 0.001 degrees of latitude is roughly 111 m.
        distance = haversine_distance_m(5.6037, -0.1870, 5.6047, -0.1870)
        self.assertGreater(distance, 100)
        self.assertLess(distance, 125)


class GeofenceEvaluationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="geo_customer")
        cls.profile_customer = cls.customer
        from customers.models import CustomerProfile

        cls.profile = CustomerProfile.objects.create(
            user=cls.customer,
            full_name="Geo Customer",
            phone="+233201234567",
            monthly_income="6500.00",
            employment_status="EMPLOYED",
        )
        cls.vehicle = Vehicle.objects.create(
            registration_number="GEO-001",
            vin="1HGCM82633A004352",
            make="Toyota",
            model_name="Corolla",
            year=2020,
            customer=cls.profile,
            geofence_latitude=Decimal(str(CENTER[0])),
            geofence_longitude=Decimal(str(CENTER[1])),
            geofence_radius_m=RADIUS_M,
        )
        cls.device = Device.objects.create(device_id="GPS-GEO", vehicle=cls.vehicle)

    def test_inside_position_clears_alerts(self):
        record, created = ingest_telemetry(payload_for("GPS-GEO", *INSIDE))
        self.assertTrue(created)
        self.assertFalse(
            Alert.objects.filter(vehicle=self.vehicle, type=Alert.Type.GEOFENCE_EXIT).exists()
        )

    def test_outside_position_raises_one_open_alert(self):
        for _ in range(3):
            ingest_telemetry(payload_for("GPS-GEO", *OUTSIDE))
        alerts = Alert.objects.filter(vehicle=self.vehicle, type=Alert.Type.GEOFENCE_EXIT)
        self.assertEqual(alerts.count(), 1)
        self.assertTrue(alerts.first().is_open)

    def test_returning_inside_auto_resolves(self):
        ingest_telemetry(payload_for("GPS-GEO", *OUTSIDE))
        self.assertTrue(
            Alert.objects.filter(vehicle=self.vehicle, type=Alert.Type.GEOFENCE_EXIT).get().is_open
        )
        ingest_telemetry(payload_for("GPS-GEO", *INSIDE))
        alert = Alert.objects.get(vehicle=self.vehicle, type=Alert.Type.GEOFENCE_EXIT)
        self.assertFalse(alert.is_open)
        # Coming back inside again opens a new incident.
        ingest_telemetry(payload_for("GPS-GEO", *OUTSIDE))
        self.assertTrue(
            Alert.objects.filter(vehicle=self.vehicle, type=Alert.Type.GEOFENCE_EXIT)
            .first()
            .is_open
        )

    def test_speeding_and_low_battery_lifecycle(self):
        ingest_telemetry(payload_for("GPS-GEO", *INSIDE, speed=140))
        self.assertTrue(
            Alert.objects.filter(vehicle=self.vehicle, type=Alert.Type.SPEEDING).get().is_open
        )
        ingest_telemetry(payload_for("GPS-GEO", *INSIDE, speed=60))
        self.assertFalse(
            Alert.objects.filter(vehicle=self.vehicle, type=Alert.Type.SPEEDING).get().is_open
        )
        ingest_telemetry(payload_for("GPS-GEO", *INSIDE, battery=15))
        self.assertTrue(
            Alert.objects.filter(vehicle=self.vehicle, type=Alert.Type.LOW_BATTERY).get().is_open
        )
        ingest_telemetry(payload_for("GPS-GEO", *INSIDE, battery=90))
        self.assertFalse(
            Alert.objects.filter(vehicle=self.vehicle, type=Alert.Type.LOW_BATTERY).get().is_open
        )

    def test_fresh_message_clears_offline(self):
        Alert.raise_or_refresh(
            vehicle=self.vehicle,
            alert_type=Alert.Type.OFFLINE,
            severity=Alert.Severity.MEDIUM,
            message="stale",
        )
        ingest_telemetry(payload_for("GPS-GEO", *INSIDE))
        alert = Alert.objects.get(vehicle=self.vehicle, type=Alert.Type.OFFLINE)
        self.assertFalse(alert.is_open)

    def test_vehicle_without_geofence_is_never_flagged(self):
        plain = Vehicle.objects.create(
            registration_number="GEO-002",
            vin="1HGCM82633A004353",
            make="Toyota",
            model_name="Corolla",
            year=2020,
        )
        Device.objects.create(device_id="GPS-PLAIN", vehicle=plain)
        ingest_telemetry(payload_for("GPS-PLAIN", *OUTSIDE))
        self.assertFalse(Alert.objects.filter(vehicle=plain).exists())


class OfflineCommandTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vehicle = Vehicle.objects.create(
            registration_number="OFF-001",
            vin="1HGCM82633A004354",
            make="Toyota",
            model_name="Corolla",
            year=2020,
        )
        cls.device = Device.objects.create(device_id="GPS-OFF", vehicle=cls.vehicle)

    def test_silent_vehicle_goes_offline(self):
        Vehicle.objects.filter(pk=self.vehicle.pk).update(
            last_telemetry_at=timezone.now() - timedelta(hours=3),
            connectivity_status=Vehicle.Connectivity.ONLINE,
        )
        call_command("check_offline_vehicles")
        alert = Alert.objects.get(vehicle=self.vehicle, type=Alert.Type.OFFLINE)
        self.assertTrue(alert.is_open)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.connectivity_status, Vehicle.Connectivity.OFFLINE)

    def test_recent_or_untracked_vehicles_are_skipped(self):
        Vehicle.objects.filter(pk=self.vehicle.pk).update(
            last_telemetry_at=timezone.now() - timedelta(minutes=2)
        )
        call_command("check_offline_vehicles")
        self.assertFalse(Alert.objects.filter(vehicle=self.vehicle).exists())
        Vehicle.objects.filter(pk=self.vehicle.pk).update(last_telemetry_at=None)
        call_command("check_offline_vehicles")
        self.assertFalse(Alert.objects.filter(vehicle=self.vehicle).exists())

    def test_second_run_refreshes_instead_of_stacking(self):
        Vehicle.objects.filter(pk=self.vehicle.pk).update(
            last_telemetry_at=timezone.now() - timedelta(hours=3)
        )
        call_command("check_offline_vehicles")
        call_command("check_offline_vehicles")
        self.assertEqual(Alert.objects.filter(vehicle=self.vehicle).count(), 1)


class AlertAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="alert_customer")
        cls.other = User.objects.create_user(username="alert_other")
        cls.operator = User.objects.create_user(
            username="alert_operator", role=User.Role.OPERATIONS
        )
        from customers.models import CustomerProfile

        cls.profile = CustomerProfile.objects.create(
            user=cls.customer,
            full_name="Alert Customer",
            phone="+233201234567",
            monthly_income="6500.00",
            employment_status="EMPLOYED",
        )
        cls.vehicle = Vehicle.objects.create(
            registration_number="ALR-001",
            vin="1HGCM82633A004355",
            make="Toyota",
            model_name="Corolla",
            year=2020,
            customer=cls.profile,
        )
        other_profile = CustomerProfile.objects.create(
            user=cls.other,
            full_name="Alert Other",
            phone="+233201234568",
            monthly_income="6500.00",
            employment_status="EMPLOYED",
        )
        cls.other_vehicle = Vehicle.objects.create(
            registration_number="ALR-002",
            vin="1HGCM82633A004356",
            make="Toyota",
            model_name="Corolla",
            year=2020,
            customer=other_profile,
        )
        Alert.objects.create(
            vehicle=cls.vehicle,
            type=Alert.Type.GEOFENCE_EXIT,
            severity=Alert.Severity.HIGH,
            message="left the area",
        )
        Alert.objects.create(
            vehicle=cls.other_vehicle,
            type=Alert.Type.SPEEDING,
            severity=Alert.Severity.HIGH,
            message="too fast",
        )

    def authenticate(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
        )

    def test_authentication_required(self):
        self.assertEqual(self.client.get(reverse("telemetry:alerts"), secure=True).status_code, 401)

    def test_customer_scoping_and_filters(self):
        self.authenticate(self.customer)
        response = self.client.get(reverse("telemetry:alerts"), secure=True)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["type"], "GEOFENCE_EXIT")
        response = self.client.get(reverse("telemetry:alerts"), {"resolved": "false"}, secure=True)
        self.assertEqual(response.data["count"], 1)
        response = self.client.get(reverse("telemetry:alerts"), {"type": "SPEEDING"}, secure=True)
        self.assertEqual(response.data["count"], 0)

    def test_operator_sees_all_and_resolves(self):
        self.authenticate(self.operator)
        response = self.client.get(reverse("telemetry:alerts"), secure=True)
        self.assertEqual(response.data["count"], 2)
        alert_id = response.data["results"][0]["id"]
        detail = reverse("telemetry:alert-resolve", kwargs={"pk": alert_id})
        response = self.client.post(detail, {}, format="json", secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data["resolved_at"])
        self.assertEqual(response.data["resolved_by"], self.operator.pk)

    def test_customer_cannot_resolve(self):
        self.authenticate(self.customer)
        alert = Alert.objects.filter(vehicle=self.vehicle).first()
        detail = reverse("telemetry:alert-resolve", kwargs={"pk": alert.pk})
        self.assertEqual(self.client.post(detail, {}, format="json", secure=True).status_code, 403)

    def test_resolve_rejects_body(self):
        self.authenticate(self.operator)
        alert = Alert.objects.filter(vehicle=self.vehicle).first()
        detail = reverse("telemetry:alert-resolve", kwargs={"pk": alert.pk})
        response = self.client.post(detail, {"note": "nope"}, format="json", secure=True)
        self.assertEqual(response.status_code, 400)

    def test_vehicle_geofence_validation(self):
        self.authenticate(self.operator)
        url = reverse("vehicles:detail", kwargs={"pk": self.vehicle.pk})
        partial = self.client.patch(url, {"geofence_latitude": 5.6}, format="json", secure=True)
        self.assertEqual(partial.status_code, 400)
        full = self.client.patch(
            url,
            {
                "geofence_latitude": "5.6037",
                "geofence_longitude": "-0.1870",
                "geofence_radius_m": 2000,
            },
            format="json",
            secure=True,
        )
        self.assertEqual(full.status_code, 200, full.data)
        cleared = self.client.patch(
            url,
            {
                "geofence_latitude": None,
                "geofence_longitude": None,
                "geofence_radius_m": None,
            },
            format="json",
            secure=True,
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.data["geofence_radius_m"])

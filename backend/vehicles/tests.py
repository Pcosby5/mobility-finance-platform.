from types import SimpleNamespace
from uuid import UUID, uuid4

from customers.models import CustomerProfile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User

from .models import Device, Vehicle
from .serializers import DeviceSerializer, VehicleSerializer


class VehicleDeviceTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="vehicle_customer")
        cls.other = User.objects.create_user(username="vehicle_other")
        cls.operator = User.objects.create_user(
            username="vehicle_operator", role=User.Role.OPERATIONS
        )
        cls.admin = User.objects.create_user(username="vehicle_admin", role=User.Role.ADMIN)
        cls.profile = CustomerProfile.objects.create(
            user=cls.customer,
            full_name="Demo Customer",
            phone="+233201234567",
            monthly_income="6500.00",
            employment_status="EMPLOYED",
        )

    def authenticate(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
        )

    def payload(self, **overrides):
        return {
            "registration_number": "DEMO-001",
            "vin": "1HGCM82633A004352",
            "make": "Honda",
            "model_name": "Accord",
            "year": 2003,
            **overrides,
        }

    def create_vehicle(self, **overrides):
        return self.client.post(
            reverse("vehicles:list"), self.payload(**overrides), format="json", secure=True
        )

    def vehicle(self, **overrides):
        return Vehicle.objects.create(**self.payload(**overrides))

    def vehicle_url(self, vehicle):
        return reverse("vehicles:detail", kwargs={"pk": vehicle.pk})

    def device_url(self, device):
        return reverse("vehicles:device-detail", kwargs={"pk": device.pk})

    def create_device(self, **overrides):
        return self.client.post(
            reverse("vehicles:device-list"),
            {"device_id": "GPS-001", **overrides},
            format="json",
            secure=True,
        )

    def test_authentication_required(self):
        self.assertEqual(self.create_vehicle().status_code, 401)
        self.assertEqual(self.create_device().status_code, 401)
        self.assertEqual(self.client.get(reverse("vehicles:list"), secure=True).status_code, 401)

    def test_operations_and_admin_can_create_vehicles(self):
        for index, actor in enumerate([self.operator, self.admin]):
            self.authenticate(actor)
            response = self.create_vehicle(
                registration_number=f"DEMO-{index}",
                vin=f"1HGCM82633A00435{index}",
                customer=str(self.profile.pk),
            )
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(UUID(response.data["id"]).version, 4)
            self.assertEqual(response.data["customer"], str(self.profile.pk))
            self.assertEqual(response.data["connectivity_status"], "UNKNOWN")
            self.assertEqual(response.data["movement_status"], "UNKNOWN")
            self.assertIsNone(response.data["last_latitude"])
            self.assertIsNone(response.data["device"])

    def test_customer_read_scope_and_write_denial(self):
        owned = self.vehicle(customer=self.profile)
        unassigned = self.vehicle(registration_number="DEMO-002", vin="1HGCM82633A004353")
        self.authenticate(self.customer)
        response = self.client.get(reverse("vehicles:list"), secure=True)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(owned.pk))
        self.assertEqual(self.client.get(self.vehicle_url(owned), secure=True).status_code, 200)
        self.assertEqual(
            self.client.get(self.vehicle_url(unassigned), secure=True).status_code, 404
        )
        self.assertEqual(self.create_vehicle().status_code, 403)
        self.assertEqual(
            self.client.patch(
                self.vehicle_url(owned), {"status": "RETIRED"}, secure=True
            ).status_code,
            403,
        )
        self.authenticate(self.other)
        self.assertEqual(self.client.get(self.vehicle_url(owned), secure=True).status_code, 404)

    def test_privileged_user_can_assign_and_unassign_customer(self):
        vehicle = self.vehicle()
        self.authenticate(self.operator)
        url = self.vehicle_url(vehicle)
        response = self.client.patch(
            url, {"customer": str(self.profile.pk)}, format="json", secure=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["customer"], str(self.profile.pk))
        self.assertEqual(
            self.client.patch(url, {"customer": None}, format="json", secure=True).status_code, 200
        )
        self.authenticate(self.customer)
        self.assertEqual(self.client.get(url, secure=True).status_code, 404)

    def test_identifiers_are_normalized_and_duplicates_rejected(self):
        self.authenticate(self.operator)
        response = self.create_vehicle(registration_number=" demo-001 ", vin="1hgcm82633a004352")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["registration_number"], "DEMO-001")
        self.assertEqual(response.data["vin"], "1HGCM82633A004352")
        self.assertEqual(self.create_vehicle(registration_number="demo-001").status_code, 400)
        self.assertEqual(self.create_vehicle(registration_number="OTHER").status_code, 400)

    def test_vehicle_validation_and_readonly_telemetry(self):
        self.authenticate(self.operator)
        for invalid in [
            {"vin": "short"},
            {"vin": "I" * 17},
            {"year": 1899},
            {"year": timezone.now().year + 2},
            {"make": " "},
            {"status": "INVALID"},
            {"customer": str(uuid4())},
            {"customer": str(self.customer.pk)},
            {"id": str(uuid4())},
            {"connectivity_status": "ONLINE"},
            {"movement_status": "MOVING"},
            {"last_latitude": "5.6"},
        ]:
            with self.subTest(invalid=invalid):
                self.assertEqual(self.create_vehicle(**invalid).status_code, 400)
        self.assertFalse(Vehicle.objects.exists())

    def test_database_protects_vehicle_values_and_coordinates(self):
        vehicle = self.vehicle()
        for invalid in [
            {"year": 1800},
            {"vin": "1hgcm82633a004352"},
            {"status": "INVALID"},
            {"connectivity_status": "INVALID"},
            {"movement_status": "INVALID"},
            {"last_latitude": "5.6"},
            {"last_latitude": "91", "last_longitude": "0"},
            {"last_latitude": "0", "last_longitude": "181"},
        ]:
            with (
                self.subTest(invalid=invalid),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                Vehicle.objects.filter(pk=vehicle.pk).update(**invalid)

    def test_device_creation_linking_and_customer_summary(self):
        vehicle = self.vehicle(customer=self.profile)
        self.authenticate(self.operator)
        response = self.create_device(vehicle=str(vehicle.pk))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(UUID(response.data["id"]).version, 4)
        self.authenticate(self.customer)
        response = self.client.get(self.vehicle_url(vehicle), secure=True)
        self.assertEqual(response.data["device"]["device_id"], "GPS-001")

    def test_device_management_is_restricted_to_operations_and_admin(self):
        device = Device.objects.create(device_id="GPS-001")
        self.authenticate(self.customer)
        self.assertEqual(self.create_device().status_code, 403)
        self.assertEqual(
            self.client.get(reverse("vehicles:device-list"), secure=True).status_code, 403
        )
        self.assertEqual(self.client.get(self.device_url(device), secure=True).status_code, 403)
        self.assertEqual(
            self.client.patch(self.device_url(device), {"enabled": False}, secure=True).status_code,
            403,
        )
        self.authenticate(self.admin)
        self.assertEqual(self.client.get(self.device_url(device), secure=True).status_code, 200)

    def test_device_assignment_is_unique_and_can_be_detached(self):
        vehicle = self.vehicle()
        device = Device.objects.create(device_id="GPS-001", vehicle=vehicle)
        self.authenticate(self.operator)
        self.assertEqual(
            self.create_device(device_id="GPS-002", vehicle=str(vehicle.pk)).status_code, 400
        )
        response = self.client.patch(
            self.device_url(device), {"vehicle": None, "enabled": False}, format="json", secure=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.create_device(device_id="GPS-002", vehicle=str(vehicle.pk)).status_code, 201
        )
        device.refresh_from_db()
        self.assertIsNone(device.vehicle)
        self.assertFalse(device.enabled)

    def test_device_identity_is_validated_unique_and_immutable(self):
        self.authenticate(self.operator)
        self.assertEqual(self.create_device(device_id="vehicles/+/telemetry").status_code, 400)
        response = self.create_device()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.create_device().status_code, 400)
        device = Device.objects.get(pk=response.data["id"])
        response = self.client.patch(
            self.device_url(device), {"device_id": "NEW"}, format="json", secure=True
        )
        self.assertEqual(response.status_code, 400)

    def test_duplicate_races_return_validation_errors(self):
        context = {"request": SimpleNamespace(user=self.operator)}
        for serializer_class, payload in [
            (VehicleSerializer, self.payload()),
            (DeviceSerializer, {"device_id": "GPS-RACE"}),
        ]:
            first = serializer_class(data=payload, context=context)
            second = serializer_class(data=payload, context=context)
            self.assertTrue(first.is_valid(), first.errors)
            self.assertTrue(second.is_valid(), second.errors)
            first.save()
            with self.assertRaises(ValidationError):
                second.save()

    def test_database_prevents_multiple_devices_per_vehicle(self):
        vehicle = self.vehicle()
        Device.objects.create(device_id="GPS-001", vehicle=vehicle)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Device.objects.create(device_id="GPS-002", vehicle=vehicle)

    def test_delete_is_not_exposed(self):
        vehicle = self.vehicle()
        device = Device.objects.create(device_id="GPS-001")
        self.authenticate(self.operator)
        self.assertEqual(
            self.client.delete(self.vehicle_url(vehicle), secure=True).status_code, 405
        )
        self.assertEqual(self.client.delete(self.device_url(device), secure=True).status_code, 405)

    def test_swagger_uses_uuid_references_and_excludes_telemetry_inputs(self):
        schema = self.client.get("/api/schema/?format=json", secure=True).json()
        components = schema["components"]["schemas"]
        for model in ["Vehicle", "Device"]:
            self.assertEqual(components[model]["properties"]["id"]["format"], "uuid")
        self.assertEqual(components["Vehicle"]["properties"]["customer"]["format"], "uuid")
        self.assertEqual(components["Device"]["properties"]["vehicle"]["format"], "uuid")
        self.assertNotIn("last_latitude", components["VehicleRequest"]["properties"])

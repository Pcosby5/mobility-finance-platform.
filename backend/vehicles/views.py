from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView

from .models import Device, Vehicle
from .permissions import ManageDevicePermission, VehicleAccessPermission, can_manage_vehicles
from .serializers import DeviceSerializer, VehicleSerializer


class VehicleQuerysetMixin:
    serializer_class = VehicleSerializer
    permission_classes = [VehicleAccessPermission]

    def get_queryset(self):
        queryset = Vehicle.objects.select_related("customer__user", "device")
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        if can_manage_vehicles(self.request.user):
            return queryset
        return queryset.filter(customer__user=self.request.user)


@extend_schema_view(
    get=extend_schema(tags=["Vehicles"], summary="List accessible vehicles"),
    post=extend_schema(
        tags=["Vehicles"],
        summary="Create a vehicle (operations/admin)",
        description=(
            "Optionally supply customer with a customer profile UUID. "
            "Telemetry fields are read-only."
        ),
        examples=[
            OpenApiExample(
                "Demo vehicle",
                request_only=True,
                value={
                    "registration_number": "DEMO-001",
                    "vin": "1HGCM82633A004352",
                    "make": "Honda",
                    "model_name": "Accord",
                    "year": 2003,
                    "status": "ACTIVE",
                },
            )
        ],
    ),
)
class VehicleListCreateView(VehicleQuerysetMixin, ListCreateAPIView):
    pass


@extend_schema_view(
    get=extend_schema(tags=["Vehicles"], summary="Get an accessible vehicle"),
    patch=extend_schema(tags=["Vehicles"], summary="Update or assign a vehicle (operations/admin)"),
)
class VehicleDetailView(VehicleQuerysetMixin, RetrieveUpdateAPIView):
    http_method_names = ["get", "patch", "head", "options"]


class DeviceQuerysetMixin:
    serializer_class = DeviceSerializer
    permission_classes = [ManageDevicePermission]
    queryset = Device.objects.all()


@extend_schema_view(
    get=extend_schema(tags=["Devices"], summary="List devices (operations/admin)"),
    post=extend_schema(
        tags=["Devices"],
        summary="Register a device (operations/admin)",
        description=(
            "device_id is a stable MQTT identifier, not a password. "
            "Optionally supply a vehicle UUID."
        ),
        examples=[
            OpenApiExample(
                "Demo GPS device",
                request_only=True,
                value={"device_id": "GPS-001", "enabled": True},
            )
        ],
    ),
)
class DeviceListCreateView(DeviceQuerysetMixin, ListCreateAPIView):
    pass


@extend_schema_view(
    get=extend_schema(tags=["Devices"], summary="Get a device (operations/admin)"),
    patch=extend_schema(
        tags=["Devices"],
        summary="Assign or disable a device (operations/admin)",
        description=(
            "Set vehicle to a vehicle UUID or null to detach. Device identity is immutable."
        ),
    ),
)
class DeviceDetailView(DeviceQuerysetMixin, RetrieveUpdateAPIView):
    http_method_names = ["get", "patch", "head", "options"]

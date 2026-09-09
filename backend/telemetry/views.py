from datetime import UTC

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import SAFE_METHODS, BasePermission
from users.models import User
from vehicles.models import Vehicle
from vehicles.permissions import can_manage_vehicles

from .models import TelemetryRecord
from .serializers import TelemetryRecordSerializer


class TelemetryAccessPermission(BasePermission):
    """Customers may read telemetry of their own vehicles; staff of all."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return can_manage_vehicles(request.user) or (
            request.user.role == User.Role.CUSTOMER and request.method in SAFE_METHODS
        )


class VehicleTelemetryQuerysetMixin:
    permission_classes = [TelemetryAccessPermission]
    serializer_class = TelemetryRecordSerializer

    def vehicle_queryset(self):
        queryset = Vehicle.objects.all()
        if getattr(self, "swagger_fake_view", False) or not hasattr(self, "request"):
            return queryset.none()
        if can_manage_vehicles(self.request.user):
            return queryset
        return queryset.filter(customer__user=self.request.user)

    def filtered_queryset(self):
        queryset = TelemetryRecord.objects.all()
        vehicle = get_object_or_404(self.vehicle_queryset(), pk=self.kwargs["pk"])
        queryset = queryset.filter(vehicle=vehicle)

        # Time-range filtering; invalid values fail loudly rather than silently
        # returning unfiltered data.
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        parsed = {}
        for name, value in (("start", start), ("end", end)):
            if not value:
                continue
            stamp = parse_datetime(value)
            if stamp is None:
                raise ValidationError({name: "Use an ISO-8601 timestamp."})
            if timezone.is_naive(stamp):
                stamp = timezone.make_aware(stamp, UTC)
            parsed[name] = stamp
        if parsed.get("start") and parsed.get("end") and parsed["start"] > parsed["end"]:
            raise ValidationError({"start": "start must not be after end."})
        if "start" in parsed:
            queryset = queryset.filter(recorded_at__gte=parsed["start"])
        if "end" in parsed:
            queryset = queryset.filter(recorded_at__lte=parsed["end"])

        ordering = self.request.query_params.get("ordering", "-recorded_at")
        if ordering not in ("recorded_at", "-recorded_at"):
            ordering = "-recorded_at"
        return queryset.order_by(ordering, "id")


@extend_schema_view(
    get=extend_schema(
        tags=["Telemetry"],
        summary="List telemetry history for a vehicle",
        description=(
            "Newest first by default. Optional ISO-8601 query parameters: "
            "start, end, ordering=recorded_at|-recorded_at. Results are paginated."
        ),
        responses={200: TelemetryRecordSerializer(many=True)},
        parameters=[
            OpenApiParameter(
                name="start",
                type=OpenApiTypes.DATETIME,
                description="Inclusive lower bound on recorded_at.",
            ),
            OpenApiParameter(
                name="end",
                type=OpenApiTypes.DATETIME,
                description="Inclusive upper bound on recorded_at.",
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                enum=["recorded_at", "-recorded_at"],
            ),
        ],
    )
)
class VehicleTelemetryListView(VehicleTelemetryQuerysetMixin, ListAPIView):
    def get_queryset(self):
        return self.filtered_queryset()

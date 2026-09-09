from django.urls import path

from .views import AlertListView, AlertResolveView, VehicleTelemetryListView

app_name = "telemetry"
urlpatterns = [
    path("vehicles/<uuid:pk>/telemetry/", VehicleTelemetryListView.as_view(), name="list"),
    path("alerts/", AlertListView.as_view(), name="alerts"),
    path("alerts/<uuid:pk>/resolve/", AlertResolveView.as_view(), name="alert-resolve"),
]

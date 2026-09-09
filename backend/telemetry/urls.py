from django.urls import path

from .views import VehicleTelemetryListView

app_name = "telemetry"
urlpatterns = [
    path("vehicles/<uuid:pk>/telemetry/", VehicleTelemetryListView.as_view(), name="list"),
]

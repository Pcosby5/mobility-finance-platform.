from django.urls import path

from .views import DeviceDetailView, DeviceListCreateView, VehicleDetailView, VehicleListCreateView

app_name = "vehicles"
urlpatterns = [
    path("vehicles/", VehicleListCreateView.as_view(), name="list"),
    path("vehicles/<uuid:pk>/", VehicleDetailView.as_view(), name="detail"),
    path("devices/", DeviceListCreateView.as_view(), name="device-list"),
    path("devices/<uuid:pk>/", DeviceDetailView.as_view(), name="device-detail"),
]

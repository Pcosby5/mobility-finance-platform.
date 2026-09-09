from rest_framework.permissions import SAFE_METHODS, BasePermission
from users.models import User


def can_manage_vehicles(user):
    return user.role in (User.Role.ADMIN, User.Role.OPERATIONS)


class VehicleAccessPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return can_manage_vehicles(request.user) or (
            request.user.role == User.Role.CUSTOMER and request.method in SAFE_METHODS
        )

    def has_object_permission(self, request, view, obj):
        return can_manage_vehicles(request.user) or (
            obj.customer_id is not None and obj.customer.user_id == request.user.pk
        )


class ManageDevicePermission(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and can_manage_vehicles(request.user)

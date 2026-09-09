from rest_framework.permissions import BasePermission
from users.models import User


def can_manage_customers(user):
    return user.role in (User.Role.ADMIN, User.Role.OPERATIONS)


class CustomerAccessPermission(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in User.Role.values

    def has_object_permission(self, request, view, obj):
        return can_manage_customers(request.user) or obj.user_id == request.user.pk

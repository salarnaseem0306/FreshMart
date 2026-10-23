from rest_framework.permissions import BasePermission

from accounts.models import User


class IsManager(BasePermission):
    """Only users with the manager role."""

    message = "Manager role required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.Role.MANAGER)


class IsCashierOrManager(BasePermission):
    """Any logged-in staff member: cashier or manager."""

    message = "Cashier or manager role required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role in (User.Role.CASHIER, User.Role.MANAGER)
        )
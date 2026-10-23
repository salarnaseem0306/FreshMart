from rest_framework.permissions import SAFE_METHODS, BasePermission

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
class CashierReadManagerWrite(BasePermission):
    """Reading: cashier or manager. Changing anything: manager only."""

    message = "Only managers can change this."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:  # GET, HEAD, OPTIONS
            return IsCashierOrManager().has_permission(request, view)
        return IsManager().has_permission(request, view)    
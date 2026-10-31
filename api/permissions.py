from rest_framework.permissions import SAFE_METHODS, BasePermission


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


class IsStaffMember(BasePermission):
    """Admins and staff; customers use the portal (or the customer-scoped endpoints)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff_member)

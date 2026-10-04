"""Role-based permission classes. Views combine these with DRF's default IsAuthenticated."""

from rest_framework.permissions import BasePermission

from .models import User


class RolePermission(BasePermission):
    allowed_roles: frozenset = frozenset()

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in self.allowed_roles)


class IsClient(RolePermission):
    allowed_roles = frozenset({User.Role.CLIENT})


class IsOperatorOrAdmin(RolePermission):
    allowed_roles = frozenset({User.Role.OPERATOR, User.Role.ADMIN})


class IsAdmin(RolePermission):
    allowed_roles = frozenset({User.Role.ADMIN})

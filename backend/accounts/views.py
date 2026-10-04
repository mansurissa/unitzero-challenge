from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.middleware.csrf import get_token
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import User
from .permissions import IsAdmin
from .serializers import LoginSerializer, UserCreateSerializer, UserSerializer, UserUpdateSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    """Sets the csrftoken cookie so a fresh browser session can make its first POST (login)."""
    return Response({"csrfToken": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    # ModelBackend refuses inactive users, so a deactivated account gets the same error as a wrong password.
    user = authenticate(
        request,
        username=serializer.validated_data["email"].strip().lower(),
        password=serializer.validated_data["password"],
    )
    if user is None:
        return Response({"detail": "Invalid email or password."}, status=status.HTTP_400_BAD_REQUEST)
    django_login(request, user)
    get_token(request)  # rotate + send the CSRF cookie along with the session cookie
    return Response(UserSerializer(user).data)


@api_view(["POST"])
def logout(request):
    django_logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def me(request):
    return Response(UserSerializer(request.user).data)


class UserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Admin-only user management: list, create, change role / name / organisation, (de)activate.

    There is no delete: deactivating keeps the audit trail (who did what) intact.
    """

    permission_classes = [IsAdmin]
    queryset = User.objects.order_by("id")
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action == "partial_update":
            return UserUpdateSerializer
        return UserSerializer

    def perform_update(self, serializer):
        user = serializer.instance
        changes = serializer.validated_data
        # An admin cannot lock themselves out: the last admin would otherwise be able to remove all admin access.
        if user == self.request.user:
            if changes.get("is_active") is False:
                raise ValidationError({"is_active": "You cannot deactivate your own account."})
            if "role" in changes and changes["role"] != User.Role.ADMIN:
                raise ValidationError({"role": "You cannot remove your own admin role."})
        serializer.save()

    def create(self, request, *args, **kwargs):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        # Return the full representation after a PATCH, not just the editable fields.
        super().update(request, *args, **kwargs)
        return Response(UserSerializer(self.get_object()).data)

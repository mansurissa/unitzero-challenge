from rest_framework import serializers

from .models import User


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "name", "role", "organisation", "is_active", "date_joined"]
        read_only_fields = fields


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["id", "email", "name", "role", "organisation", "password"]
        # The auto-generated UniqueValidator compares the raw value; we normalise first and check ourselves.
        extra_kwargs = {"email": {"validators": []}}

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserUpdateSerializer(serializers.ModelSerializer):
    """Admins can change role, active flag, name and organisation. Email and password are not editable here."""

    class Meta:
        model = User
        fields = ["name", "role", "organisation", "is_active"]

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings

from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "role")
        read_only_fields = fields


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "password")
        read_only_fields = ("id",)
        extra_kwargs = {"email": {"required": True, "allow_blank": False}}

    def validate(self, attrs):
        # Reject extra input explicitly so privilege fields are never silently accepted.
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "This field is not accepted." for field in sorted(unknown)}
            )
        candidate = User(**{key: value for key, value in attrs.items() if key != "password"})
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return User.objects.create_user(**validated_data, role=User.Role.CUSTOMER)
        except IntegrityError as exc:
            # A concurrent registration can claim the username after serializer validation.
            if User.objects.filter(username=validated_data["username"]).exists():
                raise serializers.ValidationError(
                    {"username": "A user with that username already exists."}
                ) from exc
            raise


class ActiveUserTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        token = self.token_class(attrs["refresh"])
        if not token.get(api_settings.USER_ID_CLAIM):
            raise InvalidToken("Please log in again to obtain tokens with a UUID user ID.")
        try:
            return super().validate(attrs)
        except User.DoesNotExist as exc:
            # Simple JWT 5.5 checks inactive accounts but lets deleted-user lookups escape.
            raise AuthenticationFailed("No active account found for the given token.") from exc

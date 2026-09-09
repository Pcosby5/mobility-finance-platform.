from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers
from rest_framework.generics import CreateAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)

from .serializers import (
    ActiveUserTokenRefreshSerializer,
    RegistrationSerializer,
    UserSerializer,
)

token_pair_response = inline_serializer(
    name="TokenPairResponse",
    fields={"access": serializers.CharField(), "refresh": serializers.CharField()},
)
refresh_request = inline_serializer(
    name="RefreshTokenInput", fields={"refresh": serializers.CharField()}
)


@extend_schema_view(
    post=extend_schema(
        tags=["Authentication"],
        summary="Register a customer",
        description="Creates a CUSTOMER. Role and staff fields are rejected.",
        examples=[
            OpenApiExample(
                "Demo customer",
                value={
                    "username": "demo_customer",
                    "email": "demo@example.com",
                    "password": "Demo-only!CorrectHorse7492",
                },
                request_only=True,
            )
        ],
    )
)
class RegisterView(CreateAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


@extend_schema_view(
    post=extend_schema(
        tags=["Authentication"],
        summary="Log in with username and password",
        responses={
            200: token_pair_response,
            401: OpenApiResponse(description="Invalid credentials"),
        },
        examples=[
            OpenApiExample(
                "Demo login",
                value={"username": "demo_customer", "password": "Demo-only!CorrectHorse7492"},
                request_only=True,
            )
        ],
    )
)
class LoginView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


@extend_schema_view(
    post=extend_schema(
        tags=["Authentication"],
        summary="Refresh and rotate tokens",
        description="Submit your latest refresh token. Replace both tokens with the returned pair.",
        request=refresh_request,
        responses={
            200: token_pair_response,
            401: OpenApiResponse(description="Invalid refresh token"),
        },
    )
)
class RefreshView(TokenRefreshView):
    serializer_class = ActiveUserTokenRefreshSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


@extend_schema_view(
    post=extend_schema(
        tags=["Authentication"],
        summary="Revoke a refresh token",
        description=(
            "Submit the latest refresh token. Access tokens remain valid until their "
            "five-minute expiry. Swagger's Authorize logout only clears its local token; "
            "call this endpoint to revoke a refresh token on the server."
        ),
        request=refresh_request,
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Refresh token revoked",
                examples=[OpenApiExample("Logged out", value={})],
            ),
            401: OpenApiResponse(description="Invalid or already revoked refresh token"),
        },
    )
)
class LogoutView(TokenBlacklistView):
    """Possession of a valid refresh token authorizes revoking that token only."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


@extend_schema_view(
    get=extend_schema(
        tags=["Authentication"],
        summary="Get your profile",
        description=(
            "Use Authorize with the access token returned by login. Do not paste a refresh token."
        ),
    )
)
class MeView(RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

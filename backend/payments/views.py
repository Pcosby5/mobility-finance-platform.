"""Payment endpoints.

HTTP surfaces:

* ``POST /api/v1/payments/initialize/`` — start a payment for a loan.
* ``GET  /api/v1/payments/{reference}/verify/`` — pull the latest provider state.
* ``POST /api/v1/webhooks/paystack/`` — Paystack callback.
* ``POST /api/v1/webhooks/momo/simulate/`` — development-only MoMo callback trigger.
* ``GET  /api/v1/payments/`` and ``/api/v1/payments/webhook-events/`` — read-only
  ledger and audit views for operations/admin.

Webhooks are unauthenticated by design (providers cannot hold JWTs) and are
protected by signature verification instead. The MoMo trigger additionally
requires a staff session so only the developer can resolve simulated charges.
"""

import hashlib
import hmac
import json

from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, BasePermission, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from users.models import User

from .models import Payment, WebhookEvent
from .providers import PaymentProviderError, get_provider
from .serializers import (
    MockMomoCallbackSerializer,
    PaymentInitializeSerializer,
    PaymentSerializer,
    WebhookEventSerializer,
)
from .services import handle_webhook, initialize_payment, refresh_payment_status


class PaymentPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.role in [User.Role.OPERATIONS, User.Role.ADMIN]:
            return True
        # Customers read the ledger and initialize payments on their own ACTIVE
        # loans; the service enforces loan ownership.
        return request.user.role == User.Role.CUSTOMER


class PaymentQuerysetMixin:
    permission_classes = [PaymentPermission]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        queryset = Payment.objects.select_related("loan", "customer")
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        if self.request.user.role in [User.Role.OPERATIONS, User.Role.ADMIN]:
            return queryset
        return queryset.filter(customer__user=self.request.user)


@extend_schema_view(get=extend_schema(tags=["Payments"], summary="List accessible payments"))
class PaymentListView(PaymentQuerysetMixin, ListAPIView):
    pass


@extend_schema_view(
    post=extend_schema(
        tags=["Payments"],
        summary="Initialize a payment for a loan",
        description=(
            "Creates a PENDING payment and a provider transaction. Pass the loan "
            "UUID as loan_id; amount defaults to the outstanding balance. Customers "
            "may only initialize on their own ACTIVE loans. Paystack responses "
            "include a checkout_url (test mode). Simulated MoMo charges resolve "
            "via the momo/simulate callback endpoint."
        ),
        request=PaymentInitializeSerializer,
        responses={201: PaymentSerializer},
    )
)
class PaymentInitializeView(APIView):
    permission_classes = [PaymentPermission]

    def post(self, request):
        serializer = PaymentInitializeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment, result = initialize_payment(
            actor=request.user,
            loan_id=serializer.validated_data["loan_id"].pk,
            provider_name=serializer.validated_data["provider"],
            amount=serializer.validated_data.get("amount"),
        )
        body = PaymentSerializer(payment).data
        body["checkout_url"] = result.get("checkout_url")
        return Response(body, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        tags=["Payments"],
        summary="Verify a payment against its provider",
        description=(
            "Re-fetches the transaction from the provider and applies the outcome "
            "under the same idempotent settlement rules as webhooks."
        ),
        responses={200: PaymentSerializer},
    )
)
class PaymentVerifyView(APIView):
    permission_classes = [PaymentPermission]

    def get(self, request, reference):
        queryset = Payment.objects.select_related("loan", "customer")
        if request.user.role not in [User.Role.OPERATIONS, User.Role.ADMIN]:
            queryset = queryset.filter(customer__user=request.user)
        payment = get_object_or_404(queryset, reference=reference)
        payment, note = refresh_payment_status(payment)
        # Surface the stored checkout link so a PENDING Paystack payment can
        # always be resumed from the app (covers pre-normalization payments,
        # which stored Paystack's original "authorization_url" key).
        initialization = (payment.raw_event or {}).get("initialization") or {}
        checkout_url = initialization.get("checkout_url") or initialization.get("authorization_url")
        return Response(
            PaymentSerializer(payment).data | {"detail": note, "checkout_url": checkout_url}
        )


class WebhookEventListView(ListAPIView):
    """Privileged audit trail; customers receive an empty list by design."""

    serializer_class = WebhookEventSerializer
    permission_classes = [PaymentPermission]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return WebhookEvent.objects.none()
        if self.request.user.role not in [User.Role.OPERATIONS, User.Role.ADMIN]:
            return WebhookEvent.objects.none()
        return WebhookEvent.objects.all()


@extend_schema_view(
    post=extend_schema(
        tags=["Webhooks"],
        summary="Simulate a MoMo callback (development only)",
        description=(
            "Staff-session only trigger that resolves a simulated charge and "
            "forwards a signed callback through the normal webhook pipeline."
        ),
        request=MockMomoCallbackSerializer,
        responses={200: None},
    )
)
class MockMomoWebhookView(APIView):
    """Development-only simulator trigger: POST {"reference": ..., "outcome": ...}.

    A staff session is required so only the developer can resolve simulated
    charges. The forwarded callback body is signed exactly like a real provider
    delivery, so the webhook pipeline exercised here is the production path.
    """

    # Sessions so the developer's Django admin login can trigger the simulator.
    # IsAdminUser still gates access; JWT tokens are deliberately not accepted.
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request):
        reference = str((request.data or {}).get("reference") or "")
        outcome = str((request.data or {}).get("outcome") or "success")
        if not reference:
            return Response({"detail": "reference is required."}, status=400)
        if outcome not in ("success", "failed"):
            return Response({"detail": "outcome must be success or failed."}, status=400)
        provider = get_provider("MOCK_MOMO")
        try:
            provider.resolve(reference, outcome)
        except PaymentProviderError:
            return Response({"detail": "Unknown simulated transaction."}, status=404)
        event_type = "charge.success" if outcome == "success" else "charge.failed"
        body = json.dumps({"event": event_type, "data": {"reference": reference}}).encode()
        signature = hmac.new(
            settings.MOCK_MOMO_WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        result = handle_webhook(provider_name="MOCK_MOMO", body=body, signature=signature)
        return Response(result, status=200)


@extend_schema_view(
    post=extend_schema(
        tags=["Webhooks"],
        summary="Paystack webhook receiver",
        description=(
            "Public endpoint. Authenticity is enforced by HMAC-SHA512 signature "
            "verification of the raw body; payloads are never trusted and the "
            "transaction is re-verified with Paystack before money moves."
        ),
        request=None,
        responses={200: None},
    )
)
class PaystackWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        signature = request.headers.get("x-paystack-signature", "")
        result = handle_webhook(provider_name="PAYSTACK", body=request.body, signature=signature)
        if not result.get("signature_valid", False):
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        outcome = result.get("outcome")
        if outcome == "retry":
            # Ask the provider to redeliver later.
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"detail": result.get("note", outcome or "received")})

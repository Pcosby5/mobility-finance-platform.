from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework.generics import GenericAPIView, ListAPIView, ListCreateAPIView, RetrieveAPIView
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response
from users.models import User

from .models import Loan
from .serializers import (
    InstallmentSerializer,
    LoanActionSerializer,
    LoanCreateSerializer,
    LoanSerializer,
)
from .services import create_loan, transition_loan


class LoanPermission(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role in [User.Role.OPERATIONS, User.Role.ADMIN]
            or (request.user.role == User.Role.CUSTOMER and request.method in SAFE_METHODS)
        )


class LoanQuerysetMixin:
    permission_classes = [LoanPermission]
    serializer_class = LoanSerializer

    def get_queryset(self):
        queryset = Loan.objects.all()
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        if self.request.user.role in [User.Role.OPERATIONS, User.Role.ADMIN]:
            return queryset
        return queryset.filter(customer__user=self.request.user)


@extend_schema_view(
    get=extend_schema(tags=["Loans"], summary="List accessible loans"),
    post=extend_schema(
        tags=["Loans"],
        summary="Create a pending demo loan (operations/admin)",
        description=(
            "Use actual UUIDs from Customers, Vehicles and Credit. The assessment must be "
            "approved and match the current profile. Use a first repayment date in the next "
            "90 days. Interest is flat simple interest; amounts and schedule are server-calculated."
        ),
        request=LoanCreateSerializer,
        responses={201: LoanSerializer},
    ),
)
class LoanListCreateView(LoanQuerysetMixin, ListCreateAPIView):
    def create(self, request, *args, **kwargs):
        serializer = LoanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        loan = create_loan(actor=request.user, **serializer.validated_data)
        return Response(LoanSerializer(loan).data, status=201)


@extend_schema_view(get=extend_schema(tags=["Loans"], summary="Get an accessible loan"))
class LoanDetailView(LoanQuerysetMixin, RetrieveAPIView):
    pass


@extend_schema_view(get=extend_schema(tags=["Loans"], summary="List scheduled installments"))
class LoanScheduleView(LoanQuerysetMixin, ListAPIView):
    serializer_class = InstallmentSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            from .models import RepaymentInstallment

            return RepaymentInstallment.objects.none()
        loan = get_object_or_404(super().get_queryset(), pk=self.kwargs["pk"])
        return loan.installments.all()


class LoanActionView(LoanQuerysetMixin, GenericAPIView):
    serializer_class = LoanActionSerializer
    action = None

    def post(self, request, *args, **kwargs):
        loan = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = transition_loan(loan_id=loan.pk, action=self.action)
        return Response(LoanSerializer(updated).data)


@extend_schema_view(
    post=extend_schema(
        tags=["Loans"],
        summary="Activate a pending loan (operations/admin)",
        description="Rechecks eligibility and affordability, then sets the demo balance. Send {}.",
        responses={200: LoanSerializer},
        examples=[OpenApiExample("Activate", value={}, request_only=True)],
    )
)
class LoanActivateView(LoanActionView):
    action = "activate"


@extend_schema_view(
    post=extend_schema(
        tags=["Loans"],
        summary="Cancel a pending loan (operations/admin)",
        description=(
            "Only a pending loan can be cancelled. Its schedule is retained for reference. Send {}."
        ),
        responses={200: LoanSerializer},
        examples=[OpenApiExample("Cancel", value={}, request_only=True)],
    )
)
class LoanCancelView(LoanActionView):
    action = "cancel"

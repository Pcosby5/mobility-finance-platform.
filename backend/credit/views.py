from customers.models import CustomerProfile
from customers.permissions import CustomerAccessPermission, can_manage_customers
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework.generics import ListCreateAPIView, RetrieveAPIView
from rest_framework.response import Response

from .models import CreditAssessment
from .serializers import AssessmentRequestSerializer, CreditAssessmentSerializer
from .services import assess_customer


@extend_schema_view(
    get=extend_schema(tags=["Credit"], summary="List a customer's credit assessments"),
    post=extend_schema(
        tags=["Credit"],
        summary="Run a demo credit assessment",
        description=(
            "Scores the saved customer profile and stores a versioned snapshot. "
            "Send {}. APPROVED is a demo screening result, not approval of a loan. "
            "Each request creates a new assessment; previous results remain unchanged."
        ),
        request=AssessmentRequestSerializer,
        responses={201: CreditAssessmentSerializer},
        examples=[OpenApiExample("Use saved profile", value={}, request_only=True)],
    ),
)
class CustomerAssessmentView(ListCreateAPIView):
    serializer_class = CreditAssessmentSerializer
    permission_classes = [CustomerAccessPermission]

    def get_customer(self):
        queryset = CustomerProfile.objects.all()
        if not can_manage_customers(self.request.user):
            queryset = queryset.filter(user=self.request.user)
        customer = get_object_or_404(queryset, pk=self.kwargs["customer_id"])
        self.check_object_permissions(self.request, customer)
        return customer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CreditAssessment.objects.none()
        return CreditAssessment.objects.filter(customer=self.get_customer())

    def create(self, request, *args, **kwargs):
        customer = self.get_customer()
        payload = AssessmentRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        assessment = assess_customer(customer_id=customer.pk, actor=request.user)
        return Response(CreditAssessmentSerializer(assessment).data, status=201)


@extend_schema_view(
    get=extend_schema(tags=["Credit"], summary="Retrieve a saved credit assessment")
)
class CreditAssessmentDetailView(RetrieveAPIView):
    serializer_class = CreditAssessmentSerializer

    def get_queryset(self):
        queryset = CreditAssessment.objects.all()
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        if not can_manage_customers(self.request.user):
            queryset = queryset.filter(customer__user=self.request.user)
        return queryset

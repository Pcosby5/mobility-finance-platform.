from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView

from .models import CustomerProfile
from .permissions import CustomerAccessPermission, can_manage_customers
from .serializers import CustomerProfileSerializer


class CustomerQuerysetMixin:
    serializer_class = CustomerProfileSerializer
    permission_classes = [CustomerAccessPermission]

    def get_queryset(self):
        queryset = CustomerProfile.objects.select_related("user").all()
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        if can_manage_customers(self.request.user):
            return queryset
        return queryset.filter(user=self.request.user)


@extend_schema_view(
    get=extend_schema(
        tags=["Customers"],
        summary="List accessible customer profiles",
        description="Customers see only their own profile. ADMIN and OPERATIONS see all profiles.",
    ),
    post=extend_schema(
        tags=["Customers"],
        summary="Create a customer profile",
        description=(
            "Customers omit user to create their own profile. ADMIN and OPERATIONS must supply "
            "an existing customer account UUID. "
            "Amounts are self-reported demo inputs in one currency."
        ),
        examples=[
            OpenApiExample(
                "My demo profile",
                request_only=True,
                value={
                    "full_name": "Demo Customer",
                    "phone": "+233201234567",
                    "employment_status": "EMPLOYED",
                    "employment_duration_months": 24,
                    "currency": "GHS",
                    "monthly_income": "6500.00",
                    "existing_debt": "2000.00",
                    "monthly_debt_repayment": "250.00",
                },
            )
        ],
    ),
)
class CustomerListCreateView(CustomerQuerysetMixin, ListCreateAPIView):
    pass


@extend_schema_view(
    get=extend_schema(tags=["Customers"], summary="Get an accessible customer profile"),
    patch=extend_schema(
        tags=["Customers"],
        summary="Update a customer profile",
        description="Ownership is immutable. Other customers' profiles return 404.",
    ),
)
class CustomerDetailView(CustomerQuerysetMixin, RetrieveUpdateAPIView):
    http_method_names = ["get", "patch", "head", "options"]

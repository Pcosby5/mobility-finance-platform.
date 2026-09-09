from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from users.models import User

from .models import CustomerProfile
from .permissions import can_manage_customers


class CustomerProfileSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.CUSTOMER, is_active=True),
        required=False,
        pk_field=serializers.UUIDField(),
    )
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = CustomerProfile
        fields = (
            "id",
            "user",
            "full_name",
            "email",
            "phone",
            "employment_status",
            "employment_duration_months",
            "currency",
            "monthly_income",
            "existing_debt",
            "monthly_debt_repayment",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        writable = {name for name, field in self.fields.items() if not field.read_only}
        rejected = set(self.initial_data) - writable
        if rejected:
            raise serializers.ValidationError(
                {name: "This field cannot be set." for name in sorted(rejected)}
            )
        if self.instance:
            if "user" in attrs:
                raise serializers.ValidationError({"user": "Profile ownership cannot be changed."})
            return attrs

        actor = self.context["request"].user
        if can_manage_customers(actor):
            if "user" not in attrs:
                raise serializers.ValidationError({"user": "Select a customer account."})
        else:
            if "user" in attrs and attrs["user"].pk != actor.pk:
                raise PermissionDenied("You can only create your own customer profile.")
            attrs["user"] = actor
        if CustomerProfile.objects.filter(user=attrs["user"]).exists():
            raise serializers.ValidationError({"user": "This customer already has a profile."})
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError as exc:
            # The unique user relationship also protects concurrent duplicate creation.
            if CustomerProfile.objects.filter(user=validated_data["user"]).exists():
                raise serializers.ValidationError(
                    {"user": "This customer already has a profile."}
                ) from exc
            raise

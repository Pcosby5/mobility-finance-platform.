from datetime import timedelta
from decimal import Decimal

from credit.models import CreditAssessment
from customers.models import CustomerProfile
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from users.models import User
from vehicles.models import Vehicle

from .calculations import calculate_terms
from .models import Loan, RepaymentInstallment
from .policy import (
    MAX_ASSESSMENT_AGE_DAYS,
    MAX_COMBINED_DEBT_TO_INCOME,
    MAX_FIRST_REPAYMENT_DAYS,
    OPEN_STATUSES,
    POLICY_VERSION,
)


def check_eligibility(customer, vehicle, assessment, first_due_date):
    if not customer.user.is_active or customer.user.role != User.Role.CUSTOMER:
        raise ValidationError({"customer": "An active customer account is required."})
    if vehicle.customer_id != customer.pk:
        raise ValidationError(
            {"vehicle": "Assign the vehicle to this customer before creating a loan."}
        )
    if vehicle.status != Vehicle.Status.ACTIVE:
        raise ValidationError({"vehicle": "The vehicle must be ACTIVE."})
    if (
        assessment.customer_id != customer.pk
        or assessment.decision != CreditAssessment.Decision.APPROVED
    ):
        raise ValidationError(
            {"credit_assessment": "An approved assessment for this customer is required."}
        )
    if assessment.created_at < timezone.now() - timedelta(days=MAX_ASSESSMENT_AGE_DAYS):
        raise ValidationError(
            {"credit_assessment": "Assessment is older than 30 days; run a new one."}
        )
    snapshot = assessment.input_snapshot
    current = {
        "currency": customer.currency,
        "employment_status": customer.employment_status,
        "employment_duration_months": customer.employment_duration_months,
        "monthly_income": str(customer.monthly_income),
        "existing_debt": str(customer.existing_debt),
        "monthly_debt_repayment": str(customer.monthly_debt_repayment),
    }
    if any(snapshot.get(key) != value for key, value in current.items()):
        raise ValidationError(
            {"credit_assessment": "Financial inputs changed; run a new assessment."}
        )
    today = timezone.localdate()
    if not today < first_due_date <= today + timedelta(days=MAX_FIRST_REPAYMENT_DAYS):
        raise ValidationError({"first_repayment_date": "Choose a date within the next 90 days."})


def check_affordability(customer, terms, exclude_loan=None):
    existing = Loan.objects.filter(customer=customer, status__in=OPEN_STATUSES)
    if exclude_loan:
        existing = existing.exclude(pk=exclude_loan)
    obligations = Decimal("0")
    for loan in existing:
        if loan.currency != customer.currency:
            raise ValidationError(
                {"customer": "Open loans use a different currency; review is required."}
            )
        obligations += max(loan.monthly_repayment, loan.final_repayment)
    combined = (
        customer.monthly_debt_repayment
        + obligations
        + max(terms["monthly_repayment"], terms["final_repayment"])
    )
    if (
        customer.monthly_income <= 0
        or combined > customer.monthly_income * MAX_COMBINED_DEBT_TO_INCOME
    ):
        raise ValidationError(
            {"principal_amount": "Combined monthly repayments exceed 60% of reported income."}
        )
    return combined


@transaction.atomic
def create_loan(
    *,
    actor,
    customer,
    vehicle,
    credit_assessment,
    principal_amount,
    annual_interest_rate,
    duration_months,
    first_repayment_date,
):
    # Lock ordering is customer -> vehicle -> loan throughout origination and lifecycle actions.
    customer = CustomerProfile.objects.select_for_update().get(pk=customer.pk)
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
    assessment = CreditAssessment.objects.get(pk=credit_assessment.pk)
    check_eligibility(customer, vehicle, assessment, first_repayment_date)
    if Loan.objects.filter(vehicle=vehicle, status__in=OPEN_STATUSES).exists():
        raise ValidationError({"vehicle": "This vehicle already has an open loan."})
    try:
        terms = calculate_terms(
            principal=principal_amount,
            annual_rate=annual_interest_rate,
            months=duration_months,
            first_due_date=first_repayment_date,
        )
    except ValueError as exc:
        raise ValidationError({"principal_amount": str(exc)}) from exc
    combined = check_affordability(customer, terms)
    rows = terms.pop("installments")
    loan = Loan.objects.create(
        customer=customer,
        vehicle=vehicle,
        credit_assessment=assessment,
        created_by=actor,
        currency=customer.currency,
        principal_amount=principal_amount,
        annual_interest_rate=annual_interest_rate,
        duration_months=duration_months,
        first_repayment_date=first_repayment_date,
        policy_version=POLICY_VERSION,
        origination_snapshot={
            "interest_method": "flat_simple",
            "rounding": "ROUND_HALF_UP_interest_then_final_residual",
            "maximum_combined_debt_to_income": str(MAX_COMBINED_DEBT_TO_INCOME),
            "maximum_assessment_age_days": MAX_ASSESSMENT_AGE_DAYS,
            "income": str(customer.monthly_income),
            "external_monthly_debt_repayment": str(customer.monthly_debt_repayment),
            "combined_monthly_obligation": str(combined),
            "vehicle_registration": vehicle.registration_number,
            "vehicle_vin": vehicle.vin,
        },
        **terms,
    )
    RepaymentInstallment.objects.bulk_create(
        [RepaymentInstallment(loan=loan, **row) for row in rows]
    )
    return loan


@transaction.atomic
def transition_loan(*, loan_id, action):
    references = Loan.objects.values("customer_id", "vehicle_id").get(pk=loan_id)
    customer = CustomerProfile.objects.select_for_update().get(pk=references["customer_id"])
    vehicle = Vehicle.objects.select_for_update().get(pk=references["vehicle_id"])
    loan = Loan.objects.select_for_update().get(pk=loan_id)
    if loan.status != Loan.Status.PENDING:
        raise ValidationError({"status": "Only PENDING loans can be activated or cancelled."})
    if action == "activate":
        check_eligibility(customer, vehicle, loan.credit_assessment, loan.first_repayment_date)
        check_affordability(
            customer,
            {"monthly_repayment": loan.monthly_repayment, "final_repayment": loan.final_repayment},
            exclude_loan=loan.pk,
        )
        loan.status = Loan.Status.ACTIVE
        loan.outstanding_balance = loan.total_repayable
        loan.activated_at = timezone.now()
    elif action == "cancel":
        loan.status = Loan.Status.CANCELLED
        loan.cancelled_at = timezone.now()
    else:
        raise ValueError("Unknown loan action")
    loan.save()
    return loan

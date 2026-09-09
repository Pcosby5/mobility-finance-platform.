import json
from dataclasses import asdict

from customers.models import CustomerProfile
from django.db import transaction

from .models import CreditAssessment
from .rules import RULES
from .scoring import CreditInputs, score_customer


@transaction.atomic
def assess_customer(*, customer_id, actor) -> CreditAssessment:
    # A row lock gives this assessment a consistent profile snapshot during concurrent edits.
    customer = CustomerProfile.objects.select_for_update().get(pk=customer_id)
    inputs = CreditInputs(
        currency=customer.currency,
        monthly_income=customer.monthly_income,
        existing_debt=customer.existing_debt,
        monthly_debt_repayment=customer.monthly_debt_repayment,
        employment_status=customer.employment_status,
        employment_duration_months=customer.employment_duration_months,
    )
    snapshot = json.loads(json.dumps(asdict(inputs), default=str))
    snapshot["profile_updated_at"] = customer.updated_at.isoformat()
    snapshot["data_source"] = "self_reported_demo"
    snapshot["repayment_history"] = None
    snapshot["transaction_history"] = None
    return CreditAssessment.objects.create(
        customer=customer,
        created_by=actor,
        rules_version=RULES.version,
        rules_snapshot=json.loads(json.dumps(asdict(RULES), default=str)),
        input_snapshot=snapshot,
        **score_customer(inputs),
    )

"""Flat simple interest for this demo, not amortization or an APR calculation."""

from calendar import monthrange
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def monthly_due_date(first_date: date, offset: int) -> date:
    month_index = first_date.year * 12 + first_date.month - 1 + offset
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, min(first_date.day, monthrange(year, month)[1]))


def calculate_terms(*, principal: Decimal, annual_rate: Decimal, months: int, first_due_date: date):
    if months < 1 or principal < months * CENT or annual_rate < 0:
        raise ValueError(
            "Principal must cover at least one cent per installment; term and rate must be valid."
        )
    interest = (principal * annual_rate / 100 * months / 12).quantize(CENT, ROUND_HALF_UP)
    principal_part = (principal / months).quantize(CENT, ROUND_DOWN)
    interest_part = (interest / months).quantize(CENT, ROUND_DOWN)
    installments = []
    for index in range(months):
        final = index == months - 1
        principal_due = principal - principal_part * (months - 1) if final else principal_part
        interest_due = interest - interest_part * (months - 1) if final else interest_part
        installments.append(
            {
                "number": index + 1,
                "due_date": monthly_due_date(first_due_date, index),
                "principal_due": principal_due,
                "interest_due": interest_due,
                "amount_due": principal_due + interest_due,
            }
        )
    return {
        "total_interest": interest,
        "total_repayable": principal + interest,
        "monthly_repayment": installments[0]["amount_due"],
        "final_repayment": installments[-1]["amount_due"],
        "installments": installments,
    }

"""Pure scoring logic: no database writes, network calls or hidden historical data."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .rules import RULES, CreditRules


@dataclass(frozen=True)
class CreditInputs:
    currency: str
    monthly_income: Decimal
    existing_debt: Decimal
    monthly_debt_repayment: Decimal
    employment_status: str
    employment_duration_months: int


def score_customer(inputs: CreditInputs, rules: CreditRules = RULES) -> dict:
    factors = [{"code": "BASE_SCORE", "points": rules.base_score, "reason": "Demo starting score."}]

    def factor(code, points, reason):
        factors.append({"code": code, "points": points, "reason": reason})

    def ratio_points(amount, bands):
        # Compare without rounding the ratio; rounding near a cutoff must not change the decision.
        return next(
            (points for limit, points in bands if amount <= inputs.monthly_income * limit), 0
        )

    def display_ratio(amount):
        return str((amount / inputs.monthly_income).quantize(Decimal("0.0001"), ROUND_HALF_UP))

    if inputs.monthly_income < 0 or inputs.existing_debt < 0 or inputs.monthly_debt_repayment < 0:
        raise ValueError("Credit inputs cannot contain negative monetary amounts.")
    if inputs.employment_duration_months < 0:
        raise ValueError("Employment duration cannot be negative.")

    ratios = {"debt_to_income": None, "debt_balance_to_income": None}
    if inputs.monthly_income == 0:
        factor(
            "NO_INCOME",
            0,
            "No income reported; ratios cannot be calculated. Demo decision rejected.",
        )
    else:
        factor("INCOME_PRESENT", rules.income_points, "Positive self-reported monthly income.")
        ratios = {
            "debt_to_income": display_ratio(inputs.monthly_debt_repayment),
            "debt_balance_to_income": display_ratio(inputs.existing_debt),
        }
        factor(
            "DEBT_TO_INCOME",
            ratio_points(inputs.monthly_debt_repayment, rules.debt_to_income_bands),
            "Monthly debt payments divided by monthly income: " + ratios["debt_to_income"],
        )
        factor(
            "DEBT_BALANCE",
            ratio_points(inputs.existing_debt, rules.debt_balance_bands),
            "Outstanding debt divided by monthly income: " + ratios["debt_balance_to_income"],
        )
        employed = inputs.employment_status in dict(rules.employment_points)
        factor(
            "EMPLOYMENT_STATUS",
            dict(rules.employment_points).get(inputs.employment_status, 0),
            f"Reported employment status: {inputs.employment_status}.",
        )
        duration_points = (
            next(
                (
                    points
                    for months, points in rules.employment_duration_bands
                    if inputs.employment_duration_months >= months
                ),
                0,
            )
            if employed
            else 0
        )
        factor(
            "EMPLOYMENT_DURATION",
            duration_points,
            "Current employment duration is scored only for employed or self-employed customers.",
        )

    score = min(rules.maximum_score, sum(item["points"] for item in factors))
    if score >= rules.low_risk_minimum:
        risk_band, decision = "LOW", "APPROVED"
    elif score >= rules.medium_risk_minimum:
        risk_band, decision = "MEDIUM", "REVIEW"
    else:
        risk_band, decision = "HIGH", "REJECTED"

    if inputs.monthly_income == 0 or (
        inputs.monthly_debt_repayment
        > inputs.monthly_income * rules.maximum_approvable_debt_to_income
    ):
        risk_band, decision = "HIGH", "REJECTED"
        factor(
            "AFFORDABILITY_STOP", 0, "Zero income or monthly debt payments exceed the demo limit."
        )
    elif inputs.existing_debt > 0 and inputs.monthly_debt_repayment == 0:
        if decision == "APPROVED":
            decision = "REVIEW"
        factor(
            "DEBT_PAYMENT_MISSING",
            0,
            "Debt exists but no monthly payment is reported; review needed.",
        )

    factor(
        "REPAYMENT_HISTORY_UNAVAILABLE",
        0,
        "Loan repayment history is not available yet; not scored.",
    )
    factor(
        "TRANSACTION_HISTORY_UNAVAILABLE",
        0,
        "Transaction behaviour is not available yet; not scored.",
    )
    return {
        "score": score,
        "risk_band": risk_band,
        "decision": decision,
        "factors": factors,
        "ratios": ratios,
    }

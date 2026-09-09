"""Versioned demo policy. Change the version whenever scoring behaviour changes."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CreditRules:
    version: str = "demo-v1"
    base_score: int = 300
    maximum_score: int = 850
    income_points: int = 100
    # Ordered upper bounds, inclusive. Ratios have no currency units.
    debt_to_income_bands: tuple = (
        (Decimal("0.20"), 200),
        (Decimal("0.40"), 125),
        (Decimal("0.60"), 50),
    )
    debt_balance_bands: tuple = ((Decimal("1"), 100), (Decimal("3"), 50))
    employment_points: tuple = (("EMPLOYED", 75), ("SELF_EMPLOYED", 75))
    # Ordered lower bounds, inclusive; longest duration first.
    employment_duration_bands: tuple = ((24, 75), (6, 40))
    low_risk_minimum: int = 700
    medium_risk_minimum: int = 550
    maximum_approvable_debt_to_income: Decimal = Decimal("0.60")


RULES = CreditRules()

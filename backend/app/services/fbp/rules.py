"""Explicit demo budget rule; annual base salary is not CTC."""
from decimal import Decimal, ROUND_HALF_UP
DEFAULT_BUDGET_RATE = Decimal('0.1000')
RULE_VERSION = 'DEMO_ANNUAL_FBP_V1'


def budget(annual_base_salary, rate):
    return (annual_base_salary * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

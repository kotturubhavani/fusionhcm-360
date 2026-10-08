"""Transparent synthetic monthly rules; not statutory payroll or tax advice."""
from decimal import Decimal, ROUND_HALF_UP

MONTHS_PER_YEAR = Decimal('12')
CENT = Decimal('0.01')
PAID_STATUSES = ('ACTIVE', 'ON_LEAVE')
RULE_VERSION = 'DEMO_MONTHLY_V1'


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def snapshot(definition):
    return dict(version=RULE_VERSION, months_per_year='12', rounding='ROUND_HALF_UP',
                paid_statuses=list(PAID_STATUSES), proration='inclusive calendar days',
                retirement_rate=str(definition.retirement_rate), withholding_rate=str(definition.withholding_rate),
                standard_allowance=str(definition.standard_allowance), currency=definition.currency)


def calculate(base, allowance, retirement_rate, withholding_rate):
    base, allowance = money(base), money(allowance)
    gross = base + allowance
    lines = [('EARNING', 'BASE_PAY', 'Basic Pay', base)]
    if allowance:
        lines.append(('EARNING', 'STANDARD_ALLOWANCE', 'Standard Allowance', allowance))
    # Demo retirement uses base earnings; demo withholding uses gross earnings.
    lines += [('DEDUCTION', 'DEMO_RETIREMENT', 'Retirement Contribution', money(base * retirement_rate)),
              ('DEDUCTION', 'DEMO_WITHHOLDING', 'Income Tax Withholding', money(gross * withholding_rate))]
    deductions = sum((line[3] for line in lines if line[0] == 'DEDUCTION'), Decimal('0.00'))
    return lines, gross, deductions, gross - deductions

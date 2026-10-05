"""Payroll contracts: money and rates are decimal strings, never JSON floats."""
from calendar import monthrange
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator
from app.schemas.core_hr import Contract, ReadRecord, Code, Label, Country, Currency, Day, AssignmentCompensationCreate

Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)]
Rate = Annotated[Decimal, Field(ge=0, le=1, max_digits=5, decimal_places=4, allow_inf_nan=False)]


class DefinitionCreate(Contract):
    code: Code
    name: Label
    legal_employer_id: UUID
    country_code: Country
    currency: Currency
    frequency: Literal['MONTHLY'] = 'MONTHLY'
    is_active: StrictBool = True
    retirement_rate: Rate = Decimal('0.0500')
    withholding_rate: Rate = Decimal('0.1000')
    standard_allowance: Money = Decimal('0.00')
    _decimal = field_validator('retirement_rate', 'withholding_rate', 'standard_allowance', mode='before')(AssignmentCompensationCreate.exact_salary.__func__)

    @model_validator(mode='after')
    def rates(self):
        if self.retirement_rate + self.withholding_rate > 1:
            raise ValueError('Combined demo deduction rates cannot exceed 1')
        return self


class DefinitionRead(DefinitionCreate, ReadRecord):
    pass


class PeriodCreate(Contract):
    payroll_definition_id: UUID
    period_name: Annotated[str, Field(min_length=1, max_length=100)]
    period_start: Day
    period_end: Day
    payment_date: Day

    @model_validator(mode='after')
    def dates(self):
        self.period_name = self.period_name.strip()
        if not self.period_name:
            raise ValueError('Period name is required')
        last = self.period_start.replace(day=monthrange(self.period_start.year, self.period_start.month)[1])
        if self.period_start.day != 1 or self.period_end != last:
            raise ValueError('Use one complete calendar month')
        if self.payment_date < self.period_end:
            raise ValueError('Payment date cannot precede period end')
        return self


class PeriodRead(PeriodCreate, ReadRecord):
    status: str


class RunRead(ReadRecord):
    pay_period_id: UUID
    run_number: int
    status: str
    started_at: AwareDatetime
    completed_at: AwareDatetime | None
    initiated_by_user_id: UUID | None
    rules_snapshot: dict
    failure_reason: str | None
    excluded_assignment_count: int
    unpaid_day_count: int


class ResultRead(ReadRecord):
    payroll_run_id: UUID
    person_id: UUID
    work_relationship_id: UUID
    assignment_id: UUID
    person_number: str
    worker_name: str
    assignment_number: str
    gross_pay: Decimal
    total_deductions: Decimal
    net_pay: Decimal
    currency: str
    eligible_days: int
    period_days: int
    calculation_snapshot: list[dict]


class LineRead(ReadRecord):
    payroll_result_id: UUID
    line_type: str
    code: str
    name: str
    amount: Decimal


class ResultDetail(Contract):
    result: ResultRead
    lines: list[LineRead]
    period: PeriodRead
    definition_name: str


class RunDetail(Contract):
    run: RunRead
    period: PeriodRead
    definition_name: str
    currency: str
    result_count: int
    gross_pay: Decimal
    total_deductions: Decimal
    net_pay: Decimal

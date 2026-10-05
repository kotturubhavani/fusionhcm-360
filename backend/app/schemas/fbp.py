"""Strict contracts for synthetic annual benefits elections."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator
from app.schemas.core_hr import Contract, ReadRecord, Code, Label, Currency, Day, AssignmentCompensationCreate, patch_contract
from app.services.fbp.rules import DEFAULT_BUDGET_RATE

Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)]
Rate = Annotated[Decimal, Field(gt=0, le=1, max_digits=5, decimal_places=4, allow_inf_nan=False)]


class PlanCreate(Contract):
    code: Code
    name: Label
    legal_employer_id: UUID
    plan_year: Annotated[int, Field(strict=True, ge=1900, le=9998)]
    effective_from: Day
    effective_to: Day
    currency: Currency
    budget_rate: Rate = DEFAULT_BUDGET_RATE
    is_active: StrictBool = True
    _decimal = field_validator('budget_rate', mode='before')(AssignmentCompensationCreate.exact_salary.__func__)

    @model_validator(mode='after')
    def dates(self):
        if self.effective_from != date(self.plan_year,1,1) or self.effective_to != date(self.plan_year,12,31):
            raise ValueError('An annual plan must cover January 1 through December 31 of its plan year')
        return self


PlanUpdate = patch_contract('PlanUpdate', PlanCreate)


class PlanRead(PlanCreate, ReadRecord):
    status: str
    budgets_generated_at: AwareDatetime | None


class ComponentCreate(Contract):
    code: Code
    name: Label
    description: Annotated[str, Field(strict=True, max_length=2000)] | None = None
    component_type: Literal['ALLOWANCE','BENEFIT','REIMBURSEMENT']
    min_amount: Money = Decimal('0.00')
    max_amount: Money
    default_amount: Money = Decimal('0.00')
    display_order: Annotated[int, Field(strict=True, ge=0, le=10000)] = 0
    is_active: StrictBool = True
    _decimal = field_validator('min_amount','max_amount','default_amount', mode='before')(AssignmentCompensationCreate.exact_salary.__func__)

    @model_validator(mode='after')
    def limits(self):
        if self.max_amount < self.min_amount or self.default_amount > self.max_amount or (self.default_amount and self.default_amount < self.min_amount):
            raise ValueError('Component limits/default are inconsistent; zero means not selected')
        return self


ComponentUpdate = patch_contract('ComponentUpdate', ComponentCreate)


class ComponentRead(ComponentCreate, ReadRecord):
    plan_id: UUID


class ElectionInput(Contract):
    component_id: UUID
    amount: Money
    _decimal = field_validator('amount', mode='before')(AssignmentCompensationCreate.exact_salary.__func__)


class BudgetAction(Contract):
    worker_budget_id: UUID
    expected_revision: Annotated[int, Field(strict=True, ge=0)]


class ElectionsSave(BudgetAction):
    elections: Annotated[list[ElectionInput], Field(max_length=100)]

    @model_validator(mode='after')
    def distinct(self):
        if len({e.component_id for e in self.elections}) != len(self.elections):
            raise ValueError('Each component may appear only once')
        return self


class ElectionRead(ElectionInput, ReadRecord):
    worker_budget_id: UUID
    plan_id: UUID


class BudgetRead(ReadRecord):
    plan_id: UUID
    person_id: UUID
    assignment_id: UUID
    compensation_id: UUID
    person_number: str
    worker_name: str
    assignment_number: str
    annual_base_salary: Decimal
    budget_rate: Decimal
    eligible_budget: Decimal
    currency: str
    status: str
    revision: int
    submitted_at: AwareDatetime | None
    finalized_at: AwareDatetime | None
    allocated: Decimal
    remaining: Decimal
    elections: list[ElectionRead]


class PlanView(Contract):
    plan: PlanRead
    components: list[ComponentRead]
    budgets: list[BudgetRead]


class Summary(Contract):
    workers: int
    budgets: int
    open: int
    submitted: int
    finalized: int
    eligible_budget: Decimal
    allocated: Decimal
    remaining: Decimal
    currency: str

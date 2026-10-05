"""Synthetic annual benefits plans and immutable finalized allocations."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.worker import WorkerTimestamps


def identifier():
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())


def reference(table, name):
    return mapped_column(PG_UUID(as_uuid=True), ForeignKey(table+'.id', name=name, ondelete='RESTRICT'), nullable=False)


class FBPPlan(WorkerTimestamps, Base):
    __tablename__ = 'fbp_plans'
    __table_args__ = (
        UniqueConstraint('code', name='uq_fbp_plans_code'),
        UniqueConstraint('legal_employer_id', 'plan_year', name='uq_fbp_plans_employer_year'),
        CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code)) AND name ~ '[^[:space:]]'", name='ck_fbp_plans_labels'),
        CheckConstraint('plan_year BETWEEN 1900 AND 9998 AND effective_from = make_date(plan_year,1,1) AND effective_to = make_date(plan_year,12,31)', name='ck_fbp_plans_year_dates'),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name='ck_fbp_plans_currency'),
        CheckConstraint("status IN ('DRAFT','OPEN','CLOSED')", name='ck_fbp_plans_status'),
        CheckConstraint('budget_rate > 0 AND budget_rate <= 1', name='ck_fbp_plans_rate'),
    )
    id: Mapped[UUID] = identifier()
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(150))
    legal_employer_id: Mapped[UUID] = reference('legal_employers','fk_fbp_plans_employer')
    plan_year: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    budget_rate: Mapped[Decimal] = mapped_column(Numeric(5,4))
    status: Mapped[str] = mapped_column(String(10), server_default='DRAFT')
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text('true'))
    budgets_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FBPComponent(WorkerTimestamps, Base):
    __tablename__ = 'fbp_components'
    __table_args__ = (
        UniqueConstraint('plan_id','code', name='uq_fbp_components_plan_code'),
        UniqueConstraint('id','plan_id', name='uq_fbp_components_id_plan'),
        CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code)) AND name ~ '[^[:space:]]'", name='ck_fbp_components_labels'),
        CheckConstraint("component_type IN ('ALLOWANCE','BENEFIT','REIMBURSEMENT')", name='ck_fbp_components_type'),
        CheckConstraint('min_amount >= 0 AND max_amount >= min_amount AND default_amount >= 0 AND default_amount <= max_amount AND (default_amount = 0 OR default_amount >= min_amount)', name='ck_fbp_components_limits'),
        CheckConstraint('display_order >= 0', name='ck_fbp_components_order'),
    )
    id: Mapped[UUID] = identifier()
    plan_id: Mapped[UUID] = reference('fbp_plans','fk_fbp_components_plan')
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(String(2000))
    component_type: Mapped[str] = mapped_column(String(20))
    min_amount: Mapped[Decimal] = mapped_column(Numeric(14,2))
    max_amount: Mapped[Decimal] = mapped_column(Numeric(14,2))
    default_amount: Mapped[Decimal] = mapped_column(Numeric(14,2))
    display_order: Mapped[int] = mapped_column(Integer, server_default='0')
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text('true'))


class FBPWorkerBudget(WorkerTimestamps, Base):
    __tablename__ = 'fbp_worker_budgets'
    __table_args__ = (
        UniqueConstraint('plan_id','assignment_id', name='uq_fbp_budgets_plan_assignment'),
        UniqueConstraint('id','plan_id', name='uq_fbp_budgets_id_plan'),
        Index('ix_fbp_budgets_person_plan','person_id','plan_id'),
        CheckConstraint('eligible_budget > 0 AND annual_base_salary > 0 AND budget_rate > 0 AND budget_rate <= 1', name='ck_fbp_budgets_amounts'),
        CheckConstraint("currency ~ '^[A-Z]{3}$' AND status IN ('OPEN','SUBMITTED','FINALIZED')", name='ck_fbp_budgets_currency_status'),
        CheckConstraint('revision >= 0', name='ck_fbp_budgets_revision'),
    )
    id: Mapped[UUID] = identifier()
    plan_id: Mapped[UUID] = reference('fbp_plans','fk_fbp_budgets_plan')
    person_id: Mapped[UUID] = reference('persons','fk_fbp_budgets_person')
    assignment_id: Mapped[UUID] = reference('assignments','fk_fbp_budgets_assignment')
    compensation_id: Mapped[UUID] = reference('assignment_compensation','fk_fbp_budgets_compensation')
    person_number: Mapped[str] = mapped_column(String(30))
    worker_name: Mapped[str] = mapped_column(String(201))
    assignment_number: Mapped[str] = mapped_column(String(30))
    annual_base_salary: Mapped[Decimal] = mapped_column(Numeric(14,2))
    budget_rate: Mapped[Decimal] = mapped_column(Numeric(5,4))
    eligible_budget: Mapped[Decimal] = mapped_column(Numeric(14,2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(10), server_default='OPEN')
    revision: Mapped[int] = mapped_column(Integer, server_default='0')
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FBPElection(WorkerTimestamps, Base):
    __tablename__ = 'fbp_elections'
    __table_args__ = (
        UniqueConstraint('worker_budget_id','component_id', name='uq_fbp_elections_budget_component'),
        ForeignKeyConstraint(['worker_budget_id','plan_id'],['fbp_worker_budgets.id','fbp_worker_budgets.plan_id'], name='fk_fbp_elections_budget_plan', ondelete='RESTRICT'),
        ForeignKeyConstraint(['component_id','plan_id'],['fbp_components.id','fbp_components.plan_id'], name='fk_fbp_elections_component_plan', ondelete='RESTRICT'),
        Index('ix_fbp_elections_component_plan','component_id','plan_id'),
        CheckConstraint('amount >= 0', name='ck_fbp_elections_amount'),
    )
    id: Mapped[UUID] = identifier()
    plan_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    worker_budget_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    component_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(14,2))

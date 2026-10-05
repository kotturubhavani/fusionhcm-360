"""Payroll simulation records. Completed runs are immutable through the API."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.worker import WorkerTimestamps


def identifier():
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())


def reference(table, name, nullable=False, ondelete='RESTRICT'):
    return mapped_column(PG_UUID(as_uuid=True), ForeignKey(table + '.id', name=name, ondelete=ondelete), nullable=nullable)


class PayrollDefinition(WorkerTimestamps, Base):
    __tablename__ = 'payroll_definitions'
    __table_args__ = (
        UniqueConstraint('code', name='uq_payroll_definitions_code'),
        UniqueConstraint('legal_employer_id', name='uq_payroll_definitions_employer'),
        CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code))", name='ck_payroll_definitions_code'),
        CheckConstraint("name ~ '[^[:space:]]'", name='ck_payroll_definitions_name'),
        CheckConstraint("country_code ~ '^[A-Z]{2}$' AND currency ~ '^[A-Z]{3}$'", name='ck_payroll_definitions_country_currency'),
        CheckConstraint("frequency = 'MONTHLY'", name='ck_payroll_definitions_frequency'),
        CheckConstraint('retirement_rate >= 0 AND withholding_rate >= 0 AND retirement_rate + withholding_rate <= 1', name='ck_payroll_definitions_rates'),
        CheckConstraint('standard_allowance >= 0', name='ck_payroll_definitions_allowance'),
    )
    id: Mapped[UUID] = identifier()
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(150))
    legal_employer_id: Mapped[UUID] = reference('legal_employers', 'fk_payroll_definitions_employer')
    country_code: Mapped[str] = mapped_column(String(2))
    frequency: Mapped[str] = mapped_column(String(10), server_default='MONTHLY')
    currency: Mapped[str] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text('true'))
    retirement_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    withholding_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    standard_allowance: Mapped[Decimal] = mapped_column(Numeric(14, 2))


class PayPeriod(WorkerTimestamps, Base):
    __tablename__ = 'pay_periods'
    __table_args__ = (
        UniqueConstraint('payroll_definition_id', 'period_start', name='uq_pay_periods_definition_start'),
        UniqueConstraint('payroll_definition_id', 'period_name', name='uq_pay_periods_definition_name'),
        CheckConstraint("period_start = date_trunc('month', period_start)::date AND period_end = (date_trunc('month', period_start) + interval '1 month - 1 day')::date", name='ck_pay_periods_calendar_month'),
        CheckConstraint('payment_date >= period_end', name='ck_pay_periods_payment_date'),
        CheckConstraint("period_name ~ '[^[:space:]]'", name='ck_pay_periods_name'),
        CheckConstraint("status IN ('OPEN', 'PROCESSING', 'PROCESSED')", name='ck_pay_periods_status'),
    )
    id: Mapped[UUID] = identifier()
    payroll_definition_id: Mapped[UUID] = reference('payroll_definitions', 'fk_pay_periods_definition')
    period_name: Mapped[str] = mapped_column(String(100))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    payment_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), server_default='OPEN')


class PayrollRun(WorkerTimestamps, Base):
    __tablename__ = 'payroll_runs'
    __table_args__ = (
        UniqueConstraint('pay_period_id', 'run_number', name='uq_payroll_runs_period_number'),
        Index('uq_payroll_runs_completed_period', 'pay_period_id', unique=True, postgresql_where=text("status = 'COMPLETED'")),
        CheckConstraint('run_number > 0', name='ck_payroll_runs_number'),
        CheckConstraint("status IN ('PROCESSING', 'COMPLETED', 'FAILED')", name='ck_payroll_runs_status'),
        CheckConstraint('completed_at IS NULL OR completed_at >= started_at', name='ck_payroll_runs_dates'),
    )
    id: Mapped[UUID] = identifier()
    pay_period_id: Mapped[UUID] = reference('pay_periods', 'fk_payroll_runs_period')
    run_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    initiated_by_user_id: Mapped[UUID | None] = reference('users', 'fk_payroll_runs_user', nullable=True, ondelete='SET NULL')
    rules_snapshot: Mapped[dict] = mapped_column(JSONB)
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    excluded_assignment_count: Mapped[int] = mapped_column(Integer, server_default='0')
    unpaid_day_count: Mapped[int] = mapped_column(Integer, server_default='0')


class PayrollResult(WorkerTimestamps, Base):
    __tablename__ = 'payroll_results'
    __table_args__ = (
        UniqueConstraint('payroll_run_id', 'assignment_id', name='uq_payroll_results_run_assignment'),
        Index('ix_payroll_results_person_run', 'person_id', 'payroll_run_id'),
        CheckConstraint('gross_pay >= 0 AND total_deductions >= 0 AND net_pay >= 0 AND net_pay = gross_pay - total_deductions', name='ck_payroll_results_totals'),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name='ck_payroll_results_currency'),
        CheckConstraint('eligible_days > 0 AND eligible_days <= period_days AND period_days BETWEEN 28 AND 31', name='ck_payroll_results_days'),
    )
    id: Mapped[UUID] = identifier()
    payroll_run_id: Mapped[UUID] = reference('payroll_runs', 'fk_payroll_results_run')
    person_id: Mapped[UUID] = reference('persons', 'fk_payroll_results_person')
    work_relationship_id: Mapped[UUID] = reference('work_relationships', 'fk_payroll_results_relationship')
    assignment_id: Mapped[UUID] = reference('assignments', 'fk_payroll_results_assignment')
    person_number: Mapped[str] = mapped_column(String(30))
    worker_name: Mapped[str] = mapped_column(String(201))
    assignment_number: Mapped[str] = mapped_column(String(30))
    gross_pay: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    total_deductions: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    net_pay: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3))
    eligible_days: Mapped[int] = mapped_column(Integer)
    period_days: Mapped[int] = mapped_column(Integer)
    calculation_snapshot: Mapped[list] = mapped_column(JSONB)


class PayrollResultLine(WorkerTimestamps, Base):
    __tablename__ = 'payroll_result_lines'
    __table_args__ = (
        UniqueConstraint('payroll_result_id', 'code', name='uq_payroll_result_lines_result_code'),
        CheckConstraint("line_type IN ('EARNING', 'DEDUCTION')", name='ck_payroll_result_lines_type'),
        CheckConstraint('amount >= 0', name='ck_payroll_result_lines_amount'),
    )
    id: Mapped[UUID] = identifier()
    payroll_result_id: Mapped[UUID] = reference('payroll_results', 'fk_payroll_result_lines_result')
    line_type: Mapped[str] = mapped_column(String(10))
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(150))
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))

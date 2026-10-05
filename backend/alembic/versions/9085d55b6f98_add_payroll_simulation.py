"""add payroll simulation

Revision ID: 9085d55b6f98
Revises: 5da74b24c7cc
Create Date: 2026-10-06 02:01:11.273927

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9085d55b6f98'
down_revision: Union[str, Sequence[str], None] = '5da74b24c7cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('payroll_definitions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('legal_employer_id', sa.UUID(), nullable=False),
    sa.Column('country_code', sa.String(length=2), nullable=False),
    sa.Column('frequency', sa.String(length=10), server_default='MONTHLY', nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('retirement_rate', sa.Numeric(precision=5, scale=4), nullable=False),
    sa.Column('withholding_rate', sa.Numeric(precision=5, scale=4), nullable=False),
    sa.Column('standard_allowance', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code))", name='ck_payroll_definitions_code'),
    sa.CheckConstraint("country_code ~ '^[A-Z]{2}$' AND currency ~ '^[A-Z]{3}$'", name='ck_payroll_definitions_country_currency'),
    sa.CheckConstraint("frequency = 'MONTHLY'", name='ck_payroll_definitions_frequency'),
    sa.CheckConstraint("name ~ '[^[:space:]]'", name='ck_payroll_definitions_name'),
    sa.CheckConstraint('retirement_rate >= 0 AND withholding_rate >= 0 AND retirement_rate + withholding_rate <= 1', name='ck_payroll_definitions_rates'),
    sa.CheckConstraint('standard_allowance >= 0', name='ck_payroll_definitions_allowance'),
    sa.ForeignKeyConstraint(['legal_employer_id'], ['legal_employers.id'], name='fk_payroll_definitions_employer', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_payroll_definitions_code'),
    sa.UniqueConstraint('legal_employer_id', name='uq_payroll_definitions_employer')
    )
    op.create_table('pay_periods',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('payroll_definition_id', sa.UUID(), nullable=False),
    sa.Column('period_name', sa.String(length=100), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('payment_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='OPEN', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("period_name ~ '[^[:space:]]'", name='ck_pay_periods_name'),
    sa.CheckConstraint("period_start = date_trunc('month', period_start)::date AND period_end = (date_trunc('month', period_start) + interval '1 month - 1 day')::date", name='ck_pay_periods_calendar_month'),
    sa.CheckConstraint("status IN ('OPEN', 'PROCESSING', 'PROCESSED')", name='ck_pay_periods_status'),
    sa.CheckConstraint('payment_date >= period_end', name='ck_pay_periods_payment_date'),
    sa.ForeignKeyConstraint(['payroll_definition_id'], ['payroll_definitions.id'], name='fk_pay_periods_definition', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('payroll_definition_id', 'period_name', name='uq_pay_periods_definition_name'),
    sa.UniqueConstraint('payroll_definition_id', 'period_start', name='uq_pay_periods_definition_start')
    )
    op.create_table('payroll_runs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('pay_period_id', sa.UUID(), nullable=False),
    sa.Column('run_number', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('initiated_by_user_id', sa.UUID(), nullable=True),
    sa.Column('rules_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('failure_reason', sa.String(length=255), nullable=True),
    sa.Column('excluded_assignment_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('unpaid_day_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('PROCESSING', 'COMPLETED', 'FAILED')", name='ck_payroll_runs_status'),
    sa.CheckConstraint('completed_at IS NULL OR completed_at >= started_at', name='ck_payroll_runs_dates'),
    sa.CheckConstraint('run_number > 0', name='ck_payroll_runs_number'),
    sa.ForeignKeyConstraint(['initiated_by_user_id'], ['users.id'], name='fk_payroll_runs_user', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['pay_period_id'], ['pay_periods.id'], name='fk_payroll_runs_period', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('pay_period_id', 'run_number', name='uq_payroll_runs_period_number')
    )
    op.create_index('uq_payroll_runs_completed_period', 'payroll_runs', ['pay_period_id'], unique=True, postgresql_where=sa.text("status = 'COMPLETED'"))
    op.create_table('payroll_results',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('payroll_run_id', sa.UUID(), nullable=False),
    sa.Column('person_id', sa.UUID(), nullable=False),
    sa.Column('work_relationship_id', sa.UUID(), nullable=False),
    sa.Column('assignment_id', sa.UUID(), nullable=False),
    sa.Column('person_number', sa.String(length=30), nullable=False),
    sa.Column('worker_name', sa.String(length=201), nullable=False),
    sa.Column('assignment_number', sa.String(length=30), nullable=False),
    sa.Column('gross_pay', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('total_deductions', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('net_pay', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('eligible_days', sa.Integer(), nullable=False),
    sa.Column('period_days', sa.Integer(), nullable=False),
    sa.Column('calculation_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name='ck_payroll_results_currency'),
    sa.CheckConstraint('eligible_days > 0 AND eligible_days <= period_days AND period_days BETWEEN 28 AND 31', name='ck_payroll_results_days'),
    sa.CheckConstraint('gross_pay >= 0 AND total_deductions >= 0 AND net_pay >= 0 AND net_pay = gross_pay - total_deductions', name='ck_payroll_results_totals'),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], name='fk_payroll_results_assignment', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['payroll_run_id'], ['payroll_runs.id'], name='fk_payroll_results_run', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['person_id'], ['persons.id'], name='fk_payroll_results_person', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['work_relationship_id'], ['work_relationships.id'], name='fk_payroll_results_relationship', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('payroll_run_id', 'assignment_id', name='uq_payroll_results_run_assignment')
    )
    op.create_index('ix_payroll_results_person_run', 'payroll_results', ['person_id', 'payroll_run_id'], unique=False)
    op.create_table('payroll_result_lines',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('payroll_result_id', sa.UUID(), nullable=False),
    sa.Column('line_type', sa.String(length=10), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('amount', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("line_type IN ('EARNING', 'DEDUCTION')", name='ck_payroll_result_lines_type'),
    sa.CheckConstraint('amount >= 0', name='ck_payroll_result_lines_amount'),
    sa.ForeignKeyConstraint(['payroll_result_id'], ['payroll_results.id'], name='fk_payroll_result_lines_result', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('payroll_result_id', 'code', name='uq_payroll_result_lines_result_code')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('payroll_result_lines')
    op.drop_index('ix_payroll_results_person_run', table_name='payroll_results')
    op.drop_table('payroll_results')
    op.drop_index('uq_payroll_runs_completed_period', table_name='payroll_runs', postgresql_where=sa.text("status = 'COMPLETED'"))
    op.drop_table('payroll_runs')
    op.drop_table('pay_periods')
    op.drop_table('payroll_definitions')

"""add annual flexible benefits planning

Revision ID: ccc6f4b903ce
Revises: 9085d55b6f98
Create Date: 2026-10-06 02:25:58.169435

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ccc6f4b903ce'
down_revision: Union[str, Sequence[str], None] = '9085d55b6f98'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('fbp_plans',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('legal_employer_id', sa.UUID(), nullable=False),
    sa.Column('plan_year', sa.Integer(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('budget_rate', sa.Numeric(precision=5, scale=4), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='DRAFT', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('budgets_generated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code)) AND name ~ '[^[:space:]]'", name='ck_fbp_plans_labels'),
    sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name='ck_fbp_plans_currency'),
    sa.CheckConstraint("status IN ('DRAFT','OPEN','CLOSED')", name='ck_fbp_plans_status'),
    sa.CheckConstraint('budget_rate > 0 AND budget_rate <= 1', name='ck_fbp_plans_rate'),
    sa.CheckConstraint('plan_year BETWEEN 1900 AND 9998 AND effective_from = make_date(plan_year,1,1) AND effective_to = make_date(plan_year,12,31)', name='ck_fbp_plans_year_dates'),
    sa.ForeignKeyConstraint(['legal_employer_id'], ['legal_employers.id'], name='fk_fbp_plans_employer', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_fbp_plans_code'),
    sa.UniqueConstraint('legal_employer_id', 'plan_year', name='uq_fbp_plans_employer_year')
    )
    op.create_table('fbp_components',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('plan_id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=True),
    sa.Column('component_type', sa.String(length=20), nullable=False),
    sa.Column('min_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('max_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('default_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code)) AND name ~ '[^[:space:]]'", name='ck_fbp_components_labels'),
    sa.CheckConstraint("component_type IN ('ALLOWANCE','BENEFIT','REIMBURSEMENT')", name='ck_fbp_components_type'),
    sa.CheckConstraint('display_order >= 0', name='ck_fbp_components_order'),
    sa.CheckConstraint('min_amount >= 0 AND max_amount >= min_amount AND default_amount >= 0 AND default_amount <= max_amount AND (default_amount = 0 OR default_amount >= min_amount)', name='ck_fbp_components_limits'),
    sa.ForeignKeyConstraint(['plan_id'], ['fbp_plans.id'], name='fk_fbp_components_plan', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'plan_id', name='uq_fbp_components_id_plan'),
    sa.UniqueConstraint('plan_id', 'code', name='uq_fbp_components_plan_code')
    )
    op.create_table('fbp_worker_budgets',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('plan_id', sa.UUID(), nullable=False),
    sa.Column('person_id', sa.UUID(), nullable=False),
    sa.Column('assignment_id', sa.UUID(), nullable=False),
    sa.Column('compensation_id', sa.UUID(), nullable=False),
    sa.Column('person_number', sa.String(length=30), nullable=False),
    sa.Column('worker_name', sa.String(length=201), nullable=False),
    sa.Column('assignment_number', sa.String(length=30), nullable=False),
    sa.Column('annual_base_salary', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('budget_rate', sa.Numeric(precision=5, scale=4), nullable=False),
    sa.Column('eligible_budget', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='OPEN', nullable=False),
    sa.Column('revision', sa.Integer(), server_default='0', nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("currency ~ '^[A-Z]{3}$' AND status IN ('OPEN','SUBMITTED','FINALIZED')", name='ck_fbp_budgets_currency_status'),
    sa.CheckConstraint('eligible_budget > 0 AND annual_base_salary > 0 AND budget_rate > 0 AND budget_rate <= 1', name='ck_fbp_budgets_amounts'),
    sa.CheckConstraint('revision >= 0', name='ck_fbp_budgets_revision'),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], name='fk_fbp_budgets_assignment', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['compensation_id'], ['assignment_compensation.id'], name='fk_fbp_budgets_compensation', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['person_id'], ['persons.id'], name='fk_fbp_budgets_person', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['plan_id'], ['fbp_plans.id'], name='fk_fbp_budgets_plan', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'plan_id', name='uq_fbp_budgets_id_plan'),
    sa.UniqueConstraint('plan_id', 'assignment_id', name='uq_fbp_budgets_plan_assignment')
    )
    op.create_index('ix_fbp_budgets_person_plan', 'fbp_worker_budgets', ['person_id', 'plan_id'], unique=False)
    op.create_table('fbp_elections',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('plan_id', sa.UUID(), nullable=False),
    sa.Column('worker_budget_id', sa.UUID(), nullable=False),
    sa.Column('component_id', sa.UUID(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('amount >= 0', name='ck_fbp_elections_amount'),
    sa.ForeignKeyConstraint(['component_id', 'plan_id'], ['fbp_components.id', 'fbp_components.plan_id'], name='fk_fbp_elections_component_plan', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['worker_budget_id', 'plan_id'], ['fbp_worker_budgets.id', 'fbp_worker_budgets.plan_id'], name='fk_fbp_elections_budget_plan', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('worker_budget_id', 'component_id', name='uq_fbp_elections_budget_component')
    )
    op.create_index('ix_fbp_elections_component_plan', 'fbp_elections', ['component_id', 'plan_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_fbp_elections_component_plan', table_name='fbp_elections')
    op.drop_table('fbp_elections')
    op.drop_index('ix_fbp_budgets_person_plan', table_name='fbp_worker_budgets')
    op.drop_table('fbp_worker_budgets')
    op.drop_table('fbp_components')
    op.drop_table('fbp_plans')

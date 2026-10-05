"""add reports and extract simulation

Revision ID: 57dcd64fceaa
Revises: eed5cf0e9369
Create Date: 2026-10-06 03:31:16.467871

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '57dcd64fceaa'
down_revision: Union[str, Sequence[str], None] = 'eed5cf0e9369'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('extract_definitions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('extract_type', sa.String(length=30), nullable=False),
    sa.Column('output_format', sa.String(length=4), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('configuration', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('last_successful_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("extract_type IN ('WORKER_SNAPSHOT','WORKER_CHANGES','PAYROLL_RESULTS','FBP_ELECTIONS') AND output_format IN ('CSV','JSON')", name='ck_extract_definitions_kind'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_extract_definitions_code')
    )
    op.create_table('extract_runs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('extract_definition_id', sa.UUID(), nullable=False),
    sa.Column('requested_by_user_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('mode', sa.String(length=12), nullable=False),
    sa.Column('watermark_from', sa.DateTime(timezone=True), nullable=True),
    sa.Column('watermark_to', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('row_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('output_filename', sa.String(length=100), nullable=True),
    sa.Column('error_message', sa.String(length=255), nullable=True),
    sa.Column('definition_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','FAILED') AND mode IN ('FULL','INCREMENTAL') AND row_count >= 0", name='ck_extract_runs_state'),
    sa.CheckConstraint('watermark_from IS NULL OR watermark_from <= watermark_to', name='ck_extract_runs_watermarks'),
    sa.ForeignKeyConstraint(['extract_definition_id'], ['extract_definitions.id'], name='fk_extract_runs_definition', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], name='fk_extract_runs_user', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_extract_runs_definition', 'extract_runs', ['extract_definition_id', 'started_at'], unique=False)
    op.create_table('report_definitions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=True),
    sa.Column('domain', sa.String(length=30), nullable=False),
    sa.Column('selected_columns', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('sort_definition', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("domain IN ('CORE_HR_WORKERS','PAYROLL_RESULTS','FBP_ALLOCATIONS','IMPORT_HISTORY')", name='ck_report_definitions_domain'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name='fk_reports_creator', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_report_definitions_code')
    )
    op.create_table('report_runs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('report_definition_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('requested_by_user_id', sa.UUID(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('row_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('error_message', sa.String(length=255), nullable=True),
    sa.Column('definition_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('result_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','FAILED') AND row_count >= 0", name='ck_report_runs_state'),
    sa.ForeignKeyConstraint(['report_definition_id'], ['report_definitions.id'], name='fk_report_runs_definition', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], name='fk_report_runs_user', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_report_runs_definition', 'report_runs', ['report_definition_id', 'started_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_report_runs_definition', table_name='report_runs')
    op.drop_table('report_runs')
    op.drop_table('report_definitions')
    op.drop_index('ix_extract_runs_definition', table_name='extract_runs')
    op.drop_table('extract_runs')
    op.drop_table('extract_definitions')

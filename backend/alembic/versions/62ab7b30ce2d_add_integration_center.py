"""add integration center

Revision ID: 62ab7b30ce2d
Revises: 57dcd64fceaa
Create Date: 2026-10-07 22:33:49.385417

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '62ab7b30ce2d'
down_revision: Union[str, Sequence[str], None] = '57dcd64fceaa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('integration_definitions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=True),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('integration_type', sa.String(length=30), nullable=False),
    sa.Column('transport_type', sa.String(length=10), nullable=False),
    sa.Column('endpoint_url', sa.String(length=2000), nullable=True),
    sa.Column('http_method', sa.String(length=5), nullable=True),
    sa.Column('output_format', sa.String(length=4), nullable=False),
    sa.Column('configuration', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(direction='OUTBOUND' AND integration_type IN ('WORKER_EXPORT','PAYROLL_EXPORT','FBP_EXPORT')) OR (direction='INBOUND' AND integration_type IN ('PERSON_UPDATE','ASSIGNMENT_CHANGE','COMPENSATION_CHANGE'))", name='ck_integration_definitions_type'),
    sa.CheckConstraint("transport_type IN ('HTTP_REST','FILE') AND output_format IN ('JSON','CSV')", name='ck_integration_definitions_transport'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name='fk_integration_definitions_user', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_integration_definitions_code')
    )
    op.create_table('integration_runs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('integration_definition_id', sa.UUID(), nullable=False),
    sa.Column('requested_by_user_id', sa.UUID(), nullable=True),
    sa.Column('retry_of_run_id', sa.UUID(), nullable=True),
    sa.Column('retry_depth', sa.Integer(), server_default='0', nullable=False),
    sa.Column('request_key', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=25), nullable=False),
    sa.Column('trigger_type', sa.String(length=10), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('records_read', sa.Integer(), server_default='0', nullable=False),
    sa.Column('records_succeeded', sa.Integer(), server_default='0', nullable=False),
    sa.Column('records_failed', sa.Integer(), server_default='0', nullable=False),
    sa.Column('definition_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('request_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('response_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('output_filename', sa.String(length=100), nullable=True),
    sa.Column('safe_error_message', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED') AND trigger_type IN ('MANUAL','API')", name='ck_integration_runs_state'),
    sa.CheckConstraint('records_read >= 0 AND records_succeeded >= 0 AND records_failed >= 0 AND records_succeeded + records_failed <= records_read AND retry_depth BETWEEN 0 AND 3', name='ck_integration_runs_counts'),
    sa.ForeignKeyConstraint(['integration_definition_id'], ['integration_definitions.id'], name='fk_integration_runs_definition', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], name='fk_integration_runs_user', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['retry_of_run_id'], ['integration_runs.id'], name='fk_integration_runs_retry', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('integration_definition_id', 'request_key', name='uq_integration_runs_request'),
    sa.UniqueConstraint('retry_of_run_id', name='uq_integration_runs_retry')
    )
    op.create_index('ix_integration_runs_definition', 'integration_runs', ['integration_definition_id', 'started_at'], unique=False)
    op.create_table('integration_run_items',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('integration_run_id', sa.UUID(), nullable=False),
    sa.Column('sequence_number', sa.Integer(), nullable=False),
    sa.Column('delivery_key', sa.String(length=100), nullable=False),
    sa.Column('business_reference', sa.String(length=255), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('response_status', sa.Integer(), nullable=True),
    sa.Column('safe_error_message', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("sequence_number > 0 AND status IN ('PENDING','SUCCESS','FAILED')", name='ck_integration_items_state'),
    sa.ForeignKeyConstraint(['integration_run_id'], ['integration_runs.id'], name='fk_integration_items_run', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('integration_run_id', 'sequence_number', name='uq_integration_items_sequence')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('integration_run_items')
    op.drop_index('ix_integration_runs_definition', table_name='integration_runs')
    op.drop_table('integration_runs')
    op.drop_table('integration_definitions')

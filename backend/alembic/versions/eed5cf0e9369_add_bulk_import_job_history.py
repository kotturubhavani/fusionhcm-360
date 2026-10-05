"""add bulk import job history

Revision ID: eed5cf0e9369
Revises: ccc6f4b903ce
Create Date: 2026-10-06 02:50:25.940168

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'eed5cf0e9369'
down_revision: Union[str, Sequence[str], None] = 'ccc6f4b903ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('import_jobs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('object_type', sa.String(length=30), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=25), server_default='UPLOADED', nullable=False),
    sa.Column('total_rows', sa.Integer(), nullable=False),
    sa.Column('valid_rows', sa.Integer(), server_default='0', nullable=False),
    sa.Column('invalid_rows', sa.Integer(), server_default='0', nullable=False),
    sa.Column('processed_rows', sa.Integer(), server_default='0', nullable=False),
    sa.Column('failed_rows', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("object_type IN ('WORKER_HIRE','PERSON_UPDATE','ASSIGNMENT_CHANGE','COMPENSATION_CHANGE')", name='ck_import_jobs_type'),
    sa.CheckConstraint("status IN ('UPLOADED','VALIDATED','PROCESSING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED')", name='ck_import_jobs_status'),
    sa.CheckConstraint('total_rows > 0 AND valid_rows >= 0 AND invalid_rows >= 0 AND processed_rows >= 0 AND failed_rows >= 0 AND valid_rows + invalid_rows <= total_rows AND processed_rows + failed_rows <= valid_rows', name='ck_import_jobs_counts'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name='fk_import_jobs_creator', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_import_jobs_created', 'import_jobs', ['created_at', 'id'], unique=False)
    op.create_index('ix_import_jobs_creator', 'import_jobs', ['created_by_user_id'], unique=False)
    op.create_table('import_rows',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('import_job_id', sa.UUID(), nullable=False),
    sa.Column('row_number', sa.Integer(), nullable=False),
    sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('normalized_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.String(length=10), server_default='PENDING', nullable=False),
    sa.Column('error_code', sa.String(length=50), nullable=True),
    sa.Column('error_message', sa.String(length=500), nullable=True),
    sa.Column('created_record_reference', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('PENDING','VALID','INVALID','PROCESSED','FAILED')", name='ck_import_rows_status'),
    sa.CheckConstraint('row_number >= 2', name='ck_import_rows_number'),
    sa.ForeignKeyConstraint(['import_job_id'], ['import_jobs.id'], name='fk_import_rows_job', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('import_job_id', 'row_number', name='uq_import_rows_job_number')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('import_rows')
    op.drop_index('ix_import_jobs_creator', table_name='import_jobs')
    op.drop_index('ix_import_jobs_created', table_name='import_jobs')
    op.drop_table('import_jobs')

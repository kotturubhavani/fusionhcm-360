"""create assignments and assignment versions

Revision ID: 09f8f4781ff6
Revises: b188bcc6a4e0
Create Date: 2026-10-05 22:09:42.149764

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09f8f4781ff6'
down_revision: Union[str, Sequence[str], None] = 'b188bcc6a4e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('assignments',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('work_relationship_id', sa.UUID(), nullable=False),
        sa.Column('assignment_number', sa.String(length=30), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("assignment_number ~ '[^[:space:]]' AND assignment_number = upper(btrim(assignment_number))", name='ck_assignments_assignment_number'),
        sa.CheckConstraint('end_date IS NULL OR end_date >= start_date', name='ck_assignments_dates'),
        sa.ForeignKeyConstraint(['work_relationship_id'], ['work_relationships.id'], name='fk_assignments_work_relationship', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assignment_number', name='uq_assignments_assignment_number')
    )
    op.create_index('ix_assignments_relationship_start', 'assignments', ['work_relationship_id', 'start_date'], unique=False)
    op.create_table('assignment_versions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('assignment_id', sa.UUID(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('business_unit_id', sa.UUID(), nullable=False),
        sa.Column('department_id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('grade_id', sa.UUID(), nullable=True),
        sa.Column('location_id', sa.UUID(), nullable=False),
        sa.Column('manager_assignment_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('work_time_type', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'ON_LEAVE', 'SUSPENDED')", name='ck_assignment_versions_status'),
        sa.CheckConstraint("work_time_type IN ('FULL_TIME', 'PART_TIME')", name='ck_assignment_versions_work_time_type'),
        sa.CheckConstraint('effective_to IS NULL OR effective_to >= effective_from', name='ck_assignment_versions_dates'),
        sa.CheckConstraint('manager_assignment_id IS NULL OR manager_assignment_id <> assignment_id', name='ck_assignment_versions_manager'),
        sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], name='fk_assignment_versions_assignment', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['business_unit_id'], ['business_units.id'], name='fk_assignment_versions_business_unit', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['department_id', 'business_unit_id'], ['departments.id', 'departments.business_unit_id'], name='fk_assignment_versions_department_business_unit', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['grade_id'], ['grades.id'], name='fk_assignment_versions_grade', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name='fk_assignment_versions_job', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], name='fk_assignment_versions_location', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['manager_assignment_id'], ['assignments.id'], name='fk_assignment_versions_manager', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assignment_id', 'effective_from', name='uq_assignment_versions_assignment_from')
    )
    op.create_index('ix_assignment_versions_business_unit_from', 'assignment_versions', ['business_unit_id', 'effective_from'], unique=False)
    op.create_index('ix_assignment_versions_department_business_unit', 'assignment_versions', ['department_id', 'business_unit_id'], unique=False)
    op.create_index('ix_assignment_versions_grade', 'assignment_versions', ['grade_id'], unique=False)
    op.create_index('ix_assignment_versions_job', 'assignment_versions', ['job_id'], unique=False)
    op.create_index('ix_assignment_versions_location', 'assignment_versions', ['location_id'], unique=False)
    op.create_index('ix_assignment_versions_manager', 'assignment_versions', ['manager_assignment_id'], unique=False, postgresql_where=sa.text('manager_assignment_id IS NOT NULL'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_assignment_versions_manager', table_name='assignment_versions', postgresql_where=sa.text('manager_assignment_id IS NOT NULL'))
    op.drop_index('ix_assignment_versions_location', table_name='assignment_versions')
    op.drop_index('ix_assignment_versions_job', table_name='assignment_versions')
    op.drop_index('ix_assignment_versions_grade', table_name='assignment_versions')
    op.drop_index('ix_assignment_versions_department_business_unit', table_name='assignment_versions')
    op.drop_index('ix_assignment_versions_business_unit_from', table_name='assignment_versions')
    op.drop_table('assignment_versions')
    op.drop_index('ix_assignments_relationship_start', table_name='assignments')
    op.drop_table('assignments')

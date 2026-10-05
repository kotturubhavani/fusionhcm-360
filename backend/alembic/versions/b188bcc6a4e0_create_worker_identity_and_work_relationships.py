"""create worker identity and work relationships

Revision ID: b188bcc6a4e0
Revises: 18d1a6531be2
Create Date: 2026-10-05 22:01:55.776987

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b188bcc6a4e0'
down_revision: Union[str, Sequence[str], None] = '18d1a6531be2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('persons',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('person_number', sa.String(length=30), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('preferred_name', sa.String(length=100), nullable=True),
        sa.Column('date_of_birth', sa.Date(), nullable=True),
        sa.Column('personal_email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("first_name ~ '[^[:space:]]'", name='ck_persons_first_name'),
        sa.CheckConstraint("last_name ~ '[^[:space:]]'", name='ck_persons_last_name'),
        sa.CheckConstraint("person_number ~ '[^[:space:]]' AND person_number = upper(btrim(person_number))", name='ck_persons_person_number'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('person_number', name='uq_persons_person_number')
    )
    op.create_table('work_relationships',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('person_id', sa.UUID(), nullable=False),
        sa.Column('legal_employer_id', sa.UUID(), nullable=False),
        sa.Column('employment_type', sa.String(length=20), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('termination_reason', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("employment_type IN ('REGULAR', 'FIXED_TERM', 'INTERN')", name='ck_work_relationships_employment_type'),
        sa.CheckConstraint('end_date IS NULL OR end_date >= start_date', name='ck_work_relationships_dates'),
        sa.ForeignKeyConstraint(['legal_employer_id'], ['legal_employers.id'], name='fk_work_relationships_legal_employer', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['person_id'], ['persons.id'], name='fk_work_relationships_person', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('person_id', 'legal_employer_id', 'start_date', name='uq_work_relationships_person_employer_start')
    )
    op.create_index('ix_work_relationships_employer_start', 'work_relationships', ['legal_employer_id', 'start_date'], unique=False)
    op.add_column('users', sa.Column('person_id', sa.UUID(), nullable=True))
    op.create_unique_constraint('uq_users_person_id', 'users', ['person_id'])
    op.create_foreign_key('fk_users_person', 'users', 'persons', ['person_id'], ['id'], ondelete='RESTRICT')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_users_person', 'users', type_='foreignkey')
    op.drop_constraint('uq_users_person_id', 'users', type_='unique')
    op.drop_column('users', 'person_id')
    op.drop_index('ix_work_relationships_employer_start', table_name='work_relationships')
    op.drop_table('work_relationships')
    op.drop_table('persons')

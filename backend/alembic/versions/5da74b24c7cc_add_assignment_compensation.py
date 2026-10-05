"""add assignment compensation

Revision ID: 5da74b24c7cc
Revises: 09f8f4781ff6
Create Date: 2026-10-05 22:29:28.120291

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5da74b24c7cc'
down_revision: Union[str, Sequence[str], None] = '09f8f4781ff6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('assignment_compensation',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('assignment_id', sa.UUID(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('annual_base_salary', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name='ck_assignment_compensation_currency'),
        sa.CheckConstraint('annual_base_salary >= 0', name='ck_assignment_compensation_salary'),
        sa.CheckConstraint('effective_to IS NULL OR effective_to >= effective_from', name='ck_assignment_compensation_dates'),
        sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], name='fk_assignment_compensation_assignment', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assignment_id', 'effective_from', name='uq_assignment_compensation_assignment_from')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('assignment_compensation')

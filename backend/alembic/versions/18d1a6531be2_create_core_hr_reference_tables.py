"""create core hr reference tables

Revision ID: 18d1a6531be2
Revises: 87ec97bdf444
Create Date: 2026-10-05 21:46:13.534272

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18d1a6531be2'
down_revision: Union[str, Sequence[str], None] = '87ec97bdf444'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('business_units',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code))", name='ck_business_units_code'),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name='ck_business_units_name'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_business_units_code')
    )
    op.create_table('grades',
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code))", name='ck_grades_code'),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name='ck_grades_name'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_grades_code')
    )
    op.create_table('jobs',
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code))", name='ck_jobs_code'),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name='ck_jobs_name'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_jobs_code')
    )
    op.create_table('legal_employers',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('country_code', sa.String(length=2), nullable=False),
        sa.CheckConstraint("country_code ~ '^[A-Z]{2}$'", name='ck_legal_employers_country_code'),
        sa.CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code))", name='ck_legal_employers_code'),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name='ck_legal_employers_name'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_legal_employers_code')
    )
    op.create_table('locations',
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('address_line', sa.String(length=255), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('country_code', sa.String(length=2), nullable=False),
        sa.CheckConstraint("country_code ~ '^[A-Z]{2}$'", name='ck_locations_country_code'),
        sa.CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code))", name='ck_locations_code'),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name='ck_locations_name'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_locations_code')
    )
    op.create_table('departments',
        sa.Column('business_unit_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code))", name='ck_departments_code'),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name='ck_departments_name'),
        sa.ForeignKeyConstraint(['business_unit_id'], ['business_units.id'], name='fk_departments_business_unit', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('business_unit_id', 'code', name='uq_departments_code'),
        sa.UniqueConstraint('id', 'business_unit_id', name='uq_departments_id_business_unit')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('departments')
    op.drop_table('locations')
    op.drop_table('legal_employers')
    op.drop_table('jobs')
    op.drop_table('grades')
    op.drop_table('business_units')

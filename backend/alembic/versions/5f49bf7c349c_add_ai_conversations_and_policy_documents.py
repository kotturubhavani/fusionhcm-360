"""add AI conversations and policy documents

Revision ID: 5f49bf7c349c
Revises: 62ab7b30ce2d
Create Date: 2026-10-07 23:20:13.621182

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5f49bf7c349c'
down_revision: Union[str, Sequence[str], None] = '62ab7b30ce2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('ai_conversations',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('person_id', sa.UUID(), nullable=True),
    sa.Column('scope', sa.String(length=5), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("scope IN ('STAFF','SELF')", name='ck_ai_conversations_scope'),
    sa.ForeignKeyConstraint(['person_id'], ['persons.id'], name='fk_ai_conversations_person', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_ai_conversations_user', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_conversations_owner', 'ai_conversations', ['user_id', 'created_at'], unique=False)
    op.create_table('document_sources',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.String(length=1000), nullable=True),
    sa.Column('status', sa.String(length=10), server_default='ACTIVE', nullable=False),
    sa.Column('audience', sa.String(length=5), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE','INACTIVE') AND audience IN ('ALL','STAFF')", name='ck_document_sources_scope'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name='fk_document_sources_user', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', name='uq_document_sources_name')
    )
    op.create_table('ai_messages',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('sequence_number', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=10), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('user','assistant') AND sequence_number > 0", name='ck_ai_messages_role'),
    sa.ForeignKeyConstraint(['conversation_id'], ['ai_conversations.id'], name='fk_ai_messages_conversation', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('conversation_id', 'sequence_number', name='uq_ai_messages_sequence')
    )
    op.create_table('ai_query_audits',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('conversation_id', sa.UUID(), nullable=True),
    sa.Column('query_type', sa.String(length=30), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('SUCCESS','FAILED','DENIED')", name='ck_ai_audits_status'),
    sa.ForeignKeyConstraint(['conversation_id'], ['ai_conversations.id'], name='fk_ai_audits_conversation', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_ai_audits_user', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_audits_user_created', 'ai_query_audits', ['user_id', 'created_at'], unique=False)
    op.create_table('documents',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('source_id', sa.UUID(), nullable=False),
    sa.Column('filename', sa.String(length=150), nullable=False),
    sa.Column('content_type', sa.String(length=50), nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('safe_error_message', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('INDEXED','FAILED','INACTIVE')", name='ck_documents_status'),
    sa.ForeignKeyConstraint(['source_id'], ['document_sources.id'], name='fk_documents_source', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_id', 'checksum', name='uq_documents_source_checksum')
    )
    op.create_table('document_chunks',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('text_content', sa.Text(), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('embedding_reference', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('chunk_index >= 0', name='ck_document_chunks_index'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name='fk_document_chunks_document', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id', 'chunk_index', name='uq_document_chunks_index')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('document_chunks')
    op.drop_table('documents')
    op.drop_index('ix_ai_audits_user_created', table_name='ai_query_audits')
    op.drop_table('ai_query_audits')
    op.drop_table('ai_messages')
    op.drop_table('document_sources')
    op.drop_index('ix_ai_conversations_owner', table_name='ai_conversations')
    op.drop_table('ai_conversations')

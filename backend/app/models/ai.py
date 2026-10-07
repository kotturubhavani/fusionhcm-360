"""Owned conversations, policy text, and bounded query audit records."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.worker import WorkerTimestamps
from app.models.payroll import identifier, reference


class AIConversation(WorkerTimestamps, Base):
    __tablename__ = 'ai_conversations'
    __table_args__ = (Index('ix_ai_conversations_owner', 'user_id', 'created_at'), CheckConstraint("scope IN ('STAFF','SELF')", name='ck_ai_conversations_scope'))
    id: Mapped[UUID] = identifier()
    user_id: Mapped[UUID] = reference('users', 'fk_ai_conversations_user')
    person_id: Mapped[UUID | None] = reference('persons', 'fk_ai_conversations_person', nullable=True)
    scope: Mapped[str] = mapped_column(String(5))
    title: Mapped[str] = mapped_column(String(100))


class AIMessage(WorkerTimestamps, Base):
    __tablename__ = 'ai_messages'
    __table_args__ = (UniqueConstraint('conversation_id', 'sequence_number', name='uq_ai_messages_sequence'), CheckConstraint("role IN ('user','assistant') AND sequence_number > 0", name='ck_ai_messages_role'))
    id: Mapped[UUID] = identifier()
    conversation_id: Mapped[UUID] = reference('ai_conversations', 'fk_ai_messages_conversation')
    sequence_number: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column('metadata', JSONB)


class DocumentSource(WorkerTimestamps, Base):
    __tablename__ = 'document_sources'
    __table_args__ = (UniqueConstraint('name', name='uq_document_sources_name'), CheckConstraint("status IN ('ACTIVE','INACTIVE') AND audience IN ('ALL','STAFF')", name='ck_document_sources_scope'))
    id: Mapped[UUID] = identifier()
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(10), server_default='ACTIVE')
    audience: Mapped[str] = mapped_column(String(5))
    created_by_user_id: Mapped[UUID | None] = reference('users', 'fk_document_sources_user', nullable=True, ondelete='SET NULL')


class Document(WorkerTimestamps, Base):
    __tablename__ = 'documents'
    __table_args__ = (UniqueConstraint('source_id','checksum',name='uq_documents_source_checksum'), CheckConstraint("status IN ('INDEXED','FAILED','INACTIVE')", name='ck_documents_status'))
    id: Mapped[UUID] = identifier()
    source_id: Mapped[UUID] = reference('document_sources', 'fk_documents_source')
    filename: Mapped[str] = mapped_column(String(150))
    content_type: Mapped[str] = mapped_column(String(50))
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(10))
    details: Mapped[dict] = mapped_column('metadata', JSONB)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    safe_error_message: Mapped[str | None] = mapped_column(String(255))


class DocumentChunk(WorkerTimestamps, Base):
    __tablename__ = 'document_chunks'
    __table_args__ = (UniqueConstraint('document_id','chunk_index',name='uq_document_chunks_index'), CheckConstraint('chunk_index >= 0',name='ck_document_chunks_index'))
    id: Mapped[UUID] = identifier()
    document_id: Mapped[UUID] = reference('documents','fk_document_chunks_document')
    chunk_index: Mapped[int] = mapped_column(Integer)
    text_content: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column('metadata', JSONB)
    embedding_reference: Mapped[str | None] = mapped_column(String(100))


class AIQueryAudit(WorkerTimestamps, Base):
    __tablename__ = 'ai_query_audits'
    __table_args__ = (Index('ix_ai_audits_user_created','user_id','created_at'), CheckConstraint("status IN ('SUCCESS','FAILED','DENIED')",name='ck_ai_audits_status'))
    id: Mapped[UUID] = identifier()
    user_id: Mapped[UUID | None] = reference('users','fk_ai_audits_user',nullable=True,ondelete='SET NULL')
    conversation_id: Mapped[UUID | None] = reference('ai_conversations','fk_ai_audits_conversation',nullable=True)
    query_type: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(10))
    details: Mapped[dict] = mapped_column('metadata', JSONB)

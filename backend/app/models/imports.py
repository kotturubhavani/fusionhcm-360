"""Auditable CSV import jobs and independent row outcomes."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.worker import WorkerTimestamps


class ImportJob(WorkerTimestamps, Base):
    __tablename__ = 'import_jobs'
    __table_args__ = (
        CheckConstraint("object_type IN ('WORKER_HIRE','PERSON_UPDATE','ASSIGNMENT_CHANGE','COMPENSATION_CHANGE')", name='ck_import_jobs_type'),
        CheckConstraint("status IN ('UPLOADED','VALIDATED','PROCESSING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED')", name='ck_import_jobs_status'),
        CheckConstraint('total_rows > 0 AND valid_rows >= 0 AND invalid_rows >= 0 AND processed_rows >= 0 AND failed_rows >= 0 AND valid_rows + invalid_rows <= total_rows AND processed_rows + failed_rows <= valid_rows', name='ck_import_jobs_counts'),
        Index('ix_import_jobs_created', 'created_at', 'id'),
        Index('ix_import_jobs_creator', 'created_by_user_id'),
    )
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    object_type: Mapped[str] = mapped_column(String(30))
    original_filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(25), server_default='UPLOADED')
    total_rows: Mapped[int] = mapped_column(Integer)
    valid_rows: Mapped[int] = mapped_column(Integer, server_default='0')
    invalid_rows: Mapped[int] = mapped_column(Integer, server_default='0')
    processed_rows: Mapped[int] = mapped_column(Integer, server_default='0')
    failed_rows: Mapped[int] = mapped_column(Integer, server_default='0')
    created_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL', name='fk_import_jobs_creator'))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportRow(WorkerTimestamps, Base):
    __tablename__ = 'import_rows'
    __table_args__ = (
        UniqueConstraint('import_job_id', 'row_number', name='uq_import_rows_job_number'),
        CheckConstraint('row_number >= 2', name='ck_import_rows_number'),
        CheckConstraint("status IN ('PENDING','VALID','INVALID','PROCESSED','FAILED')", name='ck_import_rows_status'),
    )
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    import_job_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey('import_jobs.id', ondelete='RESTRICT', name='fk_import_rows_job'))
    row_number: Mapped[int] = mapped_column(Integer)
    raw_data: Mapped[dict] = mapped_column(JSONB)
    normalized_data: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(10), server_default='PENDING')
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_record_reference: Mapped[dict | None] = mapped_column(JSONB)

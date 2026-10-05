"""Saved reporting and outbound extract simulation history."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.worker import WorkerTimestamps
from app.models.payroll import identifier, reference


class ReportDefinition(WorkerTimestamps, Base):
    __tablename__='report_definitions'
    __table_args__=(UniqueConstraint('code',name='uq_report_definitions_code'),CheckConstraint("domain IN ('CORE_HR_WORKERS','PAYROLL_RESULTS','FBP_ALLOCATIONS','IMPORT_HISTORY')",name='ck_report_definitions_domain'),)
    id: Mapped[UUID]=identifier()
    code: Mapped[str]=mapped_column(String(30))
    name: Mapped[str]=mapped_column(String(150))
    description: Mapped[str|None]=mapped_column(String(2000))
    domain: Mapped[str]=mapped_column(String(30))
    selected_columns: Mapped[list]=mapped_column(JSONB)
    filters: Mapped[list]=mapped_column(JSONB)
    sort_definition: Mapped[list]=mapped_column(JSONB)
    is_active: Mapped[bool]=mapped_column(Boolean,server_default=text('true'))
    created_by_user_id: Mapped[UUID|None]=reference('users','fk_reports_creator',nullable=True,ondelete='SET NULL')


class ReportRun(WorkerTimestamps, Base):
    __tablename__='report_runs'
    __table_args__=(Index('ix_report_runs_definition','report_definition_id','started_at'),CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','FAILED') AND row_count >= 0",name='ck_report_runs_state'),)
    id: Mapped[UUID]=identifier()
    report_definition_id: Mapped[UUID]=reference('report_definitions','fk_report_runs_definition')
    status: Mapped[str]=mapped_column(String(12))
    requested_by_user_id: Mapped[UUID|None]=reference('users','fk_report_runs_user',nullable=True,ondelete='SET NULL')
    started_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    row_count: Mapped[int]=mapped_column(Integer,server_default='0')
    error_message: Mapped[str|None]=mapped_column(String(255))
    definition_snapshot: Mapped[dict]=mapped_column(JSONB)
    result_payload: Mapped[list|None]=mapped_column(JSONB)


class ExtractDefinition(WorkerTimestamps, Base):
    __tablename__='extract_definitions'
    __table_args__=(UniqueConstraint('code',name='uq_extract_definitions_code'),CheckConstraint("extract_type IN ('WORKER_SNAPSHOT','WORKER_CHANGES','PAYROLL_RESULTS','FBP_ELECTIONS') AND output_format IN ('CSV','JSON')",name='ck_extract_definitions_kind'),)
    id: Mapped[UUID]=identifier()
    code: Mapped[str]=mapped_column(String(30))
    name: Mapped[str]=mapped_column(String(150))
    extract_type: Mapped[str]=mapped_column(String(30))
    output_format: Mapped[str]=mapped_column(String(4))
    is_active: Mapped[bool]=mapped_column(Boolean,server_default=text('true'))
    configuration: Mapped[dict]=mapped_column(JSONB)
    last_successful_run_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))


class ExtractRun(WorkerTimestamps, Base):
    __tablename__='extract_runs'
    __table_args__=(Index('ix_extract_runs_definition','extract_definition_id','started_at'),CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','FAILED') AND mode IN ('FULL','INCREMENTAL') AND row_count >= 0",name='ck_extract_runs_state'),CheckConstraint('watermark_from IS NULL OR watermark_from <= watermark_to',name='ck_extract_runs_watermarks'),)
    id: Mapped[UUID]=identifier()
    extract_definition_id: Mapped[UUID]=reference('extract_definitions','fk_extract_runs_definition')
    requested_by_user_id: Mapped[UUID|None]=reference('users','fk_extract_runs_user',nullable=True,ondelete='SET NULL')
    status: Mapped[str]=mapped_column(String(12))
    mode: Mapped[str]=mapped_column(String(12))
    watermark_from: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    watermark_to: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    row_count: Mapped[int]=mapped_column(Integer,server_default='0')
    output_filename: Mapped[str|None]=mapped_column(String(100))
    error_message: Mapped[str|None]=mapped_column(String(255))
    definition_snapshot: Mapped[dict]=mapped_column(JSONB)

"""Integration definitions and immutable per-attempt delivery history."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean,CheckConstraint,DateTime,Index,Integer,String,UniqueConstraint,text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.core.database import Base
from app.models.worker import WorkerTimestamps
from app.models.payroll import identifier,reference

class IntegrationDefinition(WorkerTimestamps,Base):
    __tablename__='integration_definitions'
    __table_args__=(UniqueConstraint('code',name='uq_integration_definitions_code'),CheckConstraint("(direction='OUTBOUND' AND integration_type IN ('WORKER_EXPORT','PAYROLL_EXPORT','FBP_EXPORT')) OR (direction='INBOUND' AND integration_type IN ('PERSON_UPDATE','ASSIGNMENT_CHANGE','COMPENSATION_CHANGE'))",name='ck_integration_definitions_type'),CheckConstraint("transport_type IN ('HTTP_REST','FILE') AND output_format IN ('JSON','CSV')",name='ck_integration_definitions_transport'),)
    id:Mapped[UUID]=identifier()
    code:Mapped[str]=mapped_column(String(30))
    name:Mapped[str]=mapped_column(String(150))
    description:Mapped[str|None]=mapped_column(String(2000))
    direction:Mapped[str]=mapped_column(String(10))
    integration_type:Mapped[str]=mapped_column(String(30))
    transport_type:Mapped[str]=mapped_column(String(10))
    endpoint_url:Mapped[str|None]=mapped_column(String(2000))
    http_method:Mapped[str|None]=mapped_column(String(5))
    output_format:Mapped[str]=mapped_column(String(4))
    configuration:Mapped[dict]=mapped_column(JSONB)
    is_active:Mapped[bool]=mapped_column(Boolean,server_default=text('true'))
    created_by_user_id:Mapped[UUID|None]=reference('users','fk_integration_definitions_user',nullable=True,ondelete='SET NULL')

class IntegrationRun(WorkerTimestamps,Base):
    __tablename__='integration_runs'
    __table_args__=(UniqueConstraint('integration_definition_id','request_key',name='uq_integration_runs_request'),UniqueConstraint('retry_of_run_id',name='uq_integration_runs_retry'),Index('ix_integration_runs_definition','integration_definition_id','started_at'),CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','COMPLETED_WITH_ERRORS','FAILED') AND trigger_type IN ('MANUAL','API')",name='ck_integration_runs_state'),CheckConstraint('records_read >= 0 AND records_succeeded >= 0 AND records_failed >= 0 AND records_succeeded + records_failed <= records_read AND retry_depth BETWEEN 0 AND 3',name='ck_integration_runs_counts'),)
    id:Mapped[UUID]=identifier()
    integration_definition_id:Mapped[UUID]=reference('integration_definitions','fk_integration_runs_definition')
    requested_by_user_id:Mapped[UUID|None]=reference('users','fk_integration_runs_user',nullable=True,ondelete='SET NULL')
    retry_of_run_id:Mapped[UUID|None]=reference('integration_runs','fk_integration_runs_retry',nullable=True)
    retry_depth:Mapped[int]=mapped_column(Integer,server_default='0')
    request_key:Mapped[str]=mapped_column(String(100))
    status:Mapped[str]=mapped_column(String(25))
    trigger_type:Mapped[str]=mapped_column(String(10))
    started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    records_read:Mapped[int]=mapped_column(Integer,server_default='0')
    records_succeeded:Mapped[int]=mapped_column(Integer,server_default='0')
    records_failed:Mapped[int]=mapped_column(Integer,server_default='0')
    definition_snapshot:Mapped[dict]=mapped_column(JSONB)
    request_metadata:Mapped[dict|None]=mapped_column(JSONB)
    response_metadata:Mapped[dict|None]=mapped_column(JSONB)
    output_filename:Mapped[str|None]=mapped_column(String(100))
    safe_error_message:Mapped[str|None]=mapped_column(String(255))

class IntegrationRunItem(WorkerTimestamps,Base):
    __tablename__='integration_run_items'
    __table_args__=(UniqueConstraint('integration_run_id','sequence_number',name='uq_integration_items_sequence'),CheckConstraint("sequence_number > 0 AND status IN ('PENDING','SUCCESS','FAILED')",name='ck_integration_items_state'),)
    id:Mapped[UUID]=identifier()
    integration_run_id:Mapped[UUID]=reference('integration_runs','fk_integration_items_run')
    sequence_number:Mapped[int]=mapped_column(Integer)
    delivery_key:Mapped[str]=mapped_column(String(100))
    business_reference:Mapped[str]=mapped_column(String(255))
    payload:Mapped[dict]=mapped_column(JSONB)
    status:Mapped[str]=mapped_column(String(10))
    response_status:Mapped[int|None]=mapped_column(Integer)
    safe_error_message:Mapped[str|None]=mapped_column(String(500))

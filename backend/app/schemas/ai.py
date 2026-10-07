from typing import Literal
from uuid import UUID
from pydantic import Field, StrictBool, AwareDatetime
from app.schemas.core_hr import Contract, ReadRecord, Code, Day

Tool = Literal['search_workers','get_worker_summary','get_payroll_result','get_payroll_history','get_fbp_status','get_import_job_status','get_report_run_status','get_extract_run_status','get_integration_run_status','get_my_worker_summary','get_my_payroll','get_my_fbp']
class ChatRequest(Contract):
    message: str = Field(min_length=1,max_length=2000)
    conversation_id: UUID | None = None
    tool: Tool | None = None
    person_number: Code | None = None
    reference_id: UUID | None = None
    row_number: int | None = Field(default=None,ge=2,le=5001)
    as_of: Day | None = None
    source_id: UUID | None = None
    document_id: UUID | None = None
    request_key: UUID

class DocumentState(Contract):
    is_active: StrictBool

class ConversationRead(ReadRecord):
    title: str
    scope: str

class MessageRead(ReadRecord):
    role: str
    sequence_number: int
    content: str
    details: dict

class DocumentRead(ReadRecord):
    source_id: UUID
    filename: str
    content_type: str
    checksum: str
    status: str
    details: dict
    indexed_at: AwareDatetime | None
    safe_error_message: str | None

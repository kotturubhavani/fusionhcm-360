from uuid import UUID
from pydantic import AwareDatetime
from app.schemas.core_hr import ReadRecord


class JobRead(ReadRecord):
    object_type: str
    original_filename: str
    status: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    processed_rows: int
    failed_rows: int
    created_by_user_id: UUID | None
    validated_at: AwareDatetime | None
    processed_at: AwareDatetime | None


class RowRead(ReadRecord):
    import_job_id: UUID
    row_number: int
    raw_data: dict
    normalized_data: dict | None
    status: str
    error_code: str | None
    error_message: str | None
    created_record_reference: dict | None

"""Dated base compensation, independent of organizational history."""
from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.worker import WorkerTimestamps


class AssignmentCompensation(WorkerTimestamps, Base):
    __tablename__ = 'assignment_compensation'
    __table_args__ = (
        UniqueConstraint('assignment_id', 'effective_from', name='uq_assignment_compensation_assignment_from'),
        CheckConstraint('effective_to IS NULL OR effective_to >= effective_from', name='ck_assignment_compensation_dates'),
        CheckConstraint('annual_base_salary >= 0', name='ck_assignment_compensation_salary'),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name='ck_assignment_compensation_currency'),
    )
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    assignment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey('assignments.id', name='fk_assignment_compensation_assignment', ondelete='RESTRICT'), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    annual_base_salary: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    assignment = relationship('Assignment', back_populates='compensation_history')

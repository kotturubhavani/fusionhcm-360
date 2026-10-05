"""Worker identity and employment episodes."""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.assignment import Assignment
    from app.models.reference import LegalEmployer
    from app.models.user import User


class WorkerTimestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class Person(WorkerTimestamps, Base):
    __tablename__ = "persons"
    __table_args__ = (
        UniqueConstraint("person_number", name="uq_persons_person_number"),
        CheckConstraint("person_number ~ '[^[:space:]]' AND person_number = upper(btrim(person_number))", name="ck_persons_person_number"),
        CheckConstraint("first_name ~ '[^[:space:]]'", name="ck_persons_first_name"),
        CheckConstraint("last_name ~ '[^[:space:]]'", name="ck_persons_last_name"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    person_number: Mapped[str] = mapped_column(String(30), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    preferred_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    personal_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # Keep loaded dependents intact on delete so PostgreSQL enforces RESTRICT.
    work_relationships: Mapped[list[WorkRelationship]] = relationship(back_populates="person", passive_deletes="all")
    user: Mapped[User | None] = relationship("User", back_populates="person", uselist=False, passive_deletes="all")

    @validates("person_number", "first_name", "last_name")
    def normalize_required(self, key: str, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"{key} must not be blank")
        return value.upper() if key == "person_number" else value

    @validates("preferred_name", "personal_email")
    def normalize_optional(self, key: str, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return value.lower() if key == "personal_email" else value


class WorkRelationship(WorkerTimestamps, Base):
    __tablename__ = "work_relationships"
    __table_args__ = (
        UniqueConstraint("person_id", "legal_employer_id", "start_date", name="uq_work_relationships_person_employer_start"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_work_relationships_dates"),
        CheckConstraint("employment_type IN ('REGULAR', 'FIXED_TERM', 'INTERN')", name="ck_work_relationships_employment_type"),
        Index("ix_work_relationships_employer_start", "legal_employer_id", "start_date"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    person_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("persons.id", name="fk_work_relationships_person", ondelete="RESTRICT"), nullable=False)
    legal_employer_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("legal_employers.id", name="fk_work_relationships_legal_employer", ondelete="RESTRICT"), nullable=False)
    employment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    person: Mapped[Person] = relationship(back_populates="work_relationships")
    legal_employer: Mapped[LegalEmployer] = relationship("LegalEmployer")

    assignments: Mapped[list[Assignment]] = relationship("Assignment", back_populates="work_relationship", passive_deletes="all")

"""Assignment identity and dated organizational details; no compensation or services."""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.database import Base
from app.models.worker import WorkerTimestamps

if TYPE_CHECKING:
    from app.models.reference import BusinessUnit, Department, Grade, Job, Location
    from app.models.worker import WorkRelationship


class Assignment(WorkerTimestamps, Base):
    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint("assignment_number", name="uq_assignments_assignment_number"),
        CheckConstraint("assignment_number ~ '[^[:space:]]' AND assignment_number = upper(btrim(assignment_number))", name="ck_assignments_assignment_number"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_assignments_dates"),
        Index("ix_assignments_relationship_start", "work_relationship_id", "start_date"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    work_relationship_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("work_relationships.id", name="fk_assignments_work_relationship", ondelete="RESTRICT"), nullable=False,
    )
    assignment_number: Mapped[str] = mapped_column(String(30), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    work_relationship: Mapped[WorkRelationship] = relationship("WorkRelationship", back_populates="assignments")
    versions: Mapped[list[AssignmentVersion]] = relationship(
        back_populates="assignment", foreign_keys="AssignmentVersion.assignment_id", passive_deletes="all",
    )
    manager_versions: Mapped[list[AssignmentVersion]] = relationship(
        back_populates="manager_assignment", foreign_keys="AssignmentVersion.manager_assignment_id", passive_deletes="all",
    )

    @validates("assignment_number")
    def normalize_number(self, key: str, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("assignment_number must not be blank")
        return value


class AssignmentVersion(WorkerTimestamps, Base):
    __tablename__ = "assignment_versions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "effective_from", name="uq_assignment_versions_assignment_from"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_assignment_versions_dates"),
        CheckConstraint("manager_assignment_id IS NULL OR manager_assignment_id <> assignment_id", name="ck_assignment_versions_manager"),
        CheckConstraint("status IN ('ACTIVE', 'ON_LEAVE', 'SUSPENDED')", name="ck_assignment_versions_status"),
        CheckConstraint("work_time_type IN ('FULL_TIME', 'PART_TIME')", name="ck_assignment_versions_work_time_type"),
        ForeignKeyConstraint(
            ["department_id", "business_unit_id"], ["departments.id", "departments.business_unit_id"],
            name="fk_assignment_versions_department_business_unit", ondelete="RESTRICT",
        ),
        Index("ix_assignment_versions_business_unit_from", "business_unit_id", "effective_from"),
        Index("ix_assignment_versions_department_business_unit", "department_id", "business_unit_id"),
        Index("ix_assignment_versions_job", "job_id"),
        Index("ix_assignment_versions_grade", "grade_id"),
        Index("ix_assignment_versions_location", "location_id"),
        Index("ix_assignment_versions_manager", "manager_assignment_id", postgresql_where=text("manager_assignment_id IS NOT NULL")),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    assignment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("assignments.id", name="fk_assignment_versions_assignment", ondelete="RESTRICT"), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    business_unit_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("business_units.id", name="fk_assignment_versions_business_unit", ondelete="RESTRICT"), nullable=False)
    department_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("jobs.id", name="fk_assignment_versions_job", ondelete="RESTRICT"), nullable=False)
    grade_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("grades.id", name="fk_assignment_versions_grade", ondelete="RESTRICT"), nullable=True)
    location_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("locations.id", name="fk_assignment_versions_location", ondelete="RESTRICT"), nullable=False)
    manager_assignment_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("assignments.id", name="fk_assignment_versions_manager", ondelete="RESTRICT"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    work_time_type: Mapped[str] = mapped_column(String(20), nullable=False)

    assignment: Mapped[Assignment] = relationship(back_populates="versions", foreign_keys=[assignment_id])
    manager_assignment: Mapped[Assignment | None] = relationship(back_populates="manager_versions", foreign_keys=[manager_assignment_id])
    business_unit: Mapped[BusinessUnit] = relationship("BusinessUnit", foreign_keys=[business_unit_id])
    # Match both ownership columns on reads; only department_id is synchronized on writes.
    # business_unit is explicitly supplied, so mismatches reach the database constraint.
    department: Mapped[Department] = relationship(
        "Department",
        primaryjoin="and_(AssignmentVersion.department_id == Department.id, AssignmentVersion.business_unit_id == Department.business_unit_id)",
        foreign_keys=[department_id],
    )
    job: Mapped[Job] = relationship("Job")
    grade: Mapped[Grade | None] = relationship("Grade")
    location: Mapped[Location] = relationship("Location")

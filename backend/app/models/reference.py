"""Core HR reference data. Worker and compensation models are added separately."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.database import Base


def _reference_constraints(table: str, *, department: bool = False, country: bool = False):
    constraints = [
        CheckConstraint("code ~ '[^[:space:]]' AND code = upper(btrim(code))", name=f"ck_{table}_code"),
        CheckConstraint("name ~ '[^[:space:]]'", name=f"ck_{table}_name"),
        UniqueConstraint(*(["business_unit_id", "code"] if department else ["code"]), name=f"uq_{table}_code"),
    ]
    if country:
        constraints.append(CheckConstraint("country_code ~ '^[A-Z]{2}$'", name=f"ck_{table}_country_code"))
    return tuple(constraints)


class ReferenceFields:
    """Common columns; no database table of its own."""

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    @validates("code", "name")
    def normalize_label(self, key: str, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"{key} must not be blank")
        return value.upper() if key == "code" else value


class CountryFields:
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)

    @validates("country_code")
    def normalize_country(self, key: str, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 2 or not value.isascii() or not value.isalpha():
            raise ValueError("country_code must contain two ASCII letters")
        return value


class LegalEmployer(ReferenceFields, CountryFields, Base):
    __tablename__ = "legal_employers"
    __table_args__ = _reference_constraints(__tablename__, country=True)


class BusinessUnit(ReferenceFields, Base):
    __tablename__ = "business_units"
    __table_args__ = _reference_constraints(__tablename__)

    departments: Mapped[list["Department"]] = relationship(back_populates="business_unit", passive_deletes="all")


class Department(ReferenceFields, Base):
    __tablename__ = "departments"
    __table_args__ = (
        *_reference_constraints(__tablename__, department=True),
        # Target key for the approved future assignment department/BU ownership FK.
        UniqueConstraint("id", "business_unit_id", name="uq_departments_id_business_unit"),
    )

    business_unit_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("business_units.id", name="fk_departments_business_unit", ondelete="RESTRICT"),
        nullable=False,
    )
    business_unit: Mapped[BusinessUnit] = relationship(back_populates="departments")


class Job(ReferenceFields, Base):
    __tablename__ = "jobs"
    __table_args__ = _reference_constraints(__tablename__)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Grade(ReferenceFields, Base):
    __tablename__ = "grades"
    __table_args__ = _reference_constraints(__tablename__)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Location(ReferenceFields, CountryFields, Base):
    __tablename__ = "locations"
    __table_args__ = _reference_constraints(__tablename__, country=True)

    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address_line: Mapped[str | None] = mapped_column(String(255), nullable=True)

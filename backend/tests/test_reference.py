"""PostgreSQL integration tests: migrate first, then run from backend/ with
python -m pytest tests/test_reference.py. Every test rolls its inserts back.
No seeds, DDL, or auth mutations are performed by this suite.
"""
from uuid import uuid4

import pytest
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import BusinessUnit, Department, Grade, Job, LegalEmployer, Location

MODELS = [LegalEmployer, BusinessUnit, Department, Job, Grade, Location]


@pytest.fixture
def connection():
    with engine.connect() as conn:
        assert conn.dialect.name == "postgresql"
        transaction = conn.begin()
        try:
            yield conn
        finally:
            transaction.rollback()


def values(conn, model):
    result = {"code": "TEST_" + uuid4().hex[:20].upper(), "name": "Corporate Functions"}
    if model in (LegalEmployer, Location):
        result["country_code"] = "IN"
    if model is Department:
        result["business_unit_id"] = conn.execute(
            BusinessUnit.__table__.insert().values(**values(conn, BusinessUnit)).returning(BusinessUnit.id)
        ).scalar_one()
    return result


def reject(conn, statement, *, sqlstate, constraint=None):
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(statement)
    assert error.value.orig.sqlstate == sqlstate
    if constraint:
        assert error.value.orig.diag.constraint_name == constraint


@pytest.mark.parametrize("model", MODELS)
def test_schema(connection, model):
    inspector = inspect(connection)
    table = model.__tablename__
    columns = {c["name"]: c for c in inspector.get_columns(table)}
    required = {"id", "code", "name", "is_active", "created_at", "updated_at"}
    optional = set()
    if model in (LegalEmployer, Location):
        required.add("country_code")
    if model is Department:
        required.add("business_unit_id")
    if model in (Job, Grade):
        optional.add("description")
    if model is Location:
        optional.update({"city", "address_line"})
    assert set(columns) == required | optional
    assert all(not columns[name]["nullable"] for name in required)
    assert all(columns[name]["nullable"] for name in optional)
    assert inspector.get_pk_constraint(table)["constrained_columns"] == ["id"]
    assert str(columns["id"]["type"]) == "UUID"
    assert columns["code"]["type"].length == 30
    assert columns["name"]["type"].length == 150
    for name in ("created_at", "updated_at"):
        assert columns[name]["type"].timezone
        assert columns[name]["default"] == "now()"
    assert columns["id"]["default"] == "gen_random_uuid()"
    assert columns["is_active"]["default"] == "true"
    checks = {item["name"] for item in inspector.get_check_constraints(table)}
    expected_checks = {f"ck_{table}_code", f"ck_{table}_name"}
    if model in (LegalEmployer, Location):
        expected_checks.add(f"ck_{table}_country_code")
        assert columns["country_code"]["type"].length == 2
    assert checks == expected_checks
    uniques = {item["name"]: item["column_names"] for item in inspector.get_unique_constraints(table)}
    expected_uniques = {f"uq_{table}_code": ["code"]}
    foreign_keys = inspector.get_foreign_keys(table)
    if model is Department:
        expected_uniques = {"uq_departments_code": ["business_unit_id", "code"], "uq_departments_id_business_unit": ["id", "business_unit_id"]}
        assert len(foreign_keys) == 1
        fk = foreign_keys[0]
        assert (fk["name"], fk["constrained_columns"], fk["referred_table"], fk["referred_columns"], fk["options"]["ondelete"]) == ("fk_departments_business_unit", ["business_unit_id"], "business_units", ["id"], "RESTRICT")
    else:
        assert foreign_keys == []
    assert uniques == expected_uniques
    assert all(index.get("duplicates_constraint") for index in inspector.get_indexes(table))


@pytest.mark.parametrize("model", MODELS)
def test_defaults_and_code_uniqueness(connection, model):
    table = model.__table__
    payload = values(connection, model)
    row = connection.execute(table.insert().values(**payload).returning(table)).mappings().one()
    assert row["id"] and row["is_active"] is True
    assert row["created_at"].tzinfo and row["updated_at"].tzinfo
    reject(connection, table.insert().values(**payload), sqlstate="23505", constraint=f"uq_{model.__tablename__}_code")
    # Display names are intentionally not unique.
    connection.execute(table.insert().values(**{**payload, "code": "OTHER_" + uuid4().hex[:20].upper()}))


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("field,bad", [("code", ""), ("code", " \t "), ("code", "lowercase"), ("code", " PADDED "), ("name", ""), ("name", " \t ")])
def test_named_label_checks(connection, model, field, bad):
    payload = {**values(connection, model), field: bad}
    reject(connection, model.__table__.insert().values(**payload), sqlstate="23514", constraint=f"ck_{model.__tablename__}_{field}")


@pytest.mark.parametrize("model", [LegalEmployer, Location])
@pytest.mark.parametrize("country", ["in", "I1", "", "I"])
def test_country_shape(connection, model, country):
    reject(connection, model.__table__.insert().values(**{**values(connection, model), "country_code": country}), sqlstate="23514", constraint=f"ck_{model.__tablename__}_country_code")


def test_department_ownership_and_restrict(connection):
    first = values(connection, Department)
    connection.execute(Department.__table__.insert().values(**first))
    second = {**values(connection, Department), "code": first["code"]}
    connection.execute(Department.__table__.insert().values(**second))
    reject(connection, Department.__table__.insert().values(**{**first, "business_unit_id": uuid4()}), sqlstate="23503", constraint="fk_departments_business_unit")
    reject(connection, Department.__table__.insert().values(**{**first, "business_unit_id": None}), sqlstate="23502")
    reject(connection, delete(BusinessUnit).where(BusinessUnit.id == first["business_unit_id"]), sqlstate="23503", constraint="fk_departments_business_unit")


def test_orm_normalization_updates_and_no_delete_cascade(connection):
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        unit = BusinessUnit(code="  mixed_code  ", name="  Name  ")
        department = Department(code=" team ", name=" Team ", business_unit=unit)
        employer = LegalEmployer(code=" employer ", name=" Employer ", country_code=" in ")
        session.add_all([unit, department, employer])
        session.flush()
        assert (unit.code, unit.name, department.code, employer.country_code) == ("MIXED_CODE", "Name", "TEAM", "IN")
        # Set a known older timestamp to verify the SQLAlchemy update hook.
        session.execute(text("UPDATE business_units SET updated_at = '2000-01-01' WHERE id = :id"), {"id": unit.id})
        unit.name = "Updated"
        session.flush()
        session.refresh(unit)
        assert unit.updated_at.year > 2000
        assert unit.departments == [department]
        with pytest.raises(IntegrityError) as error:
            with session.begin_nested():
                session.delete(unit)
                session.flush()
        assert error.value.orig.sqlstate == "23503"
        assert session.scalar(select(Department.id).where(Department.id == department.id)) is not None

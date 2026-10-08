"""Real PostgreSQL checks; migrate first, then python -m pytest tests/.
All inserted fixtures are rolled back; this suite does not seed or run DDL.
"""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import delete, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import Assignment, AssignmentVersion, BusinessUnit, Department, Grade, Job, LegalEmployer, Location, Person, WorkRelationship

DAY = date(2026, 1, 1)


@pytest.fixture
def connection():
    with engine.connect() as conn:
        assert conn.dialect.name == 'postgresql'
        transaction = conn.begin()
        try:
            yield conn
        finally:
            transaction.rollback()


def insert(conn, model, **values):
    return conn.execute(model.__table__.insert().values(**values).returning(model.id)).scalar_one()


def reference(conn, model, **extra):
    if model in (LegalEmployer, Location):
        extra['country_code'] = 'IN'
    return insert(conn, model, code='T' + uuid4().hex[:25].upper(), name='Corporate Functions', **extra)


def assignment_values(conn):
    person = insert(conn, Person, person_number='P' + uuid4().hex[:25].upper(), first_name='Harsha', last_name='Vardhan')
    employer = reference(conn, LegalEmployer)
    relationship = insert(conn, WorkRelationship, person_id=person, legal_employer_id=employer, employment_type='REGULAR', start_date=DAY)
    return dict(work_relationship_id=relationship, assignment_number='A' + uuid4().hex[:25].upper(), start_date=DAY)


def version_values(conn):
    unit = reference(conn, BusinessUnit)
    return dict(assignment_id=insert(conn, Assignment, **assignment_values(conn)), effective_from=DAY,
                business_unit_id=unit, department_id=reference(conn, Department, business_unit_id=unit),
                job_id=reference(conn, Job), location_id=reference(conn, Location), status='ACTIVE', work_time_type='FULL_TIME')


def reject(conn, statement, constraint, state='23514'):
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(statement)
    assert error.value.orig.sqlstate == state
    if constraint:
        assert error.value.orig.diag.constraint_name == constraint


def test_assignment_defaults_uniqueness_and_relationship_restrict(connection):
    payload = assignment_values(connection)
    row = connection.execute(Assignment.__table__.insert().values(**payload).returning(Assignment.__table__)).mappings().one()
    assert row['id'] and row['end_date'] is None and row['created_at'].tzinfo and row['updated_at'].tzinfo
    reject(connection, Assignment.__table__.insert().values(**payload), 'uq_assignments_assignment_number', '23505')
    reject(connection, delete(WorkRelationship).where(WorkRelationship.id == payload['work_relationship_id']), 'fk_assignments_work_relationship', '23503')
    reject(connection, Assignment.__table__.insert().values(**{**payload, 'assignment_number': 'OTHER', 'end_date': date(2025, 1, 1)}), 'ck_assignments_dates')
    reject(connection, Assignment.__table__.insert().values(**{**payload, 'assignment_number': 'OTHER', 'work_relationship_id': uuid4()}), 'fk_assignments_work_relationship', '23503')


@pytest.mark.parametrize('number', ['', ' \t\n ', 'lower', ' PADDED ', None])
def test_assignment_number_checks(connection, number):
    reject(connection, Assignment.__table__.insert().values(**{**assignment_values(connection), 'assignment_number': number}),
           None if number is None else 'ck_assignments_assignment_number', '23502' if number is None else '23514')


def test_assignment_orm_normalization(connection):
    with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
        assignment = Assignment(**{**assignment_values(connection), 'assignment_number': ' mixed_number '})
        session.add(assignment)
        session.flush()
        assert assignment.assignment_number == 'MIXED_NUMBER'
        assert assignment.work_relationship.assignments == [assignment]
        with pytest.raises(ValueError):
            assignment.assignment_number = ' '
        with pytest.raises(IntegrityError) as error:
            with session.begin_nested():
                session.delete(assignment.work_relationship)
                session.flush()
        assert error.value.orig.diag.constraint_name == 'fk_assignments_work_relationship'


@pytest.mark.parametrize('status', ['ACTIVE', 'ON_LEAVE', 'SUSPENDED'])
@pytest.mark.parametrize('work_time_type', ['FULL_TIME', 'PART_TIME'])
def test_version_valid_values_and_nullables(connection, status, work_time_type):
    payload = {**version_values(connection), 'status': status, 'work_time_type': work_time_type}
    row = connection.execute(AssignmentVersion.__table__.insert().values(**payload).returning(AssignmentVersion.__table__)).mappings().one()
    assert row['grade_id'] is None and row['manager_assignment_id'] is None and row['effective_to'] is None
    assert row['id'] and row['created_at'].tzinfo and row['updated_at'].tzinfo


@pytest.mark.parametrize('field,value', [('status', 'INVALID'), ('status', 'active'), ('status', None), ('work_time_type', 'CASUAL'), ('work_time_type', 'full_time'), ('work_time_type', None)])
def test_version_enum_checks(connection, field, value):
    reject(connection, AssignmentVersion.__table__.insert().values(**{**version_values(connection), field: value}),
           None if value is None else f'ck_assignment_versions_{field}', '23502' if value is None else '23514')


def test_version_unique_dates_self_manager_and_department_ownership(connection):
    payload = version_values(connection)
    insert(connection, AssignmentVersion, **payload)
    reject(connection, AssignmentVersion.__table__.insert().values(**payload), 'uq_assignment_versions_assignment_from', '23505')
    payload['effective_from'] = date(2026, 2, 1)
    reject(connection, AssignmentVersion.__table__.insert().values(**{**payload, 'effective_to': DAY}), 'ck_assignment_versions_dates')
    reject(connection, AssignmentVersion.__table__.insert().values(**{**payload, 'manager_assignment_id': payload['assignment_id']}), 'ck_assignment_versions_manager')
    reject(connection, AssignmentVersion.__table__.insert().values(**{**payload, 'business_unit_id': reference(connection, BusinessUnit)}), 'fk_assignment_versions_department_business_unit', '23503')
    # These table constraints allow overlaps; employment services enforce timeline rules.
    insert(connection, AssignmentVersion, **{**payload, 'effective_to': payload['effective_from']})


@pytest.mark.parametrize('model,key,constraint', [
    (BusinessUnit, 'business_unit_id', None),
    (Department, 'department_id', 'fk_assignment_versions_department_business_unit'),
    (Job, 'job_id', 'fk_assignment_versions_job'),
    (Grade, 'grade_id', 'fk_assignment_versions_grade'),
    (Location, 'location_id', 'fk_assignment_versions_location'),
    (Assignment, 'assignment_id', 'fk_assignment_versions_assignment'),
    (Assignment, 'manager_assignment_id', 'fk_assignment_versions_manager'),
])
def test_referenced_deletes_restricted(connection, model, key, constraint):
    payload = version_values(connection)
    payload['grade_id'] = reference(connection, Grade)
    payload['manager_assignment_id'] = insert(connection, Assignment, **assignment_values(connection))
    insert(connection, AssignmentVersion, **payload)
    reject(connection, delete(model).where(model.id == payload[key]), constraint, '23503')


@pytest.mark.parametrize('key', ['assignment_id', 'business_unit_id', 'department_id', 'job_id', 'grade_id', 'location_id', 'manager_assignment_id'])
def test_version_missing_parents(connection, key):
    reject(connection, AssignmentVersion.__table__.insert().values(**{**version_values(connection), key: uuid4()}), None, '23503')


def test_orm_links_and_department_write_conflict(connection):
    payload = version_values(connection)
    grade_id = reference(connection, Grade)
    manager_id = insert(connection, Assignment, **assignment_values(connection))
    with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
        version = AssignmentVersion(effective_from=DAY, status='ACTIVE', work_time_type='FULL_TIME',
            assignment=session.get(Assignment, payload['assignment_id']),
            business_unit=session.get(BusinessUnit, payload['business_unit_id']),
            department=session.get(Department, payload['department_id']),
            job=session.get(Job, payload['job_id']), grade=session.get(Grade, grade_id),
            location=session.get(Location, payload['location_id']), manager_assignment=session.get(Assignment, manager_id))
        session.add(version)
        session.flush()
        session.expire_all()
        assert version.assignment.versions == [version]
        assert version.manager_assignment.manager_versions == [version]
        assert version.department.business_unit_id == version.business_unit.id
        assert version.job.id == payload['job_id'] and version.grade.id == grade_id and version.location.id == payload['location_id']
        for parent in [version.assignment, version.manager_assignment]:
            with pytest.raises(IntegrityError) as error:
                with session.begin_nested():
                    session.delete(parent)
                    session.flush()
            assert error.value.orig.sqlstate == '23503'
        other_unit_id = reference(connection, BusinessUnit)
        with pytest.raises(IntegrityError) as error:
            with session.begin_nested():
                version.business_unit = session.get(BusinessUnit, other_unit_id)
                session.flush()
        assert error.value.orig.diag.constraint_name == 'fk_assignment_versions_department_business_unit'


def test_exact_schema_constraints_and_indexes(connection):
    inspector = inspect(connection)
    expected_columns = {
        'assignments': {'id', 'work_relationship_id', 'assignment_number', 'start_date', 'end_date', 'created_at', 'updated_at'},
        'assignment_versions': {'id', 'assignment_id', 'effective_from', 'effective_to', 'business_unit_id', 'department_id', 'job_id', 'grade_id', 'location_id', 'manager_assignment_id', 'status', 'work_time_type', 'created_at', 'updated_at'},
    }
    for table, names in expected_columns.items():
        cols = {c['name']: c for c in inspector.get_columns(table)}
        assert set(cols) == names
        assert {c['name'] for c in cols.values() if c['nullable']} == ({'end_date'} if table == 'assignments' else {'effective_to', 'grade_id', 'manager_assignment_id'})
        assert cols['id']['default'] == 'gen_random_uuid()'
        assert inspector.get_pk_constraint(table)['constrained_columns'] == ['id']
        for name in ['created_at', 'updated_at']:
            assert cols[name]['default'] == 'now()' and cols[name]['type'].timezone
        assert all(f['options']['ondelete'] == 'RESTRICT' for f in inspector.get_foreign_keys(table))
    assert {c['name'] for c in inspector.get_check_constraints('assignments')} == {'ck_assignments_assignment_number', 'ck_assignments_dates'}
    assert {c['name'] for c in inspector.get_check_constraints('assignment_versions')} == {'ck_assignment_versions_dates', 'ck_assignment_versions_manager', 'ck_assignment_versions_status', 'ck_assignment_versions_work_time_type'}
    assert [u['column_names'] for u in inspector.get_unique_constraints('assignments')] == [['assignment_number']]
    assert [u['column_names'] for u in inspector.get_unique_constraints('assignment_versions')] == [['assignment_id', 'effective_from']]
    fks = {tuple(f['constrained_columns']): (f['referred_table'], f['referred_columns']) for f in inspector.get_foreign_keys('assignment_versions')}
    assert fks == {('assignment_id',): ('assignments', ['id']), ('business_unit_id',): ('business_units', ['id']), ('department_id', 'business_unit_id'): ('departments', ['id', 'business_unit_id']), ('job_id',): ('jobs', ['id']), ('grade_id',): ('grades', ['id']), ('location_id',): ('locations', ['id']), ('manager_assignment_id',): ('assignments', ['id'])}
    indexes = [i for i in inspector.get_indexes('assignments') if not i.get('duplicates_constraint')]
    assert [(i['name'], i['column_names']) for i in indexes] == [('ix_assignments_relationship_start', ['work_relationship_id', 'start_date'])]
    indexes = {i['name']: i for i in inspector.get_indexes('assignment_versions') if not i.get('duplicates_constraint')}
    assert {name: i['column_names'] for name, i in indexes.items()} == {
        'ix_assignment_versions_business_unit_from': ['business_unit_id', 'effective_from'],
        'ix_assignment_versions_department_business_unit': ['department_id', 'business_unit_id'],
        'ix_assignment_versions_job': ['job_id'], 'ix_assignment_versions_grade': ['grade_id'],
        'ix_assignment_versions_location': ['location_id'], 'ix_assignment_versions_manager': ['manager_assignment_id'],
    }
    assert not any(i['unique'] for i in indexes.values())
    assert indexes['ix_assignment_versions_manager']['dialect_options']['postgresql_where'].strip('()') == 'manager_assignment_id IS NOT NULL'

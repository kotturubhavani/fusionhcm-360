"""PostgreSQL worker tests. Run after upgrade: python -m pytest tests/.
All fixture data, including auth service commits, stays inside rolled-back transactions.
"""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import delete, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import LegalEmployer, Person, User, WorkRelationship
from app.schemas.auth import RegisterRequest, UserResponse
from app.services.auth import authenticate_user, register_user


@pytest.fixture
def connection():
    with engine.connect() as conn:
        assert conn.dialect.name == "postgresql"
        transaction = conn.begin()
        try:
            yield conn
        finally:
            transaction.rollback()


def person_values():
    return dict(person_number="P" + uuid4().hex[:25].upper(), first_name="Harsha", last_name="Vardhan")


def insert_person(conn):
    return conn.execute(Person.__table__.insert().values(**person_values()).returning(Person.id)).scalar_one()


def relationship_values(conn):
    employer_id = conn.execute(LegalEmployer.__table__.insert().values(
        code="L" + uuid4().hex[:25].upper(), name="Asterion Digital Technologies Pvt. Ltd.", country_code="IN"
    ).returning(LegalEmployer.id)).scalar_one()
    return dict(person_id=insert_person(conn), legal_employer_id=employer_id, employment_type="REGULAR", start_date=date(2026, 1, 1))


def user_values():
    return dict(email=f"{uuid4().hex}@example.com", password_hash="test-only-placeholder", first_name="Naveen", last_name="Chandra")


def reject(conn, statement, state, constraint=None):
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(statement)
    assert error.value.orig.sqlstate == state
    if constraint:
        assert error.value.orig.diag.constraint_name == constraint


def test_person_valid_defaults_optional_and_uniqueness(connection):
    payload = person_values()
    row = connection.execute(Person.__table__.insert().values(**payload).returning(Person.__table__)).mappings().one()
    assert row['id'] and row['is_active'] is True
    assert row['created_at'].tzinfo and row['updated_at'].tzinfo
    for field in ('preferred_name', 'personal_email', 'date_of_birth', 'phone'):
        assert row[field] is None
    reject(connection, Person.__table__.insert().values(**payload), '23505', 'uq_persons_person_number')


@pytest.mark.parametrize('field', ['person_number', 'first_name', 'last_name'])
@pytest.mark.parametrize('value', ['', ' \t\n ', None])
def test_person_required_labels(connection, field, value):
    reject(connection, Person.__table__.insert().values(**{**person_values(), field: value}),
           '23502' if value is None else '23514', None if value is None else f'ck_persons_{field}')


@pytest.mark.parametrize('number', ['lowercase', ' PADDED '])
def test_person_number_database_normalization_guard(connection, number):
    reject(connection, Person.__table__.insert().values(**{**person_values(), 'person_number': number}), '23514', 'ck_persons_person_number')


def test_person_orm_normalization(connection):
    with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
        person = Person(person_number=' test_person ', first_name=' First ', last_name=' Last ',
                        preferred_name=' Preferred ', personal_email=' TEST@EXAMPLE.COM ',
                        date_of_birth=date(1990, 1, 1), phone='+91 0000000000')
        session.add(person)
        session.flush()
        session.refresh(person)
        assert (person.person_number, person.first_name, person.last_name, person.preferred_name, person.personal_email) == ('TEST_PERSON', 'First', 'Last', 'Preferred', 'test@example.com')
        assert person.user is None and person.work_relationships == []
        person.preferred_name = ' '
        person.personal_email = None
        session.flush()
        assert person.preferred_name is None and person.personal_email is None
        with pytest.raises(ValueError):
            person.first_name = ' '


@pytest.mark.parametrize('employment_type', ['REGULAR', 'FIXED_TERM', 'INTERN'])
def test_relationship_valid_types_and_dates(connection, employment_type):
    payload = {**relationship_values(connection), 'employment_type': employment_type}
    row = connection.execute(WorkRelationship.__table__.insert().values(**payload).returning(WorkRelationship.__table__)).mappings().one()
    assert row['id'] and row['created_at'].tzinfo and row['updated_at'].tzinfo
    assert row['end_date'] is None and row['termination_reason'] is None
    connection.execute(WorkRelationship.__table__.update().where(WorkRelationship.id == row['id']).values(end_date=payload['start_date']))


@pytest.mark.parametrize('employment_type', ['CONTRACTOR', 'regular', '', None])
def test_invalid_employment_type(connection, employment_type):
    reject(connection, WorkRelationship.__table__.insert().values(**{**relationship_values(connection), 'employment_type': employment_type}),
           '23502' if employment_type is None else '23514', None if employment_type is None else 'ck_work_relationships_employment_type')


def test_relationship_duplicate_and_date_order(connection):
    payload = relationship_values(connection)
    connection.execute(WorkRelationship.__table__.insert().values(**payload))
    reject(connection, WorkRelationship.__table__.insert().values(**payload), '23505', 'uq_work_relationships_person_employer_start')
    reject(connection, WorkRelationship.__table__.insert().values(**{**payload, 'start_date': date(2027, 1, 1), 'end_date': date(2026, 1, 1)}), '23514', 'ck_work_relationships_dates')
    # Rehire keeps the same person identity; employment services enforce overlap rules.
    connection.execute(WorkRelationship.__table__.insert().values(**{**payload, 'start_date': date(2027, 1, 1)}))


@pytest.mark.parametrize('field,constraint', [('person_id', 'fk_work_relationships_person'), ('legal_employer_id', 'fk_work_relationships_legal_employer')])
def test_relationship_missing_parent(connection, field, constraint):
    reject(connection, WorkRelationship.__table__.insert().values(**{**relationship_values(connection), field: uuid4()}), '23503', constraint)


def test_relationship_delete_restrictions_and_orm(connection):
    payload = relationship_values(connection)
    relationship_id = connection.execute(WorkRelationship.__table__.insert().values(**payload).returning(WorkRelationship.id)).scalar_one()
    reject(connection, delete(Person).where(Person.id == payload['person_id']), '23503', 'fk_work_relationships_person')
    reject(connection, delete(LegalEmployer).where(LegalEmployer.id == payload['legal_employer_id']), '23503', 'fk_work_relationships_legal_employer')
    with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
        relationship = session.get(WorkRelationship, relationship_id)
        person = relationship.person
        assert person.work_relationships == [relationship]
        assert relationship.legal_employer.id == payload['legal_employer_id']
        with pytest.raises(IntegrityError) as error:
            with session.begin_nested():
                session.delete(person)
                session.flush()
        assert error.value.orig.diag.constraint_name == 'fk_work_relationships_person'
        assert session.get(WorkRelationship, relationship_id) is not None


def test_nullable_unique_user_link_and_delete_restriction(connection):
    connection.execute(User.__table__.insert().values(**user_values()))
    connection.execute(User.__table__.insert().values(**user_values()))
    person_id = insert_person(connection)
    user_id = connection.execute(User.__table__.insert().values(**user_values(), person_id=person_id).returning(User.id)).scalar_one()
    reject(connection, User.__table__.insert().values(**user_values(), person_id=person_id), '23505', 'uq_users_person_id')
    reject(connection, User.__table__.insert().values(**user_values(), person_id=uuid4()), '23503', 'fk_users_person')
    reject(connection, delete(Person).where(Person.id == person_id), '23503', 'fk_users_person')
    with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
        user = session.get(User, user_id)
        assert user.person.id == person_id and user.person.user is user
        with pytest.raises(IntegrityError) as error:
            with session.begin_nested():
                session.delete(user.person)
                session.flush()
        assert error.value.orig.diag.constraint_name == 'fk_users_person'
        session.delete(user)
        session.flush()
        assert session.get(Person, person_id) is not None


def test_existing_auth_flow_without_person_and_no_email_link(connection):
    with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
        email = f'{uuid4().hex}@example.com'
        session.add(Person(**person_values(), personal_email=email))
        session.flush()
        user = register_user(session, RegisterRequest(email=email, password='TestOnly!Password123', first_name='Naveen', last_name='Chandra'))
        assert user.person_id is None and user.person is None
        assert authenticate_user(session, email, 'TestOnly!Password123').id == user.id
        response = UserResponse.model_validate(user)
        assert response.roles == ['EMPLOYEE']
        assert 'person_id' not in response.model_dump()


def test_exact_worker_schema_and_index(connection):
    inspector = inspect(connection)
    expected = {
        'persons': {'id', 'person_number', 'first_name', 'last_name', 'preferred_name', 'date_of_birth', 'personal_email', 'phone', 'created_at', 'updated_at', 'is_active'},
        'work_relationships': {'id', 'person_id', 'legal_employer_id', 'employment_type', 'start_date', 'end_date', 'termination_reason', 'created_at', 'updated_at'},
    }
    for table, names in expected.items():
        columns = {c['name']: c for c in inspector.get_columns(table)}
        assert set(columns) == names
        assert columns['id']['default'] == 'gen_random_uuid()'
        assert inspector.get_pk_constraint(table)['constrained_columns'] == ['id']
        optional = {'preferred_name', 'date_of_birth', 'personal_email', 'phone'} if table == 'persons' else {'end_date', 'termination_reason'}
        assert {c['name'] for c in columns.values() if c['nullable']} == optional
        for field in ('created_at', 'updated_at'):
            assert columns[field]['type'].timezone and columns[field]['default'] == 'now()'
    assert {c['name'] for c in inspector.get_check_constraints('persons')} == {'ck_persons_person_number', 'ck_persons_first_name', 'ck_persons_last_name'}
    assert {c['name'] for c in inspector.get_check_constraints('work_relationships')} == {'ck_work_relationships_dates', 'ck_work_relationships_employment_type'}
    indexes = [i for i in inspector.get_indexes('work_relationships') if not i.get('duplicates_constraint')]
    assert [(i['name'], i['column_names'], i['unique']) for i in indexes] == [('ix_work_relationships_employer_start', ['legal_employer_id', 'start_date'], False)]
    assert [(u['name'], u['column_names']) for u in inspector.get_unique_constraints('work_relationships')] == [('uq_work_relationships_person_employer_start', ['person_id', 'legal_employer_id', 'start_date'])]
    for table, expected_fk in [('work_relationships', {'person_id': 'persons', 'legal_employer_id': 'legal_employers'}), ('users', {'person_id': 'persons'})]:
        fks = inspector.get_foreign_keys(table)
        assert {f['constrained_columns'][0]: f['referred_table'] for f in fks} == expected_fk
        assert all(f['options']['ondelete'] == 'RESTRICT' and f['referred_columns'] == ['id'] for f in fks)
    assert next(c for c in inspector.get_columns('users') if c['name'] == 'person_id')['nullable']
    assert any(u['name'] == 'uq_users_person_id' and u['column_names'] == ['person_id'] for u in inspector.get_unique_constraints('users'))

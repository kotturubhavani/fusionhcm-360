"""PostgreSQL service/API regression tests; every fixture rolls back."""
from datetime import date
from decimal import Decimal
from uuid import uuid4
import warnings
import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
# Known upstream TestClient deprecation only; all other warnings remain errors.
with warnings.catch_warnings():
    warnings.filterwarnings('ignore', message='Using `httpx` with `starlette.testclient` is deprecated.*')
    from fastapi.testclient import TestClient
from app import models as m
from app.core.database import engine, get_db
from app.core.security import create_access_token
from app.main import app
from app.schemas import core_hr as s
from app.services.core_hr import employment as e, records, queries
from app.services.core_hr.common import Conflict, InvalidOperation
from app.services.core_hr.seed import seed_demo

START = date(2024, 1, 1)
CHANGE = date(2025, 1, 1)


@pytest.fixture
def db():
    with engine.connect() as connection:
        assert connection.dialect.name == 'postgresql'
        tx = connection.begin()
        with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
            yield session
        tx.rollback()


@pytest.fixture
def refs(db):
    def create(model, **kwargs):
        contract = s.REFERENCE_SCHEMAS[model.__name__][0]
        return records.create_reference(db, model, contract(code=uuid4().hex[:24], name='Digital Engineering', **kwargs))
    bu = create(m.BusinessUnit)
    return dict(legal_employer_id=create(m.LegalEmployer, country_code='IN').id,
        business_unit_id=bu.id, department_id=create(m.Department, business_unit_id=bu.id).id,
        job_id=create(m.Job).id, grade_id=create(m.Grade).id, location_id=create(m.Location, country_code='IN').id)


def request(refs, **kwargs):
    data = dict(person=s.PersonCreate(person_number=uuid4().hex[:24], first_name='Nikhil', last_name='Varma'),
        assignment_number=uuid4().hex[:24], employment_type='REGULAR', joining_date=START,
        work_time_type='FULL_TIME', annual_base_salary='100000.25', currency='inr', **refs)
    data.update(kwargs)
    return s.HireRequest(**data)


def version(result, **kwargs):
    return s.AssignmentVersionCreate(**{**{k: getattr(result.version, k) for k in s.VersionDetails.model_fields}, 'effective_from': CHANGE, **kwargs})


def counts(db):
    return {model.__tablename__: db.scalar(select(func.count()).select_from(model)) for model in [m.Person, m.WorkRelationship, m.Assignment, m.AssignmentVersion, m.AssignmentCompensation]}


def test_hire_atomic_and_as_of(db, refs):
    result = e.hire(db, request(refs))
    assert result.compensation.annual_base_salary == Decimal('100000.25')
    assert queries.worker_summary(db, result.person.id, date(2023, 1, 1)).placements == []
    current = queries.worker_summary(db, result.person.id, START)
    assert len(current.placements) == 1
    assert current.placements[0].department.id == refs['department_id']
    assert current.placements[0].compensation.currency == 'INR'
    assert db.scalar(select(m.User.id).where(m.User.person_id == result.person.id)) is None


def test_hire_rolls_back_everything_on_late_failure(db, refs):
    before = counts(db)
    other = records.create_reference(db, m.BusinessUnit, s.BusinessUnitCreate(code='OTHER', name='Other'))
    with pytest.raises(InvalidOperation):
        e.hire(db, request(refs, business_unit_id=other.id))
    assert counts(db) == before
    # A failure in the final compensation step also rolls back prior nested operations.
    from unittest.mock import patch
    with patch.object(e, 'change_compensation', side_effect=InvalidOperation('test failure')):
        with pytest.raises(InvalidOperation):
            e.hire(db, request(refs))
    assert counts(db) == before


def test_overlap_and_rehire(db, refs):
    first = e.hire(db, request(refs))
    data = request(refs, person=None, person_id=first.person.id).model_dump()
    with pytest.raises(Conflict):
        e.hire(db, s.HireRequest(**data))
    e.terminate_relationship(db, first.work_relationship.id, s.EndRequest(end_date=date(2024, 12, 31)))
    rehire = s.RehireRequest(**{k: v for k, v in data.items() if k not in ('person', 'person_id', 'joining_date')}, joining_date=CHANGE)
    second = e.rehire(db, first.person.id, rehire)
    assert second.person.person_number == first.person.person_number
    assert second.work_relationship.id != first.work_relationship.id
    assert len(e.current_relationships(db, first.person.id, CHANGE)) == 1
    assert e.relationship_status(e.get(db, m.WorkRelationship, first.work_relationship.id), CHANGE) == 'ENDED'


def test_assignment_parent_dates_and_immutable_contracts(db, refs):
    result = e.hire(db, request(refs, end_date=date(2026, 1, 1)))
    for start, end in [(date(2023, 1, 1), date(2024, 1, 1)), (START, None), (START, date(2027, 1, 1))]:
        with pytest.raises(InvalidOperation):
            e.create_assignment(db, s.AssignmentCreate(work_relationship_id=result.work_relationship.id, assignment_number=uuid4().hex[:24], start_date=start, end_date=end))
    with pytest.raises(ValidationError):
        s.PersonUpdate(person_number='NEW')
    with pytest.raises(ValidationError):
        s.AssignmentVersionCreate(**{**version(result).model_dump(), 'assignment_number': 'NEW'})


def test_history_continuity_salary_and_boundaries(db, refs):
    result = e.hire(db, request(refs))
    e.change_version(db, result.assignment.id, version(result, status='ON_LEAVE'))
    e.change_compensation(db, result.assignment.id, s.AssignmentCompensationCreate(effective_from=CHANGE, annual_base_salary='123456.78', currency='usd'))
    assert e.current_version(db, result.assignment.id, date(2024, 12, 31)).status == 'ACTIVE'
    assert e.current_version(db, result.assignment.id, CHANGE).status == 'ON_LEAVE'
    assert e.current_compensation(db, result.assignment.id, CHANGE).annual_base_salary == Decimal('123456.78')
    for at in [START, CHANGE, date(2024, 6, 1)]:
        with pytest.raises(Conflict):
            e.change_version(db, result.assignment.id, version(result, effective_from=at))
        with pytest.raises(Conflict):
            e.change_compensation(db, result.assignment.id, s.AssignmentCompensationCreate(effective_from=at, annual_base_salary='1', currency='INR'))
    e.terminate_relationship(db, result.work_relationship.id, s.EndRequest(end_date=date(2025, 12, 31), reason='End of fixed-term contract'))
    assert queries.worker_summary(db, result.person.id, date(2026, 1, 1)).placements == []
    assert e.current_compensation(db, result.assignment.id, date(2026, 1, 1)) is None
    assert e.get(db, m.Assignment, result.assignment.id).end_date == date(2025, 12, 31)


def test_initial_history_and_scheduled_termination(db, refs):
    result = e.hire(db, request(refs))
    assignment = e.create_assignment(db, s.AssignmentCreate(work_relationship_id=result.work_relationship.id, assignment_number='EXTRA', start_date=START))
    with pytest.raises(InvalidOperation):
        e.change_version(db, assignment.id, version(result))
    with pytest.raises(InvalidOperation):
        e.change_compensation(db, assignment.id, s.AssignmentCompensationCreate(effective_from=CHANGE, annual_base_salary='1', currency='INR'))
    e.change_version(db, result.assignment.id, version(result))
    with pytest.raises(Conflict):
        e.terminate_relationship(db, result.work_relationship.id, s.EndRequest(end_date=date(2024, 12, 31)))
    assert e.get(db, m.Assignment, result.assignment.id).end_date is None


def test_manager_self_cycle_same_person_and_period(db, refs):
    lead = e.hire(db, request(refs))
    child = e.hire(db, request(refs, manager_assignment_id=lead.assignment.id))
    with pytest.raises(InvalidOperation):
        e.change_version(db, lead.assignment.id, version(lead, manager_assignment_id=lead.assignment.id))
    with pytest.raises(InvalidOperation):
        e.change_version(db, lead.assignment.id, version(lead, manager_assignment_id=child.assignment.id))
    with pytest.raises(InvalidOperation):
        e.change_version(db, lead.assignment.id, version(lead, status='SUSPENDED'))
    with pytest.raises(InvalidOperation):
        e.end_assignment(db, lead.assignment.id, s.EndRequest(end_date=date(2025, 12, 31)))
    other = e.create_assignment(db, s.AssignmentCreate(work_relationship_id=lead.work_relationship.id, assignment_number='SECOND', start_date=START))
    with pytest.raises(InvalidOperation):
        e.change_version(db, other.id, version(lead, effective_from=START, manager_assignment_id=lead.assignment.id))
    assert e.current_version(db, lead.assignment.id, CHANGE).manager_assignment_id is None


@pytest.mark.parametrize('field,value', [('annual_base_salary', Decimal('-1')), ('currency', 'inr'), ('currency', 'I1R'), ('effective_to', date(2023, 1, 1))])
def test_compensation_database_constraints(db, refs, field, value):
    result = e.hire(db, request(refs))
    payload = dict(assignment_id=result.assignment.id, effective_from=CHANGE, annual_base_salary=Decimal('1'), currency='INR')
    payload[field] = value
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(m.AssignmentCompensation.__table__.insert().values(**payload))


def test_compensation_unique_fk_and_index(db, refs):
    result = e.hire(db, request(refs))
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(m.AssignmentCompensation.__table__.insert().values(assignment_id=result.assignment.id, effective_from=START, annual_base_salary=1, currency='INR'))
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(delete(m.Assignment).where(m.Assignment.id == result.assignment.id))
    inspector = inspect(db.connection())
    assert all(i.get('duplicates_constraint') for i in inspector.get_indexes('assignment_compensation'))
    assert inspector.get_unique_constraints('assignment_compensation')[0]['column_names'] == ['assignment_id', 'effective_from']


@pytest.mark.parametrize('change', [{'annual_base_salary': 1.5}, {'annual_base_salary': 'NaN'}, {'annual_base_salary': '1.001'}, {'joining_date': 12345}, {'unexpected': True}, {'work_time_type': 'OTHER'}])
def test_contract_rejections(refs, change):
    with pytest.raises(ValidationError):
        request(refs, **change)


def test_reference_update_deactivate_person_and_seed(db, refs, monkeypatch):
    from app.services.core_hr import seed
    monkeypatch.setattr(seed, "PREFIX", "T" + uuid4().hex[:6].upper() + "_")
    unit = records.update_reference(db, m.BusinessUnit, refs['business_unit_id'], s.BusinessUnitUpdate(name=' Renamed ', is_active=False))
    assert unit.name == 'Renamed' and not unit.is_active
    with pytest.raises(InvalidOperation):
        e.hire(db, request(refs))
    with pytest.raises(InvalidOperation):
        records.update_reference(db, m.BusinessUnit, unit.id, s.BusinessUnitUpdate(name=None))
    assert seed_demo(db) == {'created': True, 'persons': 10}
    before = counts(db)
    assert seed_demo(db) == {'created': False, 'persons': 10}
    assert counts(db) == before


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def headers(db, role, person_id=None):
    user = m.User(email=f'{uuid4().hex}@example.com', first_name='Manoj', last_name='Kumar', password_hash='test-only', person_id=person_id)
    db.add(user)
    db.flush()
    role_id = db.scalar(select(m.Role.id).where(m.Role.name == role))
    db.add(m.UserRole(user_id=user.id, role_id=role_id))
    db.flush()
    return {'Authorization': 'Bearer ' + create_access_token(str(user.id), [role])}


@pytest.mark.parametrize('role', ['HR', 'ADMIN'])
def test_staff_api_status_codes_and_crud(client, db, refs, role):
    auth = headers(db, role)
    payload = request(refs).model_dump(mode='json')
    response = client.post('/core-hr/workers/hire', json=payload, headers=auth)
    assert response.status_code == 201, response.text
    result = response.json()
    pid = result['person']['id']
    aid = result['assignment']['id']
    assert client.get(f'/core-hr/workers/{pid}?as_of=2024-01-01', headers=auth).status_code == 200
    assert client.get('/core-hr/workers', headers=auth).status_code == 200
    assert client.patch(f'/core-hr/persons/{pid}', json={'first_name': ' Changed '}, headers=auth).json()['first_name'] == 'Changed'
    assert client.post('/core-hr/workers/hire', json=payload, headers=auth).status_code == 409
    assert client.get(f'/core-hr/persons/{uuid4()}', headers=auth).status_code == 404
    assert client.post('/core-hr/persons', json={'person_number': 'X'}, headers=auth).status_code == 422
    assert client.post(f'/core-hr/assignments/{aid}/compensation', json={'effective_from': '2025-01-01', 'annual_base_salary': '200000.00', 'currency': 'inr'}, headers=auth).status_code == 201
    unit = client.post('/core-hr/reference/business-units', json={'code': uuid4().hex[:24], 'name': 'API Unit'}, headers=auth)
    assert unit.status_code == 201
    assert client.patch('/core-hr/reference/business-units/' + unit.json()['id'], json={'is_active': False}, headers=auth).json()['is_active'] is False
    assert client.delete('/core-hr/persons/' + pid, headers=auth).status_code == 405


def test_employee_self_only(client, db, refs):
    own = e.hire(db, request(refs))
    other = e.hire(db, request(refs))
    auth = headers(db, 'EMPLOYEE', own.person.id)
    assert client.get('/core-hr/me', headers=auth).json()['person']['id'] == str(own.person.id)
    assert client.get(f'/core-hr/workers/{own.person.id}', headers=auth).status_code == 200
    assert client.get(f'/core-hr/workers/{other.person.id}', headers=auth).status_code == 403
    assert client.get(f'/core-hr/persons/{other.person.id}', headers=auth).status_code == 403
    assert client.get('/core-hr/persons', headers=auth).status_code == 403
    assert client.post('/core-hr/workers/hire', json=request(refs).model_dump(mode='json'), headers=auth).status_code == 403
    assert client.post('/core-hr/reference/jobs', json={'code': 'BLOCK', 'name': 'No'}, headers=auth).status_code == 403
    assert client.get('/core-hr/me', headers=headers(db, 'EMPLOYEE')).status_code == 404
    assert client.get('/core-hr/me').status_code == 401
    # Supplied query identity is never used to resolve self.
    assert client.get(f'/core-hr/me?person_id={other.person.id}', headers=auth).json()['person']['id'] == str(own.person.id)


def test_auth_cookie_regression(client):
    payload = dict(email=f'{uuid4().hex}@example.com', password='SyntheticTest!12345', first_name='Sandeep', last_name='Reddy')
    assert client.post('/auth/register', json=payload).status_code == 201
    assert client.post('/auth/register', json=payload).status_code == 409
    assert client.post('/auth/register', json={**payload, 'role': 'ADMIN'}).status_code == 422
    login = client.post('/auth/login', json={k: payload[k] for k in ('email', 'password')})
    assert login.status_code == 200
    assert 'httponly' in login.headers['set-cookie'].lower()
    assert 'refresh_token' not in login.json()
    assert client.get('/auth/me', headers={'Authorization': 'Bearer ' + login.json()['access_token']}).status_code == 200
    assert client.post('/auth/refresh').status_code == 200
    wrong = client.post('/auth/login', json={'email': payload['email'], 'password': 'wrong'})
    missing = client.post('/auth/login', json={'email': 'unknown@example.com', 'password': 'wrong'})
    assert wrong.status_code == missing.status_code == 401 and wrong.json() == missing.json()
    assert client.post('/auth/logout').status_code == 200
    assert client.post('/auth/refresh').status_code == 401

def test_manager_future_intervals_and_resolved_termination(db, refs):
    lead = e.hire(db, request(refs))
    child = e.hire(db, request(refs, manager_assignment_id=lead.assignment.id))
    # A future cycle must be rejected even though the graph is valid at hire time.
    with pytest.raises(InvalidOperation):
        e.change_version(db, lead.assignment.id, version(lead, effective_from=date(2028, 1, 1), manager_assignment_id=child.assignment.id))
    # Remove reporting link from the next day before ending the lead's assignment.
    e.change_version(db, child.assignment.id, version(child, manager_assignment_id=None))
    e.terminate_relationship(db, lead.work_relationship.id, s.EndRequest(end_date=date(2024, 12, 31)))
    assert queries.worker_summary(db, child.person.id, CHANGE).placements[0].manager is None
    assert e.relationship_status(e.get(db, m.WorkRelationship, child.work_relationship.id), date(2023, 1, 1)) == 'UPCOMING'


def test_finite_or_future_manager_cannot_cover_open_reporting(db, refs):
    lead = e.hire(db, request(refs, end_date=date(2025, 12, 31)))
    with pytest.raises(InvalidOperation):
        e.hire(db, request(refs, manager_assignment_id=lead.assignment.id))
    later = e.hire(db, request(refs, joining_date=CHANGE))
    with pytest.raises(InvalidOperation):
        e.hire(db, request(refs, manager_assignment_id=later.assignment.id))
    bounded = e.hire(db, request(refs, manager_assignment_id=lead.assignment.id, end_date=date(2025, 12, 31)))
    assert bounded.version.manager_assignment_id == lead.assignment.id


def test_history_detects_existing_gap_and_outside_period(db, refs):
    result = e.hire(db, request(refs, end_date=date(2026, 1, 1)))
    with pytest.raises(InvalidOperation):
        e.change_version(db, result.assignment.id, version(result, effective_from=date(2027, 1, 1)))
    with pytest.raises(InvalidOperation):
        e.change_compensation(db, result.assignment.id, s.AssignmentCompensationCreate(effective_from=date(2027, 1, 1), annual_base_salary='1', currency='INR'))
    original = e.get(db, m.AssignmentVersion, result.version.id)
    original.effective_to = date(2024, 6, 1)
    db.flush()
    with pytest.raises(Conflict):
        e.change_version(db, result.assignment.id, version(result))


def test_concurrent_employers_summary_and_person_update(db, refs):
    first = e.hire(db, request(refs))
    employer = records.create_reference(db, m.LegalEmployer, s.LegalEmployerCreate(code=uuid4().hex[:20], name='Other employer', country_code='IN'))
    second = e.hire(db, request(refs, person=None, person_id=first.person.id, legal_employer_id=employer.id))
    assert len(queries.worker_summary(db, first.person.id, START).placements) == 2
    updated = records.update_person(db, first.person.id, s.PersonUpdate(first_name=' New ', personal_email='new@example.com'))
    assert updated.first_name == 'New' and updated.person_number == first.person.person_number
    assert second.person.id == first.person.id


def test_self_service_does_not_disclose_manager_personal_data(client, db, refs):
    lead = e.hire(db, request(refs))
    child = e.hire(db, request(refs, manager_assignment_id=lead.assignment.id))
    auth = headers(db, 'EMPLOYEE', child.person.id)
    for path in ['/core-hr/me', f'/core-hr/workers/{child.person.id}']:
        body = client.get(path, headers=auth).json()
        assert body['placements'][0]['manager'] is None
        assert body['placements'][0]['manager_assignment'] is None
        assert body['placements'][0]['version']['manager_assignment_id'] == str(lead.assignment.id)


def test_api_changes_rehire_termination_and_sanitized_conflicts(client, db, refs):
    auth = headers(db, 'HR')
    result = e.hire(db, request(refs))
    changed = client.post(f'/core-hr/assignments/{result.assignment.id}/changes', json=version(result).model_dump(mode='json'), headers=auth)
    assert changed.status_code == 201, changed.text
    assert client.post(f'/core-hr/assignments/{result.assignment.id}/changes', json=version(result).model_dump(mode='json'), headers=auth).status_code == 409
    assert client.post(f'/core-hr/work-relationships/{result.work_relationship.id}/terminate', json={'end_date':'2025-12-31'}, headers=auth).status_code == 200
    data=request(refs, joining_date=date(2026,1,1)).model_dump(mode='json',exclude={'person','person_id'})
    assert client.post(f'/core-hr/workers/{result.person.id}/rehire',json=data,headers=auth).status_code == 201
    assert client.post(f'/core-hr/workers/{result.person.id}/rehire',json={**data,'person_id':str(uuid4())},headers=auth).status_code == 422
    payload={'code':'DUPLICATE_API','name':'Corporate Functions'}
    assert client.post('/core-hr/reference/jobs',json=payload,headers=auth).status_code == 201
    duplicate=client.post('/core-hr/reference/jobs',json=payload,headers=auth)
    assert duplicate.status_code == 409 and 'INSERT' not in duplicate.text and 'psycopg' not in duplicate.text
    cors=client.options('/core-hr/persons/' + str(result.person.id),headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'PATCH'})
    assert cors.status_code == 200 and cors.headers['access-control-allow-credentials']=='true'


def test_compensation_orm_and_strict_read_shape(db, refs):
    result=e.hire(db, request(refs))
    assignment=e.get(db,m.Assignment,result.assignment.id)
    assert len(assignment.compensation_history)==1
    assert assignment.compensation_history[0].assignment is assignment
    cols={c['name']:c for c in inspect(db.connection()).get_columns('assignment_compensation')}
    assert set(cols)=={'id','assignment_id','effective_from','effective_to','annual_base_salary','currency','created_at','updated_at'}
    assert {c['name'] for c in cols.values() if c['nullable']}=={'effective_to'}
    assert cols['annual_base_salary']['type'].precision==14 and cols['annual_base_salary']['type'].scale==2
    assert cols['currency']['type'].length==3
    assert cols['id']['default']=='gen_random_uuid()'
    assert all(cols[k]['type'].timezone for k in ['created_at','updated_at'])

def test_indirect_same_person_reporting_chain(db, refs):
    first = e.hire(db, request(refs))
    extra = e.create_assignment(db, s.AssignmentCreate(work_relationship_id=first.work_relationship.id, assignment_number='EXTRA_SAME_PERSON', start_date=START))
    e.change_version(db, extra.id, version(first, effective_from=START))
    middle = e.hire(db, request(refs, manager_assignment_id=extra.id))
    with pytest.raises(InvalidOperation, match='same person'):
        e.change_version(db, first.assignment.id, version(first, manager_assignment_id=middle.assignment.id))


def test_hr_mutation_lock_serializes_separate_transactions():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.services.core_hr.common import atomic
    entered = Event()
    attempted = Event()
    @atomic
    def probe(session):
        entered.set()
    def second():
        with Session(engine) as session:
            attempted.set()
            probe(session)
            session.rollback()
    with Session(engine) as first:
        probe(first)
        entered.clear()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(second)
            try:
                assert attempted.wait(5)
                assert not entered.wait(0.1), 'Second writer bypassed the transaction lock'
            finally:
                first.rollback()
            pending.result(timeout=5)
            assert entered.is_set()

@pytest.mark.parametrize('operation', ['read', 'write'])
def test_database_failures_are_safe_api_errors(client, db, monkeypatch, operation):
    from sqlalchemy.exc import OperationalError
    auth = headers(db, 'HR')
    def failed(*args, **kwargs):
        raise OperationalError('SELECT secret_database_statement', {}, Exception('private_database_credentials'))
    if operation == 'read':
        monkeypatch.setattr(records, 'list_records', failed)
        response = client.get('/core-hr/persons', headers=auth)
    else:
        monkeypatch.setattr(records, 'create_person', failed)
        response = client.post('/core-hr/persons', headers=auth,
            json={'person_number':'SAFE_ERROR','first_name':'Nikhil','last_name':'Varma'})
    assert response.status_code == 500
    assert set(response.json()) == {'detail'}
    assert 'secret_database_statement' not in response.text
    assert 'private_database_credentials' not in response.text
    assert 'OperationalError' not in response.text


def test_same_date_as_of_order_is_stable(db, refs):
    first = e.hire(db, request(refs))
    other_employer = records.create_reference(db, m.LegalEmployer,
        s.LegalEmployerCreate(code=uuid4().hex[:20], name='Asterion Digital Technologies Pvt. Ltd.', country_code='IN'))
    second = e.hire(db, request(refs, person=None, person_id=first.person.id, legal_employer_id=other_employer.id))
    relationships = e.relationships_for_person(db, first.person.id)
    assert [r.id for r in relationships] == sorted([first.work_relationship.id, second.work_relationship.id])
    extra = e.create_assignment(db, s.AssignmentCreate(work_relationship_id=first.work_relationship.id,
        assignment_number=uuid4().hex[:20], start_date=START))
    assert [a.id for a in e.assignments_for_relationship(db, first.work_relationship.id)] == sorted([first.assignment.id, extra.id])
    assert queries.worker_summary(db, first.person.id, START).model_dump() == queries.worker_summary(db, first.person.id, START).model_dump()


def test_history_reads_refresh_cached_rows(db, refs):
    result = e.hire(db, request(refs))
    cached = e.current_compensation(db, result.assignment.id, START)
    assert cached.annual_base_salary == Decimal('100000.25')
    # Simulate a database change unknown to this session's identity map.
    db.execute(m.AssignmentCompensation.__table__.update().where(m.AssignmentCompensation.id == cached.id)
               .values(annual_base_salary=Decimal('200000.00')))
    assert e.current_compensation(db, result.assignment.id, START).annual_base_salary == Decimal('200000.00')


def test_seed_rejects_incomplete_existing_history(db, monkeypatch):
    from app.services.core_hr import seed
    monkeypatch.setattr(seed, 'PREFIX', 'T' + uuid4().hex[:6].upper() + '_')
    assert seed_demo(db)['created'] is True
    assignment_id = db.scalar(select(m.Assignment.id).where(m.Assignment.assignment_number == seed.PREFIX + 'A00'))
    # Corrupt only this rolled-back fixture; rerunning must not claim success or repair history.
    db.execute(delete(m.AssignmentCompensation).where(m.AssignmentCompensation.assignment_id == assignment_id))
    before = counts(db)
    with pytest.raises(Conflict, match='Incomplete demo history'):
        seed_demo(db)
    assert counts(db) == before

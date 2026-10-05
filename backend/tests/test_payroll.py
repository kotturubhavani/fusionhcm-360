"""Payroll PostgreSQL regressions. Fixtures roll back all writes."""
from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from app import models as m
from app.schemas import payroll as s
from app.services.payroll import service as p, rules, demo
from app.services.core_hr import employment as e
from app.services.core_hr.common import Conflict, InvalidOperation
from test_core_hr import db, refs, client, headers, request, version


@pytest.fixture
def definition(db, refs):
    return p.create_definition(db, s.DefinitionCreate(code=uuid4().hex[:24], name='Synthetic test payroll',
        legal_employer_id=refs['legal_employer_id'], country_code='IN', currency='INR', standard_allowance='1000.00'))


def period(db, definition, month=1):
    from calendar import monthrange
    return p.create_period(db, s.PeriodCreate(payroll_definition_id=definition.id, period_name=f'2025-{month:02}',
        period_start=date(2025, month, 1), period_end=date(2025, month, monthrange(2025, month)[1]), payment_date=date(2025, month, monthrange(2025, month)[1])))


def results(db, run):
    return db.scalars(select(m.PayrollResult).where(m.PayrollResult.payroll_run_id == run.id)).all()


def test_definition_uniqueness_and_employer_scope(db, refs, definition):
    with pytest.raises(Conflict):
        p.create_definition(db, s.DefinitionCreate(code='OTHER', name='Duplicate employer', legal_employer_id=refs['legal_employer_id'], country_code='IN', currency='INR'))
    with db.begin_nested():
        other=m.LegalEmployer(code=uuid4().hex[:20].upper(),name='Synthetic other',country_code='IN');db.add(other);db.flush()
        with pytest.raises(Conflict):
            p.create_definition(db,s.DefinitionCreate(code=definition.code,name='Duplicate code',legal_employer_id=other.id,country_code='IN',currency='INR'))
    with pytest.raises(InvalidOperation):
        p.create_definition(db,s.DefinitionCreate(code='BAD',name='Wrong country',legal_employer_id=refs['legal_employer_id'],country_code='US',currency='USD'))


@pytest.mark.parametrize('change', [{'period_start':'2025-01-02'}, {'period_end':'2025-02-01'}, {'payment_date':'2025-01-30'}, {'period_name':'   '}, {'period_start':123}])
def test_period_contracts(definition, change):
    fields=dict(payroll_definition_id=definition.id,period_name='Jan',period_start='2025-01-01',period_end='2025-01-31',payment_date='2025-01-31')
    fields.update(change)
    with pytest.raises(ValidationError): s.PeriodCreate(**fields)


@pytest.mark.parametrize('change', [{'retirement_rate':0.05},{'standard_allowance':True},{'withholding_rate':'NaN'}, {'retirement_rate':'0.6','withholding_rate':'0.5'}, {'standard_allowance':'-1'}, {'withholding_rate':'0.12345'}])
def test_decimal_contracts(refs, change):
    with pytest.raises(ValidationError): s.DefinitionCreate(code='TEST',name='Test',legal_employer_id=refs['legal_employer_id'],country_code='IN',currency='INR',**change)


def test_overlap(db, definition):
    period(db, definition)
    with pytest.raises(Conflict): period(db, definition)
    assert period(db, definition, 2).status == 'OPEN'


def test_full_month_totals_lines_and_immutable_snapshot(db, refs, definition):
    hired=e.hire(db,request(refs,annual_base_salary='120000.00'))
    pp=period(db,definition)
    run=p.process(db,pp.id)
    assert run.status=='COMPLETED' and pp.status=='PROCESSED'
    row=results(db,run)[0]
    assert (row.gross_pay,row.total_deductions,row.net_pay)==(Decimal('11000.00'),Decimal('1600.00'),Decimal('9400.00'))
    detail=p.result_detail(db,row)
    assert {line.code:line.amount for line in detail.lines}=={'BASE_PAY':Decimal('10000.00'),'STANDARD_ALLOWANCE':Decimal('1000.00'),'DEMO_RETIREMENT':Decimal('500.00'),'DEMO_WITHHOLDING':Decimal('1100.00')}
    assert row.eligible_days==row.period_days==31
    db.get(m.Person,hired.person.id).first_name='Changed';db.flush()
    assert row.worker_name != 'Changed Synthetic'
    assert p.run_detail(db,run.id).gross_pay==row.gross_pay
    with pytest.raises(Conflict):p.process(db,pp.id)
    assert db.scalar(select(func.count()).select_from(m.PayrollRun).where(m.PayrollRun.pay_period_id==pp.id))==1


@pytest.mark.parametrize('start,end,expected_days',[(date(2025,1,16),None,16),(date(2024,1,1),date(2025,1,15),15),(date(2025,1,31),date(2025,1,31),1)])
def test_proration(db,refs,definition,start,end,expected_days):
    e.hire(db,request(refs,joining_date=start,end_date=end,annual_base_salary='120000.00'))
    run=p.process(db,period(db,definition).id)
    row=results(db,run)[0]
    assert row.eligible_days==expected_days
    base=rules.money(Decimal('10000')*Decimal(expected_days)/Decimal(31))
    allowance=rules.money(Decimal('1000')*Decimal(expected_days)/Decimal(31))
    assert row.gross_pay==base+allowance
    assert row.net_pay==row.gross_pay-rules.money(base*Decimal('.05'))-rules.money(row.gross_pay*Decimal('.10'))


def test_exclusion_and_missing_compensation(db,refs,definition):
    e.hire(db,request(refs,end_date=date(2024,12,31)))
    future=e.hire(db,request(refs,joining_date=date(2025,2,1)))
    ended=e.hire(db,request(refs));e.end_assignment(db,ended.assignment.id,__import__('app.schemas.core_hr',fromlist=['EndRequest']).EndRequest(end_date=date(2024,12,31)))
    missing=e.hire(db,request(refs));db.execute(delete(m.AssignmentCompensation).where(m.AssignmentCompensation.assignment_id==missing.assignment.id))
    paid=e.hire(db,request(refs))
    run=p.process(db,period(db,definition).id)
    assert [r.person_id for r in results(db,run)]==[paid.person.id]
    assert run.excluded_assignment_count==1 and run.unpaid_day_count==31
    assert future.person.id != paid.person.id


def test_mid_month_compensation_and_status_segments(db,refs,definition):
    from app.schemas.core_hr import AssignmentCompensationCreate
    hired=e.hire(db,request(refs,annual_base_salary='120000.00'))
    e.change_compensation(db,hired.assignment.id,AssignmentCompensationCreate(effective_from=date(2025,1,16),annual_base_salary='240000.00',currency='INR'))
    e.change_version(db,hired.assignment.id,version(hired,effective_from=date(2025,1,21),status='SUSPENDED'))
    row=results(db,p.process(db,period(db,definition).id))[0]
    assert row.eligible_days==20
    base=rules.money((Decimal('10000')*15+Decimal('20000')*5)/31)
    assert row.gross_pay==base+rules.money(Decimal('1000')*20/31)
    assert len(row.calculation_snapshot)==2


def test_currency_failure_rolls_back_partial_results_and_retry(db,refs,definition):
    from app.schemas.core_hr import PersonCreate
    e.hire(db,request(refs,person=PersonCreate(person_number='AA'+uuid4().hex[:10],first_name='Good',last_name='Synthetic')))
    bad=e.hire(db,request(refs,currency='USD',person=PersonCreate(person_number='ZZ'+uuid4().hex[:10],first_name='Bad',last_name='Synthetic')))
    pp=period(db,definition)
    failed=p.process(db,pp.id)
    assert failed.status=='FAILED' and pp.status=='OPEN' and results(db,failed)==[]
    assert 'currency' in failed.failure_reason
    db.get(m.AssignmentCompensation,bad.compensation.id).currency='INR';db.flush()
    run=p.process(db,pp.id)
    assert run.status=='COMPLETED' and run.run_number==2 and len(results(db,run))==2
    assert failed.status=='FAILED'


def test_empty_run_fails_safely(db,definition):
    run=p.process(db,period(db,definition).id)
    assert run.status=='FAILED' and results(db,run)==[]


def test_storage_failure_is_safe(db,refs,definition,monkeypatch):
    e.hire(db,request(refs))
    monkeypatch.setattr(p,'populate_results',lambda *args: (_ for _ in ()).throw(OperationalError('secret SQL',{},Exception('private'))))
    run=p.process(db,period(db,definition).id)
    assert run.status=='FAILED' and 'secret' not in run.failure_reason and 'private' not in run.failure_reason


@pytest.mark.parametrize('value,expected',[('1.005','1.01'),('1.004','1.00'),('0.005','0.01')])
def test_rounding(value,expected):
    assert rules.money(Decimal(value))==Decimal(expected)


@pytest.mark.parametrize('role',['HR','ADMIN'])
def test_management_api(client,db,refs,role):
    auth=headers(db,role)
    e.hire(db,request(refs))
    definition=client.post('/payroll/definitions',headers=auth,json=dict(code=uuid4().hex[:24],name='API Payroll',legal_employer_id=str(refs['legal_employer_id']),country_code='IN',currency='INR'))
    assert definition.status_code==201,definition.text
    did=definition.json()['id']
    period_response=client.post('/payroll/periods',headers=auth,json=dict(payroll_definition_id=did,period_name='2025-01',period_start='2025-01-01',period_end='2025-01-31',payment_date='2025-01-31'))
    assert period_response.status_code==201,period_response.text
    pid=period_response.json()['id']
    response=client.post(f'/payroll/periods/{pid}/process',headers=auth)
    assert response.status_code==201,response.text
    run=response.json();assert run['status']=='COMPLETED'
    for path in ['/definitions','/definitions/'+did,'/periods','/periods/'+pid,'/runs','/runs/'+run['id']]:
        assert client.get('/payroll'+path,headers=auth).status_code==200
    rows=client.get('/payroll/runs/'+run['id']+'/results',headers=auth).json()
    assert isinstance(rows[0]['net_pay'],str)
    assert client.get('/payroll/results/'+rows[0]['id'],headers=auth).status_code==200
    assert client.post(f'/payroll/periods/{pid}/process',headers=auth).status_code==409


def test_employee_self_only(client,db,refs,definition):
    first=e.hire(db,request(refs));second=e.hire(db,request(refs))
    run=p.process(db,period(db,definition).id)
    own=headers(db,'EMPLOYEE',first.person.id)
    rows=client.get('/payroll/me',headers=own).json()
    assert len(rows)==1 and rows[0]['result']['person_id']==str(first.person.id)
    assert client.get('/payroll/me/'+rows[0]['result']['id'],headers=own).status_code==200
    other=next(row for row in results(db,run) if row.person_id==second.person.id)
    assert client.get('/payroll/me/'+str(other.id),headers=own).status_code==404
    assert len(client.get('/payroll/me?person_id='+str(second.person.id),headers=own).json())==1
    for path in ['/definitions','/periods','/runs','/runs/'+str(run.id),'/results/'+str(other.id)]:
        assert client.get('/payroll'+path,headers=own).status_code==403
    assert client.post('/payroll/periods/'+str(run.pay_period_id)+'/process',headers=own).status_code==403
    assert client.get('/payroll/me',headers=headers(db,'EMPLOYEE')).status_code==404
    assert client.get('/payroll/me').status_code==401


def test_seed_idempotency(db,monkeypatch):
    from app.services.core_hr import demo as hr_demo
    prefix='T'+uuid4().hex[:6].upper()+'_'
    monkeypatch.setattr(hr_demo,'PREFIX',prefix);monkeypatch.setattr(demo,'PREFIX',prefix)
    hr_demo.seed_demo(db)
    assert demo.seed_demo(db)['created']
    before={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [m.PayrollDefinition,m.PayPeriod,m.PayrollRun,m.PayrollResult,m.PayrollResultLine]}
    assert not demo.seed_demo(db)['created']
    assert before=={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [m.PayrollDefinition,m.PayPeriod,m.PayrollRun,m.PayrollResult,m.PayrollResultLine]}


def test_db_result_totals_constraint(db,refs,definition):
    e.hire(db,request(refs));run=p.process(db,period(db,definition).id);row=results(db,run)[0]
    with pytest.raises(IntegrityError), db.begin_nested():
        row.net_pay=Decimal('-1');db.flush()

def test_migration_upgrade_downgrade_upgrade_isolated_schema():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect, text
    from app.core.database import engine
    schema='payroll_test_'+uuid4().hex
    modules={}
    for path in Path('alembic/versions').glob('*.py'):
        spec=importlib.util.spec_from_file_location(path.stem,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        modules[module.revision]=module
    ordered=[];head='9085d55b6f98'
    while head:
        ordered.insert(0,modules[head]);head=modules[head].down_revision
    with engine.connect() as connection:
        transaction=connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            with Operations.context(MigrationContext.configure(connection)):
                for migration in ordered:migration.upgrade()
                assert 'payroll_results' in inspect(connection).get_table_names(schema=schema)
                ordered[-1].downgrade()
                assert 'payroll_results' not in inspect(connection).get_table_names(schema=schema)
                assert 'assignment_compensation' in inspect(connection).get_table_names(schema=schema)
                ordered[-1].upgrade()
                assert 'payroll_result_lines' in inspect(connection).get_table_names(schema=schema)
        finally:transaction.rollback()


def test_metadata_matches_database(db):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.core.database import Base
    assert compare_metadata(MigrationContext.configure(db.connection()),Base.metadata)==[]


def test_rounded_net_never_negative(db,refs,definition):
    definition.retirement_rate=Decimal('0.5000');definition.withholding_rate=Decimal('0.5000');definition.standard_allowance=Decimal('0.00');db.flush()
    e.hire(db,request(refs,annual_base_salary='0.12'))
    run=p.process(db,period(db,definition).id)
    assert run.status=='FAILED' and 'Rounded deductions' in run.failure_reason and not results(db,run)


def test_paid_leave_and_other_employer_exclusion(db,refs,definition):
    hired=e.hire(db,request(refs))
    e.change_version(db,hired.assignment.id,version(hired,effective_from=date(2025,1,1),status='ON_LEAVE'))
    other=m.LegalEmployer(code=uuid4().hex[:20].upper(),name='Different Synthetic',country_code='IN');db.add(other);db.flush()
    e.hire(db,request({**refs,'legal_employer_id':other.id}))
    run=p.process(db,period(db,definition).id)
    assert len(results(db,run))==1 and results(db,run)[0].eligible_days==31


def test_seed_rejects_missing_history(db,monkeypatch):
    from app.services.core_hr import demo as hr_demo
    prefix='T'+uuid4().hex[:6].upper()+'_'
    monkeypatch.setattr(hr_demo,'PREFIX',prefix);monkeypatch.setattr(demo,'PREFIX',prefix)
    hr_demo.seed_demo(db);demo.seed_demo(db)
    definition=db.scalar(select(m.PayrollDefinition).where(m.PayrollDefinition.code==prefix+'PAYROLL'))
    open_period=db.scalar(select(m.PayPeriod).where(m.PayPeriod.payroll_definition_id==definition.id,m.PayPeriod.status=='OPEN'))
    db.delete(open_period);db.flush()
    with pytest.raises(InvalidOperation):demo.seed_demo(db)


def test_monthly_rounding_at_half_cent(db,refs,definition):
    definition.standard_allowance=Decimal('0.00');definition.retirement_rate=Decimal('0');definition.withholding_rate=Decimal('0');db.flush()
    e.hire(db,request(refs,annual_base_salary='12.06'))
    row=results(db,p.process(db,period(db,definition).id))[0]
    assert row.gross_pay==Decimal('1.01')

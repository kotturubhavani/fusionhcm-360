"""PostgreSQL FBP regressions; fixture writes roll back."""
from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import select, func, delete, text
from sqlalchemy.exc import IntegrityError
from app import models as m
from app.schemas import fbp as s
from app.schemas import core_hr as hr
from app.services.fbp import service as f, demo, rules
from app.services.core_hr import employment as e
from app.services.core_hr.common import Conflict, InvalidOperation
from app.core.database import engine
from test_core_hr import db, refs, client, headers, request, version


@pytest.fixture
def plan(db,refs):
    return f.create_plan(db,s.PlanCreate(code=uuid4().hex[:24],name='Synthetic benefits',legal_employer_id=refs['legal_employer_id'],plan_year=2025,effective_from=date(2025,1,1),effective_to=date(2025,12,31),currency='INR'))


def component(db,plan,**kwargs):
    return f.create_component(db,plan.id,s.ComponentCreate(code=uuid4().hex[:24],name='Synthetic flexible benefit',component_type='BENEFIT',max_amount='999999999999.99',**kwargs))


def ready(db,refs,plan):
    hired=e.hire(db,request(refs,annual_base_salary='120000.00'))
    comp=component(db,plan);f.open_plan(db,plan.id);f.generate_budgets(db,plan.id)
    return hired,comp,f.workers(db,plan.id)[0]


def allocation(budget,comp,amount,revision=None):
    return s.ElectionsSave(worker_budget_id=budget.id,expected_revision=budget.revision if revision is None else revision,elections=[s.ElectionInput(component_id=comp.id,amount=amount)])


def test_plan_uniqueness(db,refs,plan):
    data={key:getattr(plan,key) for key in s.PlanCreate.model_fields}
    with pytest.raises(Conflict):f.create_plan(db,s.PlanCreate(**data))
    data['code']='DIFFERENT'
    with pytest.raises(Conflict):f.create_plan(db,s.PlanCreate(**data))


@pytest.mark.parametrize('change',[{'effective_from':'2025-01-02'},{'effective_to':'2026-12-31'},{'plan_year':2024},{'status':'OPEN'},{'budget_rate':0.1},{'budget_rate':'0'},{'budget_rate':'1.0001'}])
def test_plan_validation(refs,change):
    data=dict(code='PLAN',name='Plan',legal_employer_id=refs['legal_employer_id'],plan_year=2025,effective_from='2025-01-01',effective_to='2025-12-31',currency='INR');data.update(change)
    with pytest.raises(ValidationError):s.PlanCreate(**data)


@pytest.mark.parametrize('change',[{'min_amount':'101'},{'default_amount':'101'},{'min_amount':'50','default_amount':'20'},{'max_amount':'-1'},{'max_amount':1.1},{'component_type':'TAX'},{'display_order':-1}])
def test_component_limits(change):
    data=dict(code='C',name='Component',component_type='BENEFIT',max_amount='100');data.update(change)
    with pytest.raises(ValidationError):s.ComponentCreate(**data)


def test_draft_updates_and_frozen_settings(db,plan):
    plan=f.update_plan(db,plan.id,s.PlanUpdate(name='Updated'))
    comp=component(db,plan)
    f.update_component(db,comp.id,s.ComponentUpdate(is_active=False))
    with pytest.raises(InvalidOperation):f.open_plan(db,plan.id)
    f.update_component(db,comp.id,s.ComponentUpdate(is_active=True,default_amount='10.00'))
    with pytest.raises(InvalidOperation):f.update_component(db,comp.id,s.ComponentUpdate(max_amount=None))
    f.open_plan(db,plan.id)
    with pytest.raises(Conflict):f.update_plan(db,plan.id,s.PlanUpdate(name='No'))
    with pytest.raises(Conflict):f.update_component(db,comp.id,s.ComponentUpdate(is_active=False))


def test_budget_snapshot_and_idempotency(db,refs,plan):
    hired,comp,budget=ready(db,refs,plan)
    assert budget.eligible_budget==Decimal('12000.00') and budget.allocated==0 and budget.remaining==12000
    db.get(m.AssignmentCompensation,hired.compensation.id).annual_base_salary=Decimal('240000.00');db.flush()
    summary=f.generate_budgets(db,plan.id)
    assert summary.budgets==1 and summary.eligible_budget==12000
    assert f.workers(db,plan.id)[0].annual_base_salary==120000
    assert rules.budget(Decimal('100.05'),Decimal('.1'))==Decimal('10.01')


def test_eligibility(db,refs,plan):
    good=e.hire(db,request(refs))
    e.hire(db,request(refs,end_date=date(2024,12,31)))
    e.hire(db,request(refs,joining_date=date(2025,1,2)))
    inactive=e.hire(db,request(refs));db.get(m.Person,inactive.person.id).is_active=False;db.flush()
    leave=e.hire(db,request(refs));e.change_version(db,leave.assignment.id,version(leave,effective_from=date(2025,1,1),status='ON_LEAVE'))
    missing=e.hire(db,request(refs));db.execute(delete(m.AssignmentCompensation).where(m.AssignmentCompensation.id==missing.compensation.id))
    ended=e.hire(db,request(refs));e.end_assignment(db,ended.assignment.id,hr.EndRequest(end_date=date(2024,12,31)))
    e.hire(db,request(refs,annual_base_salary='0.00'))
    component(db,plan);f.open_plan(db,plan.id);f.generate_budgets(db,plan.id)
    assert [b.person_id for b in f.workers(db,plan.id)]==[good.person.id]


def test_currency_failure_atomic(db,refs,plan):
    e.hire(db,request(refs));e.hire(db,request(refs,currency='USD'))
    component(db,plan);f.open_plan(db,plan.id)
    with pytest.raises(InvalidOperation):f.generate_budgets(db,plan.id)
    assert f.workers(db,plan.id)==[] and db.get(m.FBPPlan,plan.id).budgets_generated_at is None


def test_component_capacity_prevents_unsubmittable_budget(db,refs,plan):
    e.hire(db,request(refs,annual_base_salary='120000'))
    f.create_component(db,plan.id,s.ComponentCreate(code='LIMIT',name='Limit',component_type='BENEFIT',max_amount='100'))
    f.open_plan(db,plan.id)
    with pytest.raises(InvalidOperation):f.generate_budgets(db,plan.id)
    assert not f.workers(db,plan.id)


def test_election_workflow(db,refs,plan):
    hired,comp,budget=ready(db,refs,plan)
    with pytest.raises(InvalidOperation):f.save_elections(db,plan.id,hired.person.id,allocation(budget,comp,'12000.01'))
    saved=f.save_elections(db,plan.id,hired.person.id,allocation(budget,comp,'5000'))
    assert saved.remaining==7000
    with pytest.raises(InvalidOperation):f.submit(db,plan.id,hired.person.id,s.BudgetAction(worker_budget_id=budget.id,expected_revision=saved.revision))
    with pytest.raises(Conflict):f.close_plan(db,plan.id)
    saved=f.save_elections(db,plan.id,hired.person.id,allocation(saved,comp,'12000'))
    submitted=f.submit(db,plan.id,hired.person.id,s.BudgetAction(worker_budget_id=budget.id,expected_revision=saved.revision))
    assert submitted.status=='SUBMITTED'
    with pytest.raises(Conflict):f.save_elections(db,plan.id,hired.person.id,allocation(submitted,comp,'1'))
    f.close_plan(db,plan.id)
    finalized=f.my_plan(db,hired.person.id,plan.id).budgets[0]
    assert finalized.status=='FINALIZED' and finalized.finalized_at
    with pytest.raises(Conflict):f.save_elections(db,plan.id,hired.person.id,allocation(finalized,comp,'1'))
    assert f.summary(db,plan.id).finalized==1


def test_same_plan_active_limits_and_replacement(db,refs,plan):
    capped=f.create_component(db,plan.id,s.ComponentCreate(code='CAP',name='Capped',component_type='ALLOWANCE',min_amount='100',max_amount='1000'))
    off=component(db,plan,is_active=False)
    hired,comp,budget=ready(db,refs,plan)
    for target,amount in [(capped,'99'),(capped,'1001'),(off,'1')]:
        with pytest.raises(InvalidOperation):f.save_elections(db,plan.id,hired.person.id,allocation(budget,target,amount))
    saved=f.save_elections(db,plan.id,hired.person.id,allocation(budget,capped,'100'))
    saved=f.save_elections(db,plan.id,hired.person.id,allocation(saved,comp,'12000'))
    assert {e.component_id:e.amount for e in saved.elections}=={capped.id:0,comp.id:12000}
    other=f.create_plan(db,s.PlanCreate(code=uuid4().hex[:24],name='Other',legal_employer_id=refs['legal_employer_id'],plan_year=2026,effective_from=date(2026,1,1),effective_to=date(2026,12,31),currency='INR'))
    foreign=component(db,other)
    with pytest.raises(InvalidOperation):f.save_elections(db,plan.id,hired.person.id,allocation(saved,foreign,'1'))
    with pytest.raises(IntegrityError),db.begin_nested():
        db.add(m.FBPElection(plan_id=plan.id,worker_budget_id=budget.id,component_id=foreign.id,amount=Decimal('1')));db.flush()


def test_lock_and_stale_revision_prevent_lost_updates(db,refs,plan):
    from concurrent.futures import ThreadPoolExecutor
    hired,comp,budget=ready(db,refs,plan)
    def competing_lock():
        with engine.connect() as conn:
            return conn.scalar(text('SELECT pg_try_advisory_xact_lock(360, 1)'))
    with ThreadPoolExecutor(max_workers=1) as pool:assert pool.submit(competing_lock).result(timeout=5) is False
    saved=f.save_elections(db,plan.id,hired.person.id,allocation(budget,comp,'1000'))
    with pytest.raises(Conflict):f.save_elections(db,plan.id,hired.person.id,allocation(budget,comp,'2000'))
    assert f.my_plan(db,hired.person.id,plan.id).budgets[0].allocated==1000
    assert saved.revision==1


@pytest.mark.parametrize('role',['HR','ADMIN'])
def test_staff_api(client,db,refs,role):
    auth=headers(db,role)
    response=client.post('/fbp/plans',headers=auth,json=dict(code=uuid4().hex[:24],name='API benefits',legal_employer_id=str(refs['legal_employer_id']),plan_year=2025,effective_from='2025-01-01',effective_to='2025-12-31',currency='INR'))
    assert response.status_code==201,response.text
    pid=response.json()['id'];e.hire(db,request(refs))
    response=client.post('/fbp/plans/'+pid+'/components',headers=auth,json=dict(code='FLEX',name='Flexible',component_type='BENEFIT',max_amount='999999.99'))
    assert response.status_code==201,response.text
    assert client.patch('/fbp/components/'+response.json()['id'],headers=auth,json={'description':'Synthetic'}).status_code==200
    assert client.patch('/fbp/plans/'+pid,headers=auth,json={'name':'Updated benefits'}).status_code==200
    assert client.post('/fbp/plans/'+pid+'/open',headers=auth).status_code==200
    assert client.post('/fbp/plans/'+pid+'/generate-budgets',headers=auth).status_code==200
    for path in ['/plans','/plans/'+pid,'/plans/'+pid+'/components','/plans/'+pid+'/workers','/plans/'+pid+'/summary']:assert client.get('/fbp'+path,headers=auth).status_code==200
    assert client.post('/fbp/plans/'+pid+'/close',headers=auth).status_code==409


def test_employee_ownership_api(client,db,refs,plan):
    other=e.hire(db,request(refs))
    hired,comp,_=ready(db,refs,plan)
    budget=next(b for b in f.workers(db,plan.id) if b.person_id==hired.person.id)
    foreign=next(b for b in f.workers(db,plan.id) if b.person_id==other.person.id)
    auth=headers(db,'EMPLOYEE',hired.person.id)
    db.commit()  # Release the fixture savepoint; outer transaction still rolls back.
    response=client.get('/fbp/me',headers=auth);assert response.status_code==200 and len(response.json())==1
    assert len(response.json()[0]['budgets'])==1
    payload=allocation(budget,comp,'12000').model_dump(mode='json')
    path='/fbp/me/'+str(plan.id)
    assert client.post(path+'/elections',headers=auth,json={**payload,'worker_budget_id':str(foreign.id)}).status_code==404
    assert client.post(path+'/elections',headers=auth,json={**payload,'person_id':str(other.person.id)}).status_code==422
    saved=client.post(path+'/elections',headers=auth,json=payload);assert saved.status_code==200,saved.text
    response=client.post(path+'/submit',headers=auth,json={'worker_budget_id':str(budget.id),'expected_revision':saved.json()['revision']});assert response.status_code==200,response.text
    assert client.get('/fbp/plans',headers=auth).status_code==403
    assert client.post('/fbp/plans/'+str(plan.id)+'/close',headers=auth).status_code==403
    assert client.get('/fbp/me',headers=headers(db,'EMPLOYEE')).status_code==404
    assert client.get('/fbp/me').status_code==401


def test_seed_idempotency(db,monkeypatch):
    from app.services.core_hr import demo as hr_demo
    prefix='T'+uuid4().hex[:6].upper()+'_';monkeypatch.setattr(hr_demo,'PREFIX',prefix);monkeypatch.setattr(demo,'PREFIX',prefix)
    hr_demo.seed_demo(db);assert demo.seed_demo(db)['created']
    models=[m.FBPPlan,m.FBPComponent,m.FBPWorkerBudget,m.FBPElection]
    before=[db.scalar(select(func.count()).select_from(model)) for model in models]
    assert not demo.seed_demo(db)['created']
    assert before==[db.scalar(select(func.count()).select_from(model)) for model in models]


def test_migration_upgrade_downgrade_upgrade_isolated_schema():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect, text
    from app.core.database import engine
    schema='fbp_test_'+uuid4().hex
    modules={}
    for path in Path('alembic/versions').glob('*.py'):
        spec=importlib.util.spec_from_file_location(path.stem,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        modules[module.revision]=module
    ordered=[];head='ccc6f4b903ce'
    while head:
        ordered.insert(0,modules[head]);head=modules[head].down_revision
    with engine.connect() as connection:
        transaction=connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            with Operations.context(MigrationContext.configure(connection)):
                for migration in ordered:migration.upgrade()
                assert 'fbp_worker_budgets' in inspect(connection).get_table_names(schema=schema)
                ordered[-1].downgrade()
                assert 'fbp_worker_budgets' not in inspect(connection).get_table_names(schema=schema)
                assert 'payroll_results' in inspect(connection).get_table_names(schema=schema)
                ordered[-1].upgrade()
                assert 'fbp_elections' in inspect(connection).get_table_names(schema=schema)
        finally:transaction.rollback()


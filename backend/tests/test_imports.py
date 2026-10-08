"""PostgreSQL import regressions. All fixture data rolls back."""
import csv
import io
from uuid import uuid4
import pytest
from sqlalchemy import select,text
from app import models as m
from app.core.config import settings
from app.services.imports import service as f,templates,operations
from app.services.core_hr.common import Conflict,InvalidOperation
from test_core_hr import db,refs,client,headers,counts


def hire_row(db,refs,**changes):
    row=dict(person_number=uuid4().hex[:24],first_name='Pranavi',last_name='Rao',employment_type='REGULAR',start_date='2024-01-01',assignment_number=uuid4().hex[:24],work_time_type='FULL_TIME',annual_base_salary='100000.25',currency='INR')
    for key,model in [('legal_employer',m.LegalEmployer),('business_unit',m.BusinessUnit),('department',m.Department),('job',m.Job),('grade',m.Grade),('location',m.Location)]:
        row[key+'_code']=db.get(model,refs[key+'_id']).code
    return {**row,**changes}


def content(kind,entries):
    output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=templates.TEMPLATES[kind]);writer.writeheader();writer.writerows(entries)
    return output.getvalue().encode()


def upload(db,entries,kind='WORKER_HIRE'):
    return f.upload(db,kind,'person-updates.csv',content(kind,entries),None)


@pytest.mark.parametrize('data',[
    b'',b'person_number\n',b'person_number,person_number\nx,y',b'person_number,unknown\nx,y',b'first_name\nx',
    b'person_number,first_name\nx',b'person_number,first_name\nx,"unterminated',b'person_number,first_name\nx,\xff',b'person_number,first_name\nx,\x00',
])
def test_bad_csv(data):
    with pytest.raises(InvalidOperation):templates.parse('PERSON_UPDATE',data)


def test_limits_and_filename(db,refs,monkeypatch):
    data=content('WORKER_HIRE',[hire_row(db,refs)])
    monkeypatch.setattr(settings,'import_max_file_bytes',len(data)-1)
    with pytest.raises(InvalidOperation):templates.parse('WORKER_HIRE',data)
    monkeypatch.setattr(settings,'import_max_file_bytes',5*1024*1024)
    monkeypatch.setattr(settings,'import_max_rows',1)
    with pytest.raises(InvalidOperation):templates.parse('PERSON_UPDATE',b'person_number,first_name\nx,a\ny,b')
    job=f.upload(db,'WORKER_HIRE','../../person-updates.csv',data,None)
    assert job.original_filename=='person-updates.csv'
    with pytest.raises(InvalidOperation):f.upload(db,'WORKER_HIRE','bad.exe',data,None)


def test_hire_dry_run_process_and_idempotency(db,refs):
    row=hire_row(db,refs);before=counts(db)
    job=upload(db,[row]);assert job.status=='UPLOADED' and counts(db)==before
    f.validate(db,job.id);assert counts(db)==before and job.valid_rows==1
    result=f.rows(db,job.id)[0];assert result.normalized_data['annual_base_salary']=='100000.25'
    f.validate(db,job.id);assert counts(db)==before
    f.process(db,job.id);assert job.status=='COMPLETED' and job.processed_rows==1
    assert all(counts(db)[key]==value+1 for key,value in before.items())
    assert result.status=='PROCESSED' and result.created_record_reference['assignment_id']
    with pytest.raises(Conflict):f.process(db,job.id)
    with pytest.raises(Conflict):f.validate(db,job.id)


@pytest.mark.parametrize('change,code',[
    ({'first_name':''},'MISSING_REQUIRED_FIELD'),({'start_date':'2024-02-30'},'INVALID_DATE'),
    ({'annual_base_salary':'1e3'},'INVALID_DECIMAL'),({'annual_base_salary':'NaN'},'INVALID_DECIMAL'),
    ({'employment_type':'CONTRACTOR'},'INVALID_ENUM'),({'job_code':'MISSING'},'REFERENCE_NOT_FOUND'),
    ({'department_code':'MISSING'},'REFERENCE_NOT_FOUND'),({'manager_assignment_number':'MISSING'},'INVALID_MANAGER'),
])
def test_invalid_rows(db,refs,change,code):
    before=counts(db);job=upload(db,[hire_row(db,refs,**change)])
    f.validate(db,job.id);row=f.rows(db,job.id)[0]
    assert row.status=='INVALID' and row.error_code==code and counts(db)==before
    with pytest.raises(Conflict):f.process(db,job.id)


def test_duplicates_and_mixed(db,refs):
    one=hire_row(db,refs);two=hire_row(db,refs,annual_base_salary='bad')
    job=upload(db,[one,two,one]);f.validate(db,job.id)
    assert (job.valid_rows,job.invalid_rows)==(1,2)
    f.process(db,job.id);assert job.status=='COMPLETED_WITH_ERRORS'
    assert [r.status for r in f.rows(db,job.id)]==['PROCESSED','INVALID','INVALID']
    for field,expected in [('person_number','DUPLICATE_PERSON_NUMBER'),('assignment_number','DUPLICATE_ASSIGNMENT_NUMBER')]:
        another=upload(db,[hire_row(db,refs,**{field:one[field]})]);f.validate(db,another.id)
        assert f.rows(db,another.id)[0].error_code==expected


def test_department_context(db,refs):
    unit=m.BusinessUnit(code=uuid4().hex[:24],name='Business Operations');db.add(unit);db.flush()
    job=upload(db,[hire_row(db,refs,business_unit_code=unit.code)]);f.validate(db,job.id)
    assert job.invalid_rows==1


def test_runtime_failure_isolated(db,refs,monkeypatch):
    job=upload(db,[hire_row(db,refs),hire_row(db,refs)])
    f.validate(db,job.id);before=counts(db);original=operations.apply;calls=0
    def fail_second(*args):
        nonlocal calls
        calls+=1
        result=original(*args)
        if calls==2:raise RuntimeError('sensitive internal detail')
        return result
    monkeypatch.setattr(operations,'apply',fail_second)
    f.process(db,job.id)
    assert (job.processed_rows,job.failed_rows)==(1,1)
    assert all(counts(db)[key]==value+1 for key,value in before.items())
    failed=f.rows(db,job.id,'FAILED')[0]
    assert failed.error_code=='PROCESSING_ERROR' and 'sensitive' not in failed.error_message


def test_stale_validation_rechecks(db,refs):
    data=hire_row(db,refs);job=upload(db,[data]);f.validate(db,job.id)
    other=upload(db,[data]);f.validate(db,other.id);f.process(db,other.id)
    f.process(db,job.id);assert job.failed_rows==1


def test_person_assignment_compensation_changes(db,refs):
    data=hire_row(db,refs);job=upload(db,[data]);f.validate(db,job.id);f.process(db,job.id)
    identifier=f.rows(db,job.id)[0].created_record_reference['assignment_id']
    from uuid import UUID
    for kind,row in [
        ('PERSON_UPDATE',{'person_number':data['person_number'],'preferred_name':'Updated'}),
        ('ASSIGNMENT_CHANGE',{**{k:data.get(k,'') for k in templates.VERSION},'assignment_number':data['assignment_number'],'effective_date':'2025-01-01','work_time_type':'PART_TIME'}),
        ('COMPENSATION_CHANGE',{'assignment_number':data['assignment_number'],'effective_date':'2025-01-01','annual_base_salary':'120000.99','currency':'INR'}),
    ]:
        change=upload(db,[row],kind);before=counts(db);f.validate(db,change.id)
        assert change.valid_rows==1 and counts(db)==before
        f.process(db,change.id);assert change.status=='COMPLETED'
    assert str(db.scalar(select(m.AssignmentCompensation.annual_base_salary).where(m.AssignmentCompensation.assignment_id==UUID(identifier),m.AssignmentCompensation.effective_to.is_(None))))=='120000.99'
    assert db.scalar(select(m.Person.preferred_name).where(m.Person.person_number==data['person_number'].upper()))=='Updated'
    missing=upload(db,[{'assignment_number':'MISSING','effective_date':'2025-01-01','annual_base_salary':'1','currency':'INR'}],'COMPENSATION_CHANGE')
    f.validate(db,missing.id);assert f.rows(db,missing.id)[0].error_code=='ASSIGNMENT_NOT_FOUND'


def test_lock_held(db,refs):
    from app.core.database import engine
    job=upload(db,[hire_row(db,refs)]);f.validate(db,job.id)
    with engine.connect() as other:
        assert other.scalar(text('SELECT pg_try_advisory_xact_lock(360,1)')) is False


@pytest.mark.parametrize('role',['HR','ADMIN'])
def test_staff_api(client,db,refs,role):
    auth=headers(db,role);db.commit()
    assert client.get('/imports/templates',headers=auth).status_code==200
    template=client.get('/imports/templates/WORKER_HIRE',headers=auth)
    assert template.status_code==200 and 'person_number' in template.text
    r=client.post('/imports',headers=auth,data={'object_type':'WORKER_HIRE'},files={'file':('test.csv',content('WORKER_HIRE',[hire_row(db,refs)]),'text/csv')})
    assert r.status_code==201,r.text
    jid=r.json()['id']
    assert client.post(f'/imports/{jid}/validate',headers=auth).json()['valid_rows']==1
    assert client.post(f'/imports/{jid}/process',headers=auth).json()['processed_rows']==1
    assert client.post(f'/imports/{jid}/process',headers=auth).status_code==409
    assert client.get(f'/imports/{jid}/rows',headers=auth).json()[0]['status']=='PROCESSED'
    assert client.get(f'/imports/{jid}/errors.csv',headers=auth).status_code==200


def test_employee_blocked(client,db):
    auth=headers(db,'EMPLOYEE');db.commit();jid=str(uuid4())
    for method,path in [('GET',''),('GET','/templates'),('POST',''),('GET','/'+jid),('GET','/'+jid+'/rows'),('POST','/'+jid+'/validate'),('POST','/'+jid+'/process'),('GET','/'+jid+'/errors.csv')]:
        assert client.request(method,'/imports'+path,headers=auth).status_code==403
    assert client.get('/imports').status_code==401


def test_error_csv_formula_safety():
    assert templates.csv_safe('  =SUM(A1)')=="'  =SUM(A1)"
    assert templates.csv_safe('@bad')=="'@bad"


def test_migration_upgrade_downgrade_upgrade_isolated_schema():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect, text
    from app.core.database import engine
    schema='imports_test_'+uuid4().hex
    modules={}
    for path in Path('alembic/versions').glob('*.py'):
        spec=importlib.util.spec_from_file_location(path.stem,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        modules[module.revision]=module
    ordered=[];head='eed5cf0e9369'
    while head:
        ordered.insert(0,modules[head]);head=modules[head].down_revision
    with engine.connect() as connection:
        transaction=connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            with Operations.context(MigrationContext.configure(connection)):
                for migration in ordered:migration.upgrade()
                assert 'import_jobs' in inspect(connection).get_table_names(schema=schema)
                ordered[-1].downgrade()
                assert 'import_jobs' not in inspect(connection).get_table_names(schema=schema)
                assert 'payroll_results' in inspect(connection).get_table_names(schema=schema)
                ordered[-1].upgrade()
                assert 'import_rows' in inspect(connection).get_table_names(schema=schema)
        finally:transaction.rollback()


def test_fatal_job_rolls_back(db,refs,monkeypatch):
    job=upload(db,[hire_row(db,refs)]);f.validate(db,job.id);before=counts(db)
    def fail(*args,**kwargs):raise RuntimeError('internal detail')
    monkeypatch.setattr(f,'rows',fail)
    assert f.process(db,job.id).status=='FAILED'
    assert counts(db)==before and job.processed_rows==0

def test_multipart_limits_and_malformed(client,db,monkeypatch):
    auth=headers(db,'HR');db.commit()
    response=client.post('/imports',headers={**auth,'Content-Type':'multipart/form-data'},content=b'invalid')
    assert response.status_code==422
    response=client.post('/imports',headers=auth,data={'object_type':'PERSON_UPDATE'},files=[('file',('one.csv',b'person_number,first_name\nx,y')),('file',('two.csv',b'person_number,first_name\nx,y'))])
    assert response.status_code==422
    monkeypatch.setattr(settings,'import_max_file_bytes',1)
    response=client.post('/imports',headers=auth,content=b'x'*65538)
    assert response.status_code==413

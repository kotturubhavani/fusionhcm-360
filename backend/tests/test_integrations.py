"""Integration PostgreSQL and isolated HTTP regressions; changes roll back."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app import models as m
from app.core.config import settings
from app.schemas import integrations as s
from app.services.integrations import service as f, security, demo, payloads
from app.services.core_hr import employment
from app.services.core_hr.common import Conflict, InvalidOperation
from test_core_hr import db, refs, client, headers, request

@pytest.fixture(autouse=True)
def isolate(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'integration_output_dir',tmp_path)
    monkeypatch.setattr(settings,'allow_private_integration_targets',False)
    monkeypatch.setattr(settings,'integration_credential_env_keys',['INTEGRATION_TOKEN_TEST'])
    monkeypatch.setenv('INTEGRATION_TOKEN_TEST','synthetic-test-token')

def definition(**kwargs):
    return s.DefinitionCreate(**(dict(code=uuid4().hex[:24],name='Synthetic integration',direction='OUTBOUND',integration_type='WORKER_EXPORT',transport_type='FILE')|kwargs))
def run_request(**kwargs):return s.RunRequest(request_key=uuid4().hex,**kwargs)
def inbound(kind='PERSON_UPDATE',**kwargs):return definition(**(dict(direction='INBOUND',integration_type=kind,transport_type='HTTP_REST',configuration={'auth_type':'BEARER_ENV','credential_env_key':'INTEGRATION_TOKEN_TEST'})|kwargs))

@pytest.mark.parametrize('change',[
 {'direction':'INBOUND'},{'integration_type':'SQL'}, {'transport_type':'FTP'},
 {'transport_type':'HTTP_REST'}, {'endpoint_url':'https://example.com'},
 {'configuration':{'password':'secret'}}, {'configuration':{'auth_type':'BEARER_ENV','credential_env_key':'DATABASE_URL'}},
 {'configuration':{'department_code':'D'}}, {'configuration':{'fbp_plan_code':'P'}},
])
def test_contract(change):
    with pytest.raises(ValidationError):definition(**change)

@pytest.mark.parametrize('url',['file:///etc/passwd','http://localhost','http://127.0.0.1','http://[::1]','http://169.254.169.254','http://10.0.0.1','https://example.com?token=secret','https://user:pass@example.com','http://example.com:bad','http://example.com/#token','http://example.com\n'])
def test_url_rejection(url):
    with pytest.raises(InvalidOperation):security.endpoint(url)

def test_dns_and_credentials(monkeypatch):
    monkeypatch.setattr(security.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',80))])
    with pytest.raises(InvalidOperation):security.endpoint('https://public.example',resolve=True)
    assert security.authorized('INTEGRATION_TOKEN_TEST','synthetic-test-token')
    assert not security.authorized('DATABASE_URL','wrong')
    assert not security.authorized('INTEGRATION_TOKEN_TEST','wrong')

@pytest.mark.parametrize('format',['CSV','JSON'])
def test_worker_file(db,refs,format):
    h=employment.hire(db,request(refs))
    d=f.create(db,definition(output_format=format,configuration={'legal_employer_code':db.get(m.LegalEmployer,refs['legal_employer_id']).code}))
    run=f.execute(db,d.id,run_request());assert run.status=='COMPLETED',run.safe_error_message
    assert run.records_succeeded==1
    item=f.items(db,run.id)[0];assert item.payload['person_number']==h.person.person_number
    assert 'annual_base_salary' not in item.payload and 'personal_email' not in item.payload
    output=f.download(db,run.id)[1].read_text(encoding='utf-8-sig');assert h.person.person_number in output
    with pytest.raises(Conflict):f.execute(db,d.id,s.RunRequest(request_key=run.request_key))
    with pytest.raises(Conflict):f.retry(db,run.id,run_request())

@pytest.mark.parametrize('kind',['PAYROLL_EXPORT','FBP_EXPORT'])
def test_seeded_exports(db,kind):
    d=f.create(db,definition(integration_type=kind));run=f.execute(db,d.id,run_request())
    assert run.status=='COMPLETED',run.safe_error_message
    for item in f.items(db,run.id):
        assert item.payload['person_number'] and item.payload['assignment_number']
        assert 'id' not in item.payload

@pytest.fixture
def partner(monkeypatch):
    state={'statuses':[200], 'requests':[], 'delay':0}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['requests'].append((body,self.headers.get('Idempotency-Key')))
            time.sleep(state['delay'])
            try:
                self.send_response(state['statuses'].pop(0) if len(state['statuses'])>1 else state['statuses'][0]);self.end_headers()
            except (BrokenPipeError,ConnectionResetError):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setattr(settings,'allow_private_integration_targets',True)
    state['url']=f'http://127.0.0.1:{server.server_port}/partner'
    try:yield state
    finally:server.shutdown();server.server_close();thread.join()

def http_definition(partner):return definition(transport_type='HTTP_REST',endpoint_url=partner['url'],http_method='POST',configuration={'auth_type':'BEARER_ENV','credential_env_key':'INTEGRATION_TOKEN_TEST'})

def test_http_retry_failed_only(db,partner,monkeypatch):
    monkeypatch.setattr(payloads,'outbound',lambda *args:[{'person_number':'SYNTHETIC_A'},{'person_number':'SYNTHETIC_B'}])
    partner['statuses']=[200,503]
    d=f.create(db,http_definition(partner));run=f.execute(db,d.id,run_request())
    assert run.status=='COMPLETED_WITH_ERRORS' and run.records_succeeded==1 and run.records_failed==1
    partner['statuses']=[200]
    retried=f.retry(db,run.id,run_request());assert retried.status=='COMPLETED' and retried.records_read==1
    assert retried.retry_of_run_id==run.id
    assert partner['requests'][1]==partner['requests'][2]
    assert len(partner['requests'])==3
    serialized=s.RunRead.model_validate(run).model_dump_json()+s.ItemRead.model_validate(f.items(db,run.id)[0]).model_dump_json()
    assert 'synthetic-test-token' not in serialized and 'Authorization' not in serialized
    with pytest.raises(Conflict):f.retry(db,run.id,run_request())

@pytest.mark.parametrize('status',[400,500,302])
def test_http_failures(db,partner,monkeypatch,status):
    monkeypatch.setattr(payloads,'outbound',lambda *args:[{'person_number':'SYNTHETIC'}]);partner['statuses']=[status]
    d=f.create(db,http_definition(partner));run=f.execute(db,d.id,run_request());assert run.status=='FAILED'
    assert f.items(db,run.id)[0].response_status==status
    assert len(partner['requests'])==1

def test_timeout(db,partner,monkeypatch):
    monkeypatch.setattr(payloads,'outbound',lambda *args:[{'person_number':'SYNTHETIC'}])
    monkeypatch.setattr(settings,'integration_http_timeout_seconds',.1);partner['delay']=.3
    d=f.create(db,http_definition(partner));run=f.execute(db,d.id,run_request());assert run.status=='FAILED'
    assert f.items(db,run.id)[0].response_status is None

def test_inbound_person_mixed_csv_and_replay(db,refs):
    h=employment.hire(db,request(refs));d=f.create(db,inbound())
    run=f.execute(db,d.id,run_request(records=[{'person_number':h.person.person_number,'preferred_name':'Synthetic renamed'},{'person_number':'MISSING_SYNTHETIC','first_name':'Missing'}]))
    assert run.status=='COMPLETED_WITH_ERRORS' and run.records_succeeded==1
    assert db.get(m.Person,h.person.id).preferred_name=='Synthetic renamed'
    retry=f.retry(db,run.id,run_request());assert retry.records_read==1 and retry.status=='FAILED'
    csvdef=f.create(db,inbound(transport_type='FILE',output_format='CSV'))
    csv=f.execute(db,csvdef.id,run_request(csv_content=f'person_number,preferred_name\n{h.person.person_number},CSV Synthetic\n'))
    assert csv.status=='COMPLETED'
    with pytest.raises(InvalidOperation):f.execute(db,d.id,run_request(records=[{'password':'not-allowed'}]))
    with pytest.raises(InvalidOperation):f.execute(db,d.id,run_request(records=[{'person_number':'DUP'},{'person_number':'DUP'}]))

def test_inbound_assignment_compensation(db,refs):
    h=employment.hire(db,request(refs))
    row={'assignment_number':h.assignment.assignment_number,'effective_date':'2025-01-01','work_time_type':'FULL_TIME','status':'ACTIVE'}
    for model,key in [(m.BusinessUnit,'business_unit'),(m.Department,'department'),(m.Job,'job'),(m.Grade,'grade'),(m.Location,'location')]:row[key+'_code']=db.get(model,refs[key+'_id']).code
    d=f.create(db,inbound('ASSIGNMENT_CHANGE'));run=f.execute(db,d.id,run_request(records=[row]));assert run.status=='COMPLETED'
    c=f.create(db,inbound('COMPENSATION_CHANGE'));run=f.execute(db,c.id,run_request(records=[{'assignment_number':h.assignment.assignment_number,'effective_date':'2025-01-01','annual_base_salary':'123456.78','currency':'INR'}]));assert run.status=='COMPLETED'
    invalid=f.execute(db,c.id,run_request(records=[{'assignment_number':h.assignment.assignment_number,'effective_date':'2025-01-01','annual_base_salary':'-1','currency':'INR'}]));assert invalid.status=='FAILED'

def test_api_auth_and_safe_validation(client,db,refs):
    auth=headers(db,'ADMIN');emp=headers(db,'EMPLOYEE');h=employment.hire(db,request(refs));db.commit()
    created=client.post('/integrations',headers=auth,json=definition().model_dump(mode='json'));assert created.status_code==201,created.text
    identifier=created.json()['id']
    assert client.post('/integrations',headers=auth,json=created.json()).status_code==422
    for path in ['/integrations','/integrations/runs','/integrations/'+identifier]:assert client.get(path,headers=emp).status_code==403
    assert client.post('/integrations/'+identifier+'/run',headers=emp,json={'request_key':'test'}).status_code==403
    run=client.post('/integrations/'+identifier+'/run',headers=auth,json={'request_key':'test'});assert run.status_code==200 and run.json()['status']=='COMPLETED',run.text
    for suffix in ['', '/items','/download']:assert client.get('/integrations/runs/'+run.json()['id']+suffix,headers=auth).status_code==200
    value=inbound().model_dump(mode='json');res=client.post('/integrations',headers=auth,json=value);assert res.status_code==201,res.text
    path='/integrations/inbound/'+value['code']
    assert client.post(path,headers=emp,json={'records':[]}).status_code==401
    response=client.post(path,headers={'X-Integration-Key':'synthetic-test-token','Idempotency-Key':'partner-test'},json={'records':[{'person_number':h.person.person_number,'preferred_name':'Partner synthetic'}]})
    assert response.status_code==200 and response.json()['status']=='COMPLETED',response.text
    assert 'synthetic-test-token' not in response.text
    assert client.post(path,headers={'X-Integration-Key':'synthetic-test-token','Idempotency-Key':'partner-test'},json={'records':[{'person_number':h.person.person_number}]}).status_code==409
    value['configuration']['password']='secret-not-echoed'
    response=client.post('/integrations',headers=auth,json=value);assert response.status_code==422 and 'secret-not-echoed' not in response.text

def test_seed_unique_disabled_and_path(db):
    demo.seed(db);assert demo.seed(db)==0
    value=definition();f.create(db,value)
    with pytest.raises(Conflict):f.create(db,value)
    d=f.create(db,definition(is_active=False))
    with pytest.raises(Conflict):f.execute(db,d.id,run_request())
    for path in ['../secret.json','C:/secret.csv','invalid.csv']:
        with pytest.raises(InvalidOperation):f.output_path(path)


def test_migration_upgrade_downgrade_upgrade_isolated_schema():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect, text
    from app.core.database import engine
    schema='integrations_test_'+uuid4().hex
    modules={}
    for path in Path('alembic/versions').glob('*.py'):
        spec=importlib.util.spec_from_file_location(path.stem,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        modules[module.revision]=module
    ordered=[];head='62ab7b30ce2d'
    while head:
        ordered.insert(0,modules[head]);head=modules[head].down_revision
    with engine.connect() as connection:
        transaction=connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            with Operations.context(MigrationContext.configure(connection)):
                for migration in ordered:migration.upgrade()
                assert 'integration_runs' in inspect(connection).get_table_names(schema=schema)
                ordered[-1].downgrade()
                assert 'integration_runs' not in inspect(connection).get_table_names(schema=schema)
                assert 'payroll_results' in inspect(connection).get_table_names(schema=schema)
                ordered[-1].upgrade()
                assert 'integration_run_items' in inspect(connection).get_table_names(schema=schema)
        finally:transaction.rollback()


def test_retry_cap_scope_and_failed_file(db,monkeypatch):
    monkeypatch.setattr(payloads,'outbound',lambda *args:[{'person_number':'SYNTHETIC'}])
    def fail(*args):raise OSError('private filesystem details')
    monkeypatch.setattr(f,'write_file',fail)
    d=f.create(db,definition());run=f.execute(db,d.id,run_request())
    assert run.status=='FAILED' and 'private' not in run.safe_error_message
    for depth in range(1,4):
        run=f.retry(db,run.id,run_request());assert run.retry_depth==depth
    with pytest.raises(Conflict):f.retry(db,run.id,run_request())
    run=f.execute(db,d.id,run_request())
    f.update(db,d.id,definition(code=d.code,output_format='CSV'))
    with pytest.raises(Conflict):f.retry(db,run.id,run_request())

def test_orphan_cleanup(db):
    import os
    from scripts.cleanup_integration_orphans import cleanup
    d=f.create(db,definition());run=f.execute(db,d.id,run_request())
    retained=f.download(db,run.id)[1];orphan=f.output_path(str(uuid4())+'.json');orphan.write_text('[]')
    for path in (retained,orphan):os.utime(path,(1,1))
    assert cleanup(db,1)==1 and retained.exists() and not orphan.exists()

def test_private_definition_read_after_security_setting_change(db,partner,monkeypatch):
    d=f.create(db,http_definition(partner));monkeypatch.setattr(settings,'allow_private_integration_targets',False)
    assert s.DefinitionRead.model_validate(d).endpoint_url==partner['url']
    with pytest.raises(InvalidOperation):f.execute(db,d.id,run_request())

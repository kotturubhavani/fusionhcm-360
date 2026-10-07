"""Bounded synchronous runs with independent items and explicit retry lineage."""
import json,re,time
from datetime import datetime,UTC
from uuid import uuid4
from sqlalchemy import select
from app import models as m
from app.core.config import settings
from app.schemas import integrations as s
from app.services.core_hr.common import atomic,get,Conflict,InvalidOperation,NotFound
from app.services.imports import templates,operations
from app.services.analytics.reports import csv_bytes
from . import payloads,security


def listing(db,model,offset=0,limit=50):
    return db.scalars(select(model).order_by(model.created_at.desc(),model.id).offset(offset).limit(limit)).all()
def items(db,identifier,offset=0,limit=100):
    get(db,m.IntegrationRun,identifier)
    return db.scalars(select(m.IntegrationRunItem).where(m.IntegrationRunItem.integration_run_id==identifier).order_by(m.IntegrationRunItem.sequence_number).offset(offset).limit(limit)).all()
def output_path(filename):
    if not re.fullmatch(r'[0-9a-f-]{36}\.(csv|json)',filename):raise InvalidOperation('Invalid artifact reference.')
    root=settings.integration_output_dir.resolve();path=(root/filename).resolve()
    if path.parent!=root:raise InvalidOperation('Invalid artifact reference.')
    return path

def write_file(filename,records,format):
    path=output_path(filename);path.parent.mkdir(parents=True,exist_ok=True)
    flat=[{k:json.dumps(v,ensure_ascii=True) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in records]
    content=csv_bytes(list(flat[0]) if flat else ['no_records'],flat) if format=='CSV' else json.dumps(records,ensure_ascii=False,indent=2).encode()
    with path.open('xb') as stream:stream.write(content)


def check_reference(payload):
    key=payload.configuration.credential_env_key
    if key and key not in settings.integration_credential_env_keys:raise InvalidOperation('Credential reference is not enabled in application settings.')

@atomic
def create(db,payload,user_id=None):
    check_reference(payload)
    row=m.IntegrationDefinition(**payload.model_dump(mode='json'),created_by_user_id=user_id);db.add(row);db.flush();return row
@atomic
def update(db,identifier,payload):
    check_reference(payload);row=get(db,m.IntegrationDefinition,identifier,lock=True)
    if row.direction!=payload.direction or row.integration_type!=payload.integration_type:raise Conflict('Create a new definition to change direction or business type.')
    for key,value in payload.model_dump(mode='json').items():setattr(row,key,value)
    db.flush();return row


def inbound_rows(definition,request):
    if definition.transport_type=='FILE':
        if request.csv_content is None or request.records is not None:raise InvalidOperation('FILE inbound requires csv_content only.')
        rows=[r for _,r in templates.parse(definition.integration_type,request.csv_content.encode('utf-8'))]
    else:
        if request.records is None or request.csv_content is not None:raise InvalidOperation('REST inbound requires records only.')
        rows=request.records
    if not rows or len(rows)>settings.integration_max_items:raise InvalidOperation('Supply between 1 and the configured maximum items.')
    allowed=set(templates.TEMPLATES[definition.integration_type])
    for row in rows:
        if set(row)-allowed or any(len(v)>10000 for v in row.values()):raise InvalidOperation('Unknown fields or excessive field size; payload was not retained.')
    targets=[r.get("person_number" if definition.integration_type=="PERSON_UPDATE" else "assignment_number", "").strip().upper() for r in rows]
    if len(targets)!=len(set(targets)):raise InvalidOperation("Only one operation per target is allowed per request.")
    return rows


def business_reference(row):
    return ' / '.join(str(row[k]) for k in ('person_number','assignment_number','period','plan') if row.get(k))[:255] or 'Unresolved record'

@atomic
def execute(db,identifier,request,user_id=None,trigger='MANUAL',retry_id=None):
    definition=get(db,m.IntegrationDefinition,identifier,lock=True)
    if not definition.is_active:raise Conflict('Activate the integration before execution.')
    if db.scalar(select(m.IntegrationRun.id).where(m.IntegrationRun.integration_definition_id==identifier,m.IntegrationRun.request_key==request.request_key)):
        raise Conflict('This request key already has a run. Inspect history instead of resubmitting.')
    contract=s.DefinitionCreate.model_validate(definition);check_reference(contract)
    original=None;source=[]
    if retry_id:
        original=get(db,m.IntegrationRun,retry_id,lock=True)
        if original.integration_definition_id!=identifier or original.status not in ('FAILED','COMPLETED_WITH_ERRORS') or original.retry_depth>=3:raise Conflict('This run is not eligible for retry.')
        if db.scalar(select(m.IntegrationRun.id).where(m.IntegrationRun.retry_of_run_id==retry_id)):raise Conflict('A retry already exists. Inspect the latest retry run.')
        # Retries keep business scope/payload frozen; destination/credential can be repaired explicitly.
        previous=s.DefinitionCreate.model_validate(original.definition_snapshot)
        current=contract.model_dump(mode='json');old=previous.model_dump(mode='json')
        for name in ('endpoint_url','http_method','is_active','name','description','code'):current.pop(name,None);old.pop(name,None)
        for values in (current,old):
            values['configuration'].pop('auth_type',None);values['configuration'].pop('credential_env_key',None)
        if current!=old:raise Conflict('Retry requires unchanged business scope and transport.')
        source=[item for item in items(db,retry_id) if item.status=='FAILED']
        if not source:raise Conflict('No failed items are available to retry.')
        records=[item.payload for item in source]
    elif contract.direction=='INBOUND':records=inbound_rows(contract,request)
    else:
        if request.records is not None or request.csv_content is not None:raise InvalidOperation('Outbound runs read existing domain data; do not supply payloads.')
        records=None
    run=m.IntegrationRun(integration_definition_id=identifier,requested_by_user_id=user_id,retry_of_run_id=retry_id,retry_depth=original.retry_depth+1 if original else 0,request_key=request.request_key,status='RUNNING',trigger_type=trigger,started_at=datetime.now(UTC),definition_snapshot=contract.model_dump(mode='json'),request_metadata={'transport':contract.transport_type,'direction':contract.direction},records_read=0,records_succeeded=0,records_failed=0)
    db.add(run);db.flush()
    try:
        with db.begin_nested():
            if records is None:records=payloads.outbound(db,contract)
            if len(records)>settings.integration_max_items:raise InvalidOperation('Export exceeds the configured item limit.')
            run.records_read=len(records)
            work=[]
            for index,record in enumerate(records,1):
                key=source[index-1].delivery_key if source else str(uuid4())
                item=m.IntegrationRunItem(integration_run_id=run.id,sequence_number=index,delivery_key=key,business_reference=business_reference(record),payload=record,status='PENDING');db.add(item);work.append(item)
            db.flush()
            if contract.direction=='OUTBOUND' and contract.transport_type=='FILE':
                filename=f'{run.id}.{contract.output_format.lower()}'
                try:
                    write_file(filename,records,contract.output_format);run.output_filename=filename
                    for item in work:item.status='SUCCESS'
                except Exception:
                    try:output_path(filename).unlink(missing_ok=True)
                    except OSError:pass
                    for item in work:item.status='FAILED';item.safe_error_message='Local output could not be generated.'
                    run.safe_error_message='Local output could not be generated.'
            else:
                deadline=time.monotonic()+30
                for item in work:
                    try:
                        if time.monotonic()>deadline:raise InvalidOperation('Run time limit reached.')
                        if contract.direction=='INBOUND':
                            with db.begin_nested():
                                identity,payload=operations.prepare(db,contract.integration_type,item.payload)
                                operations.apply(db,contract.integration_type,identity,payload)
                            item.status='SUCCESS'
                        else:
                            status=security.deliver(contract,item.payload,item.delivery_key);item.response_status=status
                            if not 200<=status<300:raise InvalidOperation('Partner rejected delivery.')
                            item.status='SUCCESS'
                    except Exception:
                        item.status='FAILED';item.safe_error_message='Business validation or delivery failed; verify input, destination and credential configuration before retry.'
                    db.flush()
            run.records_succeeded=sum(i.status=='SUCCESS' for i in work);run.records_failed=sum(i.status=='FAILED' for i in work)
            run.status='COMPLETED_WITH_ERRORS' if run.records_failed and run.records_succeeded else 'FAILED' if run.records_failed or run.safe_error_message else 'COMPLETED'
            run.response_metadata={'successful_items':run.records_succeeded,'failed_items':run.records_failed}
            db.flush()
    except Exception:
        run.status='FAILED';run.safe_error_message='Run failed. Delivery may be uncertain; inspect partner receipts before starting a new run.'
    run.completed_at=datetime.now(UTC);db.flush();return run

@atomic
def retry(db,identifier,request,user_id=None):
    if request.records is not None or request.csv_content is not None:raise InvalidOperation('Retries use saved failed payloads only.')
    original=get(db,m.IntegrationRun,identifier,lock=True)
    return execute(db,original.integration_definition_id,request,user_id,retry_id=identifier)

def download(db,identifier):
    run=get(db,m.IntegrationRun,identifier)
    if run.status!='COMPLETED' or not run.output_filename:raise Conflict('No completed FILE output is available.')
    path=output_path(run.output_filename)
    if not path.is_file():raise NotFound('Output artifact is unavailable.')
    return run,path

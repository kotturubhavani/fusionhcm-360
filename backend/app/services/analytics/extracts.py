"""Local outbound artifacts. Watermarks use application timestamps, not CDC."""
import json,re
from datetime import UTC,datetime
from sqlalchemy import func,select
from app import models as m
from app.core.config import settings
from app.schemas import analytics as s
from app.services.core_hr.common import atomic,get,Conflict,NotFound,InvalidOperation
from . import data,reports
from .metadata import EXTRACT_DOMAINS,DOMAINS


def output_path(filename):
    if not re.fullmatch(r'[0-9a-f-]{36}\.(csv|json)',filename):raise InvalidOperation('Invalid output reference.')
    root=settings.extract_output_dir.resolve();path=(root/filename).resolve()
    if path.parent!=root:raise InvalidOperation('Invalid output reference.')
    return path

def write_output(filename,content):
    path=output_path(filename);path.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive creation avoids overwriting any prior artifact.
    with path.open('xb') as stream:stream.write(content)

@atomic
def create(db,payload):
    row=m.ExtractDefinition(**payload.model_dump(mode='json'));db.add(row);db.flush();return row
@atomic
def update(db,identifier,payload):
    row=get(db,m.ExtractDefinition,identifier,lock=True)
    if row.last_successful_run_at and (payload.extract_type!=row.extract_type or payload.configuration.model_dump(mode='json')!=row.configuration):
        raise Conflict('Create a new definition to change scope after a successful run; its watermark starts fresh.')
    for k,v in payload.model_dump(mode='json').items():setattr(row,k,v)
    db.flush();return row

def interval(changed,lower,upper):return (lower is None or changed>lower) and changed<=upper

@atomic
def run(db,identifier,payload,user_id=None):
    definition=get(db,m.ExtractDefinition,identifier,lock=True)
    if not definition.is_active:raise Conflict('Activate the extract before running it.')
    upper=db.scalar(select(func.clock_timestamp()))
    lower=definition.last_successful_run_at if payload.mode=='INCREMENTAL' else None
    snapshot=s.ExtractCreate.model_validate(definition).model_dump(mode='json')
    row=m.ExtractRun(extract_definition_id=identifier,requested_by_user_id=user_id,status='RUNNING',mode=payload.mode,watermark_from=lower,watermark_to=upper,started_at=upper,definition_snapshot=snapshot)
    db.add(row);db.flush();filename=f'{row.id}.{definition.output_format.lower()}'
    try:
        with db.begin_nested():
            contract=s.ExtractCreate.model_validate(definition);domain=EXTRACT_DOMAINS[contract.extract_type]
            if contract.extract_type=='WORKER_CHANGES':items=data.worker_rows(db,upper.date(),changes=True)
            elif contract.extract_type=='FBP_ELECTIONS':items=data.election_rows(db,upper.date())
            else:items=data.domain_rows(db,domain,upper.date())
            items=[r for r in items if interval(r['_changed'],lower,upper)]
            items=reports.filtered(items,domain,contract.configuration.filters,[])
            columns=list(DOMAINS[domain])+(['component','component_name'] if contract.extract_type=='FBP_ELECTIONS' else [])
            output=reports.json_safe([{c:r.get(c) for c in columns} for r in items])
            content=reports.csv_bytes(columns,output) if contract.output_format=='CSV' else json.dumps(output,ensure_ascii=False,indent=2).encode('utf-8')
            write_output(filename,content)
        row.row_count=len(output);row.output_filename=filename;row.status='COMPLETED';definition.last_successful_run_at=upper
    except Exception:
        try:
            output_path(filename).unlink(missing_ok=True)
        except OSError:
            pass  # The failed run exposes no artifact; local cleanup can remove it later.
        row.status='FAILED';row.error_message='Extract generation failed; check source data limits and local output storage.'
    row.completed_at=datetime.now(UTC);db.flush();return row

def download(db,identifier):
    row=get(db,m.ExtractRun,identifier)
    if row.status!='COMPLETED' or not row.output_filename:raise Conflict('Only completed extracts have output.')
    path=output_path(row.output_filename)
    if not path.is_file():raise NotFound('Output is unavailable or has been removed by local retention cleanup.')
    return row,path

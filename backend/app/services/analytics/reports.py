"""Bounded snapshots and exact typed filtering; no client SQL."""
import csv,io,json
from datetime import date,datetime,UTC
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select
from openpyxl import Workbook
from app import models as m
from app.schemas import analytics as s
from app.services.core_hr.common import atomic,get,Conflict
from . import data
from .metadata import DOMAINS,label


def serial(value):
    if isinstance(value,(date,datetime,Decimal,UUID)):return str(value) if isinstance(value,(Decimal,UUID)) else value.isoformat()
    raise TypeError('Unsupported report value')

def json_safe(value):return json.loads(json.dumps(value,default=serial))
def cell(value):
    if value is None:return ''
    text=str(value)
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) else text

def csv_bytes(columns,rows):
    output=io.StringIO(newline='');writer=csv.writer(output);writer.writerow([label(c) for c in columns])
    for row in rows:writer.writerow([cell(row.get(c)) for c in columns])
    return output.getvalue().encode('utf-8-sig')

def xlsx_bytes(columns,rows):
    workbook=Workbook();sheet=workbook.active;sheet.title='Report';sheet.append([label(c) for c in columns])
    for row in rows:sheet.append([cell(row.get(c)) for c in columns])
    sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
    output=io.BytesIO();workbook.save(output);workbook.close();return output.getvalue()

def matches(row,f,kind):
    value=row.get(f.field)
    if value is None:return False
    expected=[s.typed(v,kind) for v in f.value] if isinstance(f.value,list) else s.typed(f.value,kind)
    return {'equals':lambda:value==expected,'not_equals':lambda:value!=expected,'contains':lambda:str(expected).casefold() in str(value).casefold(),'in':lambda:value in expected,'greater_than':lambda:value>expected,'less_than':lambda:value<expected,'date_on_or_after':lambda:value>=expected,'date_on_or_before':lambda:value<=expected}[f.operator]()

def filtered(rows,domain,filters,sorts):
    result=[row for row in rows if all(matches(row,f,DOMAINS[domain][f.field]) for f in filters)]
    result.sort(key=lambda row:row['_key'])
    for sort in reversed(sorts):result.sort(key=lambda row:(row.get(sort.field) is None,row.get(sort.field)),reverse=sort.direction=='desc')
    return result

def listing(db,model,offset=0,limit=50):
    return db.scalars(select(model).order_by(model.created_at.desc(),model.id).offset(offset).limit(limit)).all()

@atomic
def create_report(db,payload,user_id=None):
    row=m.ReportDefinition(**payload.model_dump(mode='json'),created_by_user_id=user_id);db.add(row);db.flush();return row
@atomic
def update_report(db,identifier,payload):
    row=get(db,m.ReportDefinition,identifier,lock=True)
    for k,v in payload.model_dump(mode='json').items():setattr(row,k,v)
    db.flush();return row
@atomic
def run_report(db,identifier,payload,user_id=None):
    definition=get(db,m.ReportDefinition,identifier,lock=True)
    if not definition.is_active:raise Conflict('Activate the report before running it.')
    snapshot=s.ReportCreate.model_validate(definition).model_dump(mode='json');snapshot['as_of']=payload.as_of.isoformat()
    run=m.ReportRun(report_definition_id=identifier,requested_by_user_id=user_id,status='RUNNING',definition_snapshot=snapshot)
    db.add(run);db.flush()
    try:
        with db.begin_nested():
            contract=s.ReportCreate.model_validate(definition)
            rows=filtered(data.domain_rows(db,contract.domain,payload.as_of),contract.domain,contract.filters,contract.sort_definition)
            output=json_safe([{c:row.get(c) for c in contract.selected_columns} for row in rows])
        run.result_payload=output;run.row_count=len(output);run.status='COMPLETED'
    except Exception:
        run.status='FAILED';run.error_message='Report generation failed; check the definition and source data limits.'
    run.completed_at=datetime.now(UTC);db.flush();return run

def results(db,identifier,offset=0,limit=100):
    run=get(db,m.ReportRun,identifier)
    if run.status!='COMPLETED':raise Conflict('Only completed reports have results.')
    return {'columns':run.definition_snapshot['selected_columns'],'total':run.row_count,'rows':run.result_payload[offset:offset+limit]}

def export(db,identifier,format):
    run=get(db,m.ReportRun,identifier)
    if run.status!='COMPLETED':raise Conflict('Only completed reports can be exported.')
    return (csv_bytes if format=='csv' else xlsx_bytes)(run.definition_snapshot['selected_columns'],run.result_payload)

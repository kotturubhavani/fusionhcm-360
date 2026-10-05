"""Management-only reporting and local extract downloads."""
from uuid import UUID
from fastapi import APIRouter,Depends,Query
from fastapi.responses import Response,FileResponse
from sqlalchemy.orm import Session
from app import models as m
from app.api.core_hr import CoreHRRoute,save
from app.api.dependencies import require_hr
from app.core.database import get_db
from app.schemas import analytics as s
from app.services.analytics import reports as r,extracts as e,metadata
from app.services.core_hr.common import get
reports=APIRouter(prefix='/reports',tags=['Reports'],route_class=CoreHRRoute,dependencies=[Depends(require_hr)])
extracts=APIRouter(prefix='/extracts',tags=['Extracts'],route_class=CoreHRRoute,dependencies=[Depends(require_hr)])

@reports.get('/metadata')
def fields():return metadata.metadata()
@reports.get('/runs',response_model=list[s.ReportRunRead])
def report_runs(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=Depends(get_db)):
    return r.listing(db,m.ReportRun,offset,limit)
@reports.get('/runs/{identifier}',response_model=s.ReportRunRead)
def report_run(identifier:UUID,db:Session=Depends(get_db)):return get(db,m.ReportRun,identifier)
@reports.get('/runs/{identifier}/results')
def results(identifier:UUID,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=100),db:Session=Depends(get_db)):return r.results(db,identifier,offset,limit)
@reports.get('/runs/{identifier}/export.csv')
def csv_export(identifier:UUID,db:Session=Depends(get_db)):
    return Response(r.export(db,identifier,'csv'),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="report-{identifier}.csv"'})
@reports.get('/runs/{identifier}/export.xlsx')
def xlsx_export(identifier:UUID,db:Session=Depends(get_db)):
    return Response(r.export(db,identifier,'xlsx'),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="report-{identifier}.xlsx"'})
@reports.get('',response_model=list[s.ReportRead])
def report_list(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=Depends(get_db)):return r.listing(db,m.ReportDefinition,offset,limit)
@reports.post('',response_model=s.ReportRead,status_code=201)
def create_report(payload:s.ReportCreate,user:m.User=Depends(require_hr),db:Session=Depends(get_db)):return save(db,r.create_report,payload,user.id)
@reports.get('/{identifier}',response_model=s.ReportRead)
def report_detail(identifier:UUID,db:Session=Depends(get_db)):return get(db,m.ReportDefinition,identifier)
@reports.patch('/{identifier}',response_model=s.ReportRead)
def edit_report(identifier:UUID,payload:s.ReportCreate,db:Session=Depends(get_db)):return save(db,r.update_report,identifier,payload)
@reports.post('/{identifier}/run',response_model=s.ReportRunRead)
def execute_report(identifier:UUID,payload:s.ReportRequest,user:m.User=Depends(require_hr),db:Session=Depends(get_db)):return save(db,r.run_report,identifier,payload,user.id)
@extracts.get('/definitions',response_model=list[s.ExtractRead])
def extract_list(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=Depends(get_db)):return r.listing(db,m.ExtractDefinition,offset,limit)
@extracts.post('/definitions',response_model=s.ExtractRead,status_code=201)
def create_extract(payload:s.ExtractCreate,db:Session=Depends(get_db)):return save(db,e.create,payload)
@extracts.get('/definitions/{identifier}',response_model=s.ExtractRead)
def extract_detail(identifier:UUID,db:Session=Depends(get_db)):return get(db,m.ExtractDefinition,identifier)
@extracts.patch('/definitions/{identifier}',response_model=s.ExtractRead)
def edit_extract(identifier:UUID,payload:s.ExtractCreate,db:Session=Depends(get_db)):return save(db,e.update,identifier,payload)
@extracts.post('/definitions/{identifier}/run',response_model=s.ExtractRunRead)
def execute_extract(identifier:UUID,payload:s.ExtractRequest,user:m.User=Depends(require_hr),db:Session=Depends(get_db)):return save(db,e.run,identifier,payload,user.id)
@extracts.get('/runs',response_model=list[s.ExtractRunRead])
def extract_runs(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=Depends(get_db)):return r.listing(db,m.ExtractRun,offset,limit)
@extracts.get('/runs/{identifier}',response_model=s.ExtractRunRead)
def extract_run(identifier:UUID,db:Session=Depends(get_db)):return get(db,m.ExtractRun,identifier)
@extracts.get('/runs/{identifier}/download')
def download(identifier:UUID,db:Session=Depends(get_db)):
    row,path=e.download(db,identifier)
    return FileResponse(path,filename=row.output_filename,media_type='text/csv' if path.suffix=='.csv' else 'application/json')

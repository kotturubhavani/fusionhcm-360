"""HR/ADMIN CSV imports with bounded multipart requests."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.concurrency import run_in_threadpool
from python_multipart.exceptions import MultipartParseError
from sqlalchemy.orm import Session
from app import models as m
from app.api.core_hr import CoreHRRoute, save
from app.api.dependencies import require_hr
from app.core.config import settings
from app.core.database import get_db
from app.schemas.imports import JobRead, RowRead
from app.services.core_hr.common import get
from app.services.imports import service as f, templates

router=APIRouter(prefix='/imports',tags=['Bulk imports'],route_class=CoreHRRoute,dependencies=[Depends(require_hr)])


@router.get('/templates')
def list_templates():
    return [{'object_type':kind,'columns':columns,'required':templates.required(kind)} for kind,columns in templates.TEMPLATES.items()]


@router.get('/templates/{object_type}')
def download_template(object_type: str):
    return Response(templates.template(object_type),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{object_type}.csv"'})


@router.post('',response_model=JobRead,status_code=201)
async def upload(request: Request,user:m.User=Depends(require_hr),db:Session=Depends(get_db)):
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>settings.import_max_file_bytes+65536:
            raise HTTPException(413,'Upload exceeds the configured request size limit.')
    async def receive():
        return {'type':'http.request','body':bytes(content),'more_body':False}
    bounded=Request(request.scope,receive)
    try:
        async with bounded.form(max_files=1,max_fields=1,max_part_size=65536) as form:
            if len(form.multi_items())!=2 or set(form.keys())!={'object_type','file'}:
                raise HTTPException(422,'Supply exactly object_type and file.')
            file=form['file'];kind=form['object_type']
            if not isinstance(file,UploadFile) or not isinstance(kind,str):
                raise HTTPException(422,'Supply a CSV file and object_type.')
            contents=await file.read(settings.import_max_file_bytes+1)
            return await run_in_threadpool(save,db,f.upload,kind,file.filename,contents,user.id)
    except MultipartParseError:
        raise HTTPException(422,'Malformed multipart upload.') from None
    except StarletteHTTPException as exc:
        if exc.status_code==400:
            raise HTTPException(422,'Malformed multipart upload.') from None
        raise


@router.get('',response_model=list[JobRead])
def jobs(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=Depends(get_db)):
    return f.jobs(db,offset,limit)


@router.get('/{job_id}',response_model=JobRead)
def detail(job_id:UUID,db:Session=Depends(get_db)):
    return get(db,m.ImportJob,job_id)


@router.get('/{job_id}/rows',response_model=list[RowRead])
def rows(job_id:UUID,status:Literal['PENDING','VALID','INVALID','PROCESSED','FAILED']|None=None,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=100),db:Session=Depends(get_db)):
    return f.rows(db,job_id,status,offset,limit)


@router.post('/{job_id}/validate',response_model=JobRead)
def validate(job_id:UUID,db:Session=Depends(get_db)):
    return save(db,f.validate,job_id)


@router.post('/{job_id}/process',response_model=JobRead)
def process(job_id:UUID,db:Session=Depends(get_db)):
    return save(db,f.process,job_id)


@router.get('/{job_id}/errors.csv')
def errors(job_id:UUID,db:Session=Depends(get_db)):
    return Response(f.errors_csv(db,job_id),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="import-{job_id}-errors.csv"'})

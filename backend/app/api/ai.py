"""Owned AI conversations and staff-only policy management."""
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from python_multipart.exceptions import MultipartParseError
from pydantic import ValidationError
from app import models as m
from app.api.dependencies import get_current_user,require_hr
from app.api.core_hr import CoreHRRoute,save
from app.core.database import get_db
from app.core.config import settings
from app.schemas import ai as s
from app.services.ai import service,documents
from app.services.core_hr.common import get,HRError

class AIRoute(CoreHRRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handler(request):
            try:return await original(request)
            except RequestValidationError:raise HTTPException(422,'Invalid assistant request.') from None
            except documents.AccessDenied:raise HTTPException(403,'Insufficient assistant permissions.') from None
        return handler
router=APIRouter(prefix='/ai',tags=['AI assistant'],route_class=AIRoute)

async def body(request,limit):
    content=bytearray()
    async for chunk in request.stream():
        if len(content)+len(chunk)>limit:raise HTTPException(413,'Request exceeds the size limit.')
        content.extend(chunk)
    return bytes(content)

@router.get('/capabilities')
def capabilities(user:m.User=Depends(get_current_user)):
    documents.authorized(user)
    return {'provider':settings.ai_provider,'mode':'Deterministic responses' if settings.ai_provider=='mock' else 'AI evidence selection','staff':documents.staff(user),'document_max_bytes':settings.ai_document_max_bytes,'streaming':False}

@router.post('/chat')
async def chat(request:Request,user:m.User=Depends(get_current_user),db:Session=Depends(get_db)):
    content=await body(request,16384)
    try:payload=s.ChatRequest.model_validate_json(content)
    except ValidationError:raise HTTPException(422,'Invalid chat request. Supply a message and request_key; use supported tool/filter fields only.') from None
    result=await run_in_threadpool(save,db,service.chat,user,payload)
    if result['status']=='DENIED':return JSONResponse(status_code=403,content={'detail':result['error']})
    return result

@router.get('/conversations',response_model=list[s.ConversationRead])
def conversations(offset:int=Query(0,ge=0),user:m.User=Depends(get_current_user),db:Session=Depends(get_db)):
    return service.conversations(db,user,offset)

@router.get('/conversations/{identifier}')
def history(identifier:UUID,user:m.User=Depends(get_current_user),db:Session=Depends(get_db)):
    row,messages=service.history(db,user,identifier)
    return {'conversation':s.ConversationRead.model_validate(row),'messages':[s.MessageRead.model_validate(r) for r in messages]}

@router.get('/documents',response_model=list[s.DocumentRead])
def documents_list(offset:int=Query(0,ge=0),user:m.User=Depends(require_hr),db:Session=Depends(get_db)):
    return db.scalars(select(m.Document).order_by(m.Document.created_at.desc(),m.Document.id).offset(offset).limit(30)).all()

@router.get('/documents/{identifier}',response_model=s.DocumentRead)
def document(identifier:UUID,user:m.User=Depends(require_hr),db:Session=Depends(get_db)):
    return get(db,m.Document,identifier)

def upload_and_save(db,user,filename,data,audience):
    try:return save(db,documents.ingest,user,filename,data,audience)
    except HRError:
        documents.audit(db,user,'UPLOAD_DOCUMENT','FAILED',{})
        db.commit()
        raise

@router.post('/documents',response_model=s.DocumentRead,status_code=201)
async def upload(request:Request,user:m.User=Depends(require_hr),db:Session=Depends(get_db)):
    content=await body(request,settings.ai_document_max_bytes+65536)
    async def receive():return {'type':'http.request','body':content,'more_body':False}
    bounded=Request(request.scope,receive)
    try:
        async with bounded.form(max_files=1,max_fields=1,max_part_size=1024) as form:
            if len(form.multi_items())!=2 or set(form.keys())!={'file','audience'}:raise HTTPException(422,'Supply exactly file and audience (ALL or STAFF).')
            file=form['file'];audience=form['audience']
            if not isinstance(file,UploadFile) or audience not in ('ALL','STAFF'):raise HTTPException(422,'Invalid document upload.')
            data=await file.read(settings.ai_document_max_bytes+1)
            return await run_in_threadpool(upload_and_save,db,user,file.filename,data,audience)
    except (MultipartParseError,StarletteHTTPException) as exc:
        if isinstance(exc,StarletteHTTPException) and exc.status_code!=400:raise
        raise HTTPException(422,'Malformed document upload.') from None

@router.post('/documents/{identifier}/reindex',response_model=s.DocumentRead)
def reindex(identifier:UUID,user:m.User=Depends(require_hr),db:Session=Depends(get_db)):
    return save(db,documents.reindex,user,identifier)

@router.patch('/documents/{identifier}',response_model=s.DocumentRead)
def state(identifier:UUID,payload:s.DocumentState,user:m.User=Depends(require_hr),db:Session=Depends(get_db)):
    return save(db,documents.set_active,user,identifier,payload.is_active)

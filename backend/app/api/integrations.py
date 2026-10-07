"""JWT-protected management and a separate integration-key inbound route."""
import json
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from fastapi.responses import FileResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app import models as m
from app.api.core_hr import CoreHRRoute,save
from app.api.dependencies import require_hr
from app.core.database import get_db
from app.schemas import integrations as s
from app.services.integrations import service as f,security
from app.services.core_hr.common import get
class IntegrationRoute(CoreHRRoute):
    def get_route_handler(self):
        handler=super().get_route_handler()
        async def safe(request):
            try:return await handler(request)
            except RequestValidationError:raise HTTPException(422,'Invalid integration request. Check the documented fields and configuration.') from None
        return safe
router=APIRouter(prefix='/integrations',tags=['Integration Center'],route_class=IntegrationRoute)
staff=[Depends(require_hr)]

async def bounded_body(request):
    content=bytearray()
    async for chunk in request.stream():
        if len(content)+len(chunk)>1024*1024:raise HTTPException(413,'Integration input exceeds 1 MiB.')
        content.extend(chunk)
    return bytes(content)
async def run_request(request):
    content=await bounded_body(request)
    try:return s.RunRequest.model_validate_json(content)
    except ValidationError:raise HTTPException(422,'Invalid run request. Use a request_key and typed records or csv_content.') from None

@router.post('/inbound/{code}',response_model=s.RunRead)
async def inbound(code:str,request:Request,db:Session=Depends(get_db)):
    definition=db.scalar(select(m.IntegrationDefinition).where(m.IntegrationDefinition.code==code.upper()))
    provided=request.headers.get('X-Integration-Key','')
    if not definition or definition.direction!='INBOUND' or not definition.is_active or not security.authorized(definition.configuration.get('credential_env_key'),provided):
        raise HTTPException(401,'Invalid integration credentials.')
    body=await bounded_body(request)
    try:
        key=request.headers.get('Idempotency-Key','')
        if definition.transport_type=='FILE':
            if request.headers.get('content-type','').split(';')[0]!='text/csv':raise ValueError()
            payload=s.RunRequest(request_key=key,csv_content=body.decode('utf-8-sig'))
        else:
            data=json.loads(body)
            if not isinstance(data,dict) or set(data)!={'records'}:raise ValueError()
            payload=s.RunRequest(request_key=key,records=data['records'])
    except (ValueError,UnicodeError):raise HTTPException(422,'Use the configured CSV or JSON records format and an Idempotency-Key.') from None
    return await run_in_threadpool(partner_execute,db,definition.id,payload,provided)

def partner_execute(db,identifier,payload,provided):
    # Recheck the credential under the writer lock so a concurrent rotation cannot
    # authorize a run using a stale definition read before the body was received.
    db.execute(text('SELECT pg_advisory_xact_lock(360, 1)'))
    definition=get(db,m.IntegrationDefinition,identifier,lock=True)
    if definition.direction!='INBOUND' or not definition.is_active or not security.authorized(definition.configuration.get('credential_env_key'),provided):
        raise HTTPException(401,'Invalid integration credentials.')
    return save(db,f.execute,identifier,payload,None,'API')

@router.get('/runs',response_model=list[s.RunRead],dependencies=staff)
def runs(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=Depends(get_db)):return f.listing(db,m.IntegrationRun,offset,limit)
@router.get('/runs/{identifier}',response_model=s.RunRead,dependencies=staff)
def run_detail(identifier:UUID,db:Session=Depends(get_db)):return get(db,m.IntegrationRun,identifier)
@router.get('/runs/{identifier}/items',response_model=list[s.ItemRead],dependencies=staff)
def items(identifier:UUID,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=100),db:Session=Depends(get_db)):return f.items(db,identifier,offset,limit)
@router.post('/runs/{identifier}/retry',response_model=s.RunRead)
async def retry(identifier:UUID,request:Request,user:m.User=Depends(require_hr),db:Session=Depends(get_db)):
    payload=await run_request(request)
    return await run_in_threadpool(save,db,f.retry,identifier,payload,user.id)
@router.get('/runs/{identifier}/download',dependencies=staff)
def download(identifier:UUID,db:Session=Depends(get_db)):
    run,path=f.download(db,identifier);return FileResponse(path,filename=run.output_filename,media_type='text/csv' if path.suffix=='.csv' else 'application/json')
@router.get('',response_model=list[s.DefinitionRead],dependencies=staff)
def definitions(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=Depends(get_db)):return f.listing(db,m.IntegrationDefinition,offset,limit)
@router.post('',response_model=s.DefinitionRead,status_code=201)
def create(payload:s.DefinitionCreate,user:m.User=Depends(require_hr),db:Session=Depends(get_db)):return save(db,f.create,payload,user.id)
@router.get('/{identifier}',response_model=s.DefinitionRead,dependencies=staff)
def detail(identifier:UUID,db:Session=Depends(get_db)):return get(db,m.IntegrationDefinition,identifier)
@router.patch('/{identifier}',response_model=s.DefinitionRead,dependencies=staff)
def update(identifier:UUID,payload:s.DefinitionCreate,db:Session=Depends(get_db)):return save(db,f.update,identifier,payload)
@router.post('/{identifier}/run',response_model=s.RunRead)
async def execute(identifier:UUID,request:Request,user:m.User=Depends(require_hr),db:Session=Depends(get_db)):
    payload=await run_request(request)
    return await run_in_threadpool(save,db,f.execute,identifier,payload,user.id)

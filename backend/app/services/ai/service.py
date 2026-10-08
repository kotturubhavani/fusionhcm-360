"""Authorized retrieval, constrained evidence selection, and owned history."""
from datetime import datetime,UTC
from sqlalchemy import select,func
from app import models as m
from app.core.config import settings
from app.services.core_hr.common import atomic,NotFound,InvalidOperation,HRError
from . import documents,orchestrator



def scope(user):return 'STAFF' if documents.staff(user) else 'SELF'
def conversation(db,user,identifier,lock=False):
    documents.authorized(user)
    query=select(m.AIConversation).where(m.AIConversation.id==identifier,m.AIConversation.user_id==user.id,m.AIConversation.scope==scope(user))
    if scope(user)=='SELF':query=query.where(m.AIConversation.person_id==user.person_id)
    if lock:query=query.with_for_update()
    row=db.scalar(query)
    if not row:raise NotFound('Conversation not found.')
    return row

def conversations(db,user,offset=0):
    documents.authorized(user)
    query=select(m.AIConversation).where(m.AIConversation.user_id==user.id,m.AIConversation.scope==scope(user))
    if scope(user)=='SELF':query=query.where(m.AIConversation.person_id==user.person_id)
    return db.scalars(query.order_by(m.AIConversation.updated_at.desc(),m.AIConversation.id).offset(offset).limit(30)).all()

def history(db,user,identifier):
    row=conversation(db,user,identifier)
    return row,db.scalars(select(m.AIMessage).where(m.AIMessage.conversation_id==identifier).order_by(m.AIMessage.sequence_number)).all()

@atomic
def chat(db,user,request):
    documents.authorized(user)
    previous=db.scalar(select(m.AIQueryAudit.id).where(m.AIQueryAudit.user_id==user.id,m.AIQueryAudit.details['request_key'].astext==str(request.request_key)))
    if previous:raise InvalidOperation('This request was already handled. Reload conversation history before retrying.')
    convo=None
    try:
        documents.safe_input(request.message)
        if request.conversation_id:convo=conversation(db,user,request.conversation_id,lock=True)
        if convo and db.scalar(select(func.count()).select_from(m.AIMessage).where(m.AIMessage.conversation_id==convo.id))>=100:raise InvalidOperation('Conversation limit reached. Start a new conversation.')
        result=orchestrator.run(db,user,request)
    except documents.AccessDenied as exc:
        db.add(m.AIQueryAudit(user_id=user.id,query_type='GUARDRAIL',action='ORCHESTRATE',status='DENIED',details={'request_key':str(request.request_key),'orchestrator_route':'DENIED','selected_agents':[],'agent_trace':[]}));db.flush()
        return {'status':'DENIED','error':str(exc),'query_type':'GUARDRAIL','orchestrator_route':'DENIED','selected_agents':[],'agent_trace':[],'sections':[],'structured_data':{},'citations':[]}
    except HRError as exc:
        db.add(m.AIQueryAudit(user_id=user.id,query_type='VALIDATION',action='ORCHESTRATE',status='FAILED',details={'request_key':str(request.request_key)}));db.flush()
        return {'status':'FAILED','error':str(exc),'selected_agents':[],'agent_trace':[],'citations':[],'structured_data':{}}
    if convo is None:
        convo=m.AIConversation(user_id=user.id,person_id=user.person_id,scope=scope(user),title=request.message.strip()[:100]);db.add(convo);db.flush()
    count=db.scalar(select(func.count()).select_from(m.AIMessage).where(m.AIMessage.conversation_id==convo.id))
    db.add(m.AIMessage(conversation_id=convo.id,sequence_number=count+1,role='user',content=request.message,details={}))
    details={k:v for k,v in result.items() if k!='answer'}
    details.update(provider=settings.ai_provider,request_key=str(request.request_key))
    message=m.AIMessage(conversation_id=convo.id,sequence_number=count+2,role='assistant',content=result['answer'],details=details);db.add(message)
    convo.updated_at=datetime.now(UTC)
    audit_details={k:details[k] for k in ('provider','request_key','orchestrator_route','selected_agents','agent_trace')}
    audit_details.update(outcome=result['status'],citation_ids=[c['id'] for c in result['citations']])
    db.add(m.AIQueryAudit(user_id=user.id,conversation_id=convo.id,query_type=result['query_type'],action='ORCHESTRATE',status='SUCCESS' if result['status']=='SUCCESS' else 'FAILED',details=audit_details));db.flush()
    return {'conversation_id':str(convo.id),'message_id':str(message.id),'answer':result['answer'],**details}

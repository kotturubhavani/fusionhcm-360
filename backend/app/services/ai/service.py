"""Authorized retrieval, constrained evidence selection, and owned history."""
from datetime import datetime,UTC
from sqlalchemy import select,func
from app import models as m
from app.services.core_hr.common import atomic,NotFound,InvalidOperation,HRError
from . import documents,tools,routing,providers

EXPLANATIONS={
 'payroll':'Gross is earnings before deductions. Net is gross less the deductions listed in the saved result. These are simulator calculations, not tax or payroll advice.',
 'fbp':'Allocated is the sum of saved component elections; remaining is the budget less allocated. OPEN budgets have not been submitted. This is a benefits-planning simulation, not benefits or tax advice.'}

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
    convo=None;kind='GENERAL_CHAT';tool=None
    # Replays are rejected before provider work; writer lock serializes concurrent requests.
    previous=db.scalar(select(m.AIQueryAudit.id).where(m.AIQueryAudit.user_id==user.id,m.AIQueryAudit.details['request_key'].astext==str(request.request_key)))
    if previous:raise InvalidOperation('This request was already handled. Reload conversation history before retrying.')
    try:
        documents.safe_input(request.message)
        if request.conversation_id:convo=conversation(db,user,request.conversation_id,lock=True)
        kind,tool=routing.route(user,request)
        data=tools.execute(db,user,tool,request) if tool else {}
        evidence=documents.retrieve(db,user,request.message,request.source_id,request.document_id) if kind in ('DOCUMENT_RAG','HYBRID') else []
    except documents.AccessDenied as exc:
        db.add(m.AIQueryAudit(user_id=user.id,query_type=kind,action=tool or 'ROUTE',status='DENIED',details={'request_key':str(request.request_key)}));db.flush()
        return {'status':'DENIED','error':str(exc)}
    except HRError as exc:
        # Validation/not-found errors are audited without retaining submitted text.
        db.add(m.AIQueryAudit(user_id=user.id,query_type=kind,action=tool or 'RETRIEVE',status='FAILED',details={'request_key':str(request.request_key)}));db.flush()
        return {'status':'FAILED','error':str(exc)}
    except providers.ProviderError:
        db.add(m.AIQueryAudit(user_id=user.id,query_type=kind,action='RETRIEVE',status='FAILED',details={'request_key':str(request.request_key)}));db.flush()
        return {'status':'FAILED','error':'Document retrieval is unavailable. Check the provider/vector store and retry.'}
    if convo is None:
        convo=m.AIConversation(user_id=user.id,person_id=user.person_id,scope=scope(user),title=request.message.strip()[:100]);db.add(convo);db.flush()
    count=db.scalar(select(func.count()).select_from(m.AIMessage).where(m.AIMessage.conversation_id==convo.id))
    if count>=100:raise InvalidOperation('Conversation limit reached. Start a new conversation.')
    db.add(m.AIMessage(conversation_id=convo.id,sequence_number=count+1,role='user',content=request.message,details={}))
    status='SUCCESS';error=None;selected=[]
    try:
        # Bounded context is freshly authorized each turn. Prior answers are never tool input.
        import json
        if len(json.dumps(data,default=str))>24000:raise providers.ProviderError('Narrow this query to one worker or run.')
        selection=providers.provider().select(request.message,[{'id':e['id'],'text':e['text']} for e in evidence],data)
        by_id={e['id']:e for e in evidence}
        if len(selection.selected_ids)!=len(set(selection.selected_ids)) or any(i not in by_id for i in selection.selected_ids):raise providers.ProviderError('Provider returned invalid evidence references.')
        selected=[by_id[i] for i in selection.selected_ids]
        answer='Here are the authorized source records.' if data else 'Relevant policy excerpts are shown below.' if selected else 'I could not find supporting evidence for that question. Try a specific worker, payroll, benefits or policy question.'
        if kind=='GENERAL_CHAT':answer='I can look up authorized worker, payroll and benefits records, explain import errors, show run statuses and retrieve indexed policy excerpts. Ask a specific question or choose a suggested prompt.'
        if tool and 'payroll' in tool:answer+='\n\n'+EXPLANATIONS['payroll']
        if tool and 'fbp' in tool:answer+='\n\n'+EXPLANATIONS['fbp']
    except providers.ProviderError:
        status='FAILED';error='AI provider failed or returned invalid evidence. Please retry later.';answer=error;data={};selected=[]
    details={'query_type':kind,'tool':tool,'structured_data':data,'citations':selected,'provider':settings_provider(),'status':status,'error':error,'request_key':str(request.request_key)}
    message=m.AIMessage(conversation_id=convo.id,sequence_number=count+2,role='assistant',content=answer,details=details);db.add(message)
    convo.updated_at=datetime.now(UTC)
    db.add(m.AIQueryAudit(user_id=user.id,conversation_id=convo.id,query_type=kind,action=tool or 'EVIDENCE_SELECTION',status=status,details={'provider':settings_provider(),'citation_count':len(selected),'request_key':str(request.request_key)}));db.flush()
    return {'status':status,'error':error,'conversation_id':str(convo.id),'message_id':str(message.id),'answer':answer,**details}

def settings_provider():
    from app.core.config import settings
    return settings.ai_provider

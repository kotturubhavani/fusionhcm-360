"""Bounded policy ingestion and permission-filtered retrieval."""
import hashlib
import re
import subprocess
import sys
import unicodedata
from datetime import datetime,UTC
from pathlib import PurePath
from sqlalchemy import select,or_
from app import models as m
from app.core.config import settings
from app.services.core_hr.common import atomic,get,InvalidOperation,Conflict
from . import providers,vectors

class AccessDenied(Exception):
    pass

def staff(user):
    return user.is_active and bool({r.name for r in user.roles}&{'HR','ADMIN'})

def authorized(user):
    if not user.is_active or not {r.name for r in user.roles}&{'HR','ADMIN','EMPLOYEE'}:raise AccessDenied('Assistant access is unavailable.')

def require_staff(user):
    authorized(user)
    if not staff(user):raise AccessDenied('Document management requires HR or ADMIN.')

SENSITIVE = re.compile(r'-----BEGIN .*PRIVATE KEY|\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{30,})\b|(?:password|api[_ -]?key|authorization|access[_ -]?token)\s*[:=]\s*\S+',re.I)
from .guardrails import DOCUMENT_INJECTION as INJECTION, normalize


def safe_input(value):
    if SENSITIVE.search(value):raise InvalidOperation('Do not submit credentials or private keys.')

def extract(filename,content):
    if not filename or len(filename)>150 or '/' in filename or '\\' in filename or ':' in filename or any(ord(c)<32 for c in filename):raise InvalidOperation('Use a plain document filename without a path.')
    suffix=PurePath(filename).suffix.lower()
    if suffix not in ('.pdf','.txt','.md'):raise InvalidOperation('Only PDF, UTF-8 TXT and Markdown are supported.')
    if not content or len(content)>settings.ai_document_max_bytes:raise InvalidOperation('Document exceeds the upload limit or is empty.')
    if suffix=='.pdf':
        if not content.startswith(b'%PDF-'):raise InvalidOperation('Invalid PDF content.')
        try:
            parsed=subprocess.run([sys.executable,'-m','app.services.ai.pdf_reader'],input=content,capture_output=True,timeout=8,check=True)
            value=parsed.stdout.decode('utf-8')
        except Exception:raise InvalidOperation('PDF must contain extractable text, be unencrypted, and have at most 30 pages / 40,000 characters. Scanned PDFs are not supported.') from None
        mime='application/pdf'
    else:
        try:value=content.decode('utf-8-sig')
        except UnicodeError:raise InvalidOperation('Text documents must use UTF-8.') from None
        mime='text/markdown' if suffix=='.md' else 'text/plain'
    if '\x00' in value or any(ord(c)<32 and c not in '\n\r\t' for c in value):raise InvalidOperation('Document contains binary/control characters.')
    value=unicodedata.normalize('NFKC',value).replace('\r\n','\n').strip()
    if not 30<=len(value)<=40000:raise InvalidOperation('Extracted text must contain 30 to 40,000 characters.')
    safe_input(value)
    if INJECTION.search(normalize(value)):raise InvalidOperation('Document contains instruction-like content and requires review before indexing.')
    return value,mime

def chunk_text(value):
    # Overlapping bounded windows preserve adjacent policy context.
    return [value[i:i+900] for i in range(0,len(value),750) if value[i:i+900].strip()]

def audit(db,user,action,status,details):
    db.add(m.AIQueryAudit(user_id=user.id if user else None,query_type='DOCUMENT_ADMIN',action=action,status=status,details=details))

@atomic
def ingest(db,user,filename,content,audience='ALL',source_name='Policy library'):
    require_staff(user)
    if audience not in ('ALL','STAFF'):raise InvalidOperation('Invalid policy audience.')
    value,mime=extract(filename,content)
    source_name=source_name+' ('+audience+')'
    source=db.scalar(select(m.DocumentSource).where(m.DocumentSource.name==source_name))
    if source is None:
        source=m.DocumentSource(name=source_name,description='Synthetic HCM policy documents',status='ACTIVE',audience=audience,created_by_user_id=user.id);db.add(source);db.flush()
    if source.status!='ACTIVE' or source.audience!=audience:raise Conflict('Policy source is unavailable.')
    checksum=hashlib.sha256(content).hexdigest()
    existing=db.scalar(select(m.Document).where(m.Document.source_id==source.id,m.Document.checksum==checksum))
    if existing:return existing
    document=m.Document(source_id=source.id,filename=filename,content_type=mime,checksum=checksum,status='FAILED',details={'audience':audience,'chunk_count':0})
    db.add(document);db.flush()
    chunks=[]
    for index,chunk in enumerate(chunk_text(value)):
        row=m.DocumentChunk(document_id=document.id,chunk_index=index,text_content=chunk,details={'character_start':index*750});db.add(row);chunks.append(row)
    db.flush()
    return index_document(db,user,document,chunks)

def index_document(db,user,document,chunks):
    provider=providers.provider()
    try:
        embedded=provider.embed([c.text_content for c in chunks])
        vectors.upsert(provider.signature,chunks,embedded)
        for chunk in chunks:
            # Immutable text may have independent mock and hosted indexes.
            spaces=set(chunk.details.get('embedding_spaces',[]))
            if chunk.embedding_reference:spaces.add(chunk.embedding_reference)
            spaces.add(provider.signature)
            chunk.details={**chunk.details,'embedding_spaces':sorted(spaces)}
            chunk.embedding_reference=provider.signature
        document.status='INDEXED';document.indexed_at=datetime.now(UTC);document.safe_error_message=None
        document.details={**document.details,'chunk_count':len(chunks),'embedding':provider.signature}
        audit(db,user,'INDEX_DOCUMENT','SUCCESS',{'document_id':str(document.id),'chunks':len(chunks)})
    except providers.ProviderError:
        document.status='FAILED';document.safe_error_message='Indexing failed. Check the provider/vector store and reindex.'
        document.details={**document.details,'chunk_count':len(chunks)}
        audit(db,user,'INDEX_DOCUMENT','FAILED',{'document_id':str(document.id)})
    db.flush();return document

@atomic
def reindex(db,user,identifier):
    require_staff(user);document=get(db,m.Document,identifier,lock=True)
    if document.status=='INACTIVE':raise Conflict('Activate the document before reindexing.')
    chunks=db.scalars(select(m.DocumentChunk).where(m.DocumentChunk.document_id==identifier).order_by(m.DocumentChunk.chunk_index)).all()
    return index_document(db,user,document,chunks)

@atomic
def set_active(db,user,identifier,active):
    require_staff(user);document=get(db,m.Document,identifier,lock=True)
    document.status='FAILED' if active else 'INACTIVE'
    document.safe_error_message='Reindex to activate retrieval.' if active else None
    audit(db,user,'ACTIVATE_DOCUMENT' if active else 'DEACTIVATE_DOCUMENT','SUCCESS',{'document_id':str(identifier)})
    db.flush();return document

def retrieve(db,user,query,source_id=None,document_id=None):
    authorized(user);provider=providers.provider()
    statement=select(m.DocumentChunk,m.Document,m.DocumentSource).join(m.Document,m.DocumentChunk.document_id==m.Document.id).join(m.DocumentSource,m.Document.source_id==m.DocumentSource.id).where(m.Document.status=='INDEXED',m.DocumentSource.status=='ACTIVE',or_(m.DocumentChunk.embedding_reference==provider.signature,m.DocumentChunk.details['embedding_spaces'].contains([provider.signature])))
    if not staff(user):statement=statement.where(m.DocumentSource.audience=='ALL')
    if source_id:statement=statement.where(m.Document.source_id==source_id)
    if document_id:statement=statement.where(m.Document.id==document_id)
    rows=db.execute(statement.order_by(m.Document.id,m.DocumentChunk.chunk_index).limit(2001)).all()
    if len(rows)>2000:raise InvalidOperation('Policy scope is too large; select a document or source filter.')
    if not rows:return []
    lookup={str(c.id):(c,d,src) for c,d,src in rows}
    matches=vectors.search(provider.signature,provider.embed([query],query=True)[0],list(lookup),settings.ai_top_k,settings.ai_min_score)
    result=[]
    for hit in matches:
        if str(hit['id']) not in lookup:continue
        c,d,src=lookup[str(hit['id'])]
        # Reapply trust checks even if an index was created by another process.
        if INJECTION.search(normalize(c.text_content)) or SENSITIVE.search(c.text_content):continue
        if settings.ai_provider=='mock' and not set(providers.terms(query))&set(providers.terms(c.text_content)):continue
        result.append({'id':str(c.id),'document_id':str(d.id),'document_name':d.filename,'source_name':src.name,'chunk_index':c.chunk_index,'text':c.text_content,'score':round(hit['score'],4)})
    return result

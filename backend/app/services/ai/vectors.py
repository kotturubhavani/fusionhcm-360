"""Qdrant holds only vectors and opaque IDs; PostgreSQL authorizes retrieval."""
import httpx
from app.core.config import settings
from .providers import ProviderError

def collection(signature):
    return settings.ai_qdrant_collection+'_'+signature.replace('-','_')

def request(method,path,body=None,allow_missing=False):
    try:
        with httpx.Client(base_url=settings.ai_qdrant_url,timeout=5,trust_env=False,follow_redirects=False) as client:
            response=client.request(method,path,json=body)
            if allow_missing and response.status_code==404:return None
            response.raise_for_status()
            return response.json()
    except Exception:raise ProviderError('Document vector store is unavailable. Please retry later.') from None

def upsert(signature,chunks,vectors):
    name=collection(signature)
    if request('GET','/collections/'+name,allow_missing=True) is None:
        request('PUT','/collections/'+name,{'vectors':{'size':256,'distance':'Cosine'}})
    request('PUT','/collections/'+name+'/points?wait=true',{'points':[{'id':str(chunk.id),'vector':vector} for chunk,vector in zip(chunks,vectors,strict=True)]})

def search(signature,vector,allowed_ids,limit,threshold):
    if not allowed_ids:return []
    name=collection(signature)
    if request('GET','/collections/'+name,allow_missing=True) is None:raise ProviderError('Policy vectors are missing. Ask HR to reindex documents.')
    data=request('POST','/collections/'+name+'/points/query',{'query':vector,'filter':{'must':[{'has_id':[str(i) for i in allowed_ids]}]},'limit':limit,'score_threshold':threshold,'with_payload':False,'with_vector':False})
    return sorted(data['result']['points'],key=lambda p:(-p['score'],str(p['id'])))

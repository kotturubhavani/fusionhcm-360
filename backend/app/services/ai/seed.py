"""Explicit, idempotent synthetic-policy ingestion; no account creation."""
from pathlib import Path
from app.services.core_hr.common import InvalidOperation
from .documents import ingest,require_staff,reindex

def seed(db,user):
    require_staff(user)
    root=Path(__file__).resolve().parents[4]/'synthetic-data'/'policies'
    result=[]
    for path in sorted(root.glob('*.md')):
        row=ingest(db,user,path.name,path.read_bytes(),'ALL','Asterion Policies')
        if row.status=='FAILED':row=reindex(db,user,row.id)
        result.append(row)
    if len(result)!=5:raise InvalidOperation('Expected five synthetic policy documents.')
    return result

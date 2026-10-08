"""Reusable synthetic FILE definitions only; no startup or external delivery."""
from sqlalchemy import select
from app import models as m
from app.schemas.integrations import DefinitionCreate
from app.services.core_hr.common import atomic,Conflict
from .service import create
@atomic
def seed(db):
    count=0
    for code,name,kind in [('DEMO360_I_WORKERS','Worker Master Outbound','WORKER_EXPORT'),('DEMO360_I_PAYROLL','Payroll Results Outbound','PAYROLL_EXPORT'),('DEMO360_I_FBP','Benefits Elections Outbound','FBP_EXPORT')]:
        existing=db.scalar(select(m.IntegrationDefinition).where(m.IntegrationDefinition.code==code))
        if existing:
            if existing.direction!='OUTBOUND' or existing.integration_type!=kind or existing.transport_type!='FILE':raise Conflict('Reserved demo integration has conflicting settings.')
        else:
            create(db,DefinitionCreate(code=code,name=name,direction='OUTBOUND',integration_type=kind,transport_type='FILE',output_format='JSON'));count+=1
    return count

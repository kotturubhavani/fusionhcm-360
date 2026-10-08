"""Explicit reusable synthetic definitions; never runs reports/extracts."""
from sqlalchemy import select
from app import models as m
from app.schemas import analytics as s
from app.services.core_hr.common import atomic,Conflict
from . import reports,extracts

@atomic
def seed(db):
    definitions=[('DEMO360_R_WORKFORCE','Active Workforce by Department','CORE_HR_WORKERS',['person_number','employee_name','department','assignment_status']),('DEMO360_R_PAYROLL','Monthly Payroll Results','PAYROLL_RESULTS',['period','person_number','gross_pay','total_deductions','net_pay','currency']),('DEMO360_R_FBP','Benefits Allocation Status','FBP_ALLOCATIONS',['plan','person_number','eligible_budget','elected_amount','remaining_amount','status'])]
    count=0
    for code,name,domain,columns in definitions:
        existing=db.scalar(select(m.ReportDefinition).where(m.ReportDefinition.code==code))
        if existing:
            if existing.domain!=domain:raise Conflict('Reserved demo report has a conflicting domain.')
        else:
            reports.create_report(db,s.ReportCreate(code=code,name=name,domain=domain,selected_columns=columns,filters=[s.Filter(field='assignment_status',operator='equals',value='ACTIVE')] if domain=='CORE_HR_WORKERS' else [],sort_definition=[s.Sort(field=columns[0])]))
            count+=1
    for code,name,kind in [('DEMO360_E_WORKFORCE','Worker Master Export','WORKER_SNAPSHOT'),('DEMO360_E_CHANGES','Worker Changes Export','WORKER_CHANGES'),('DEMO360_E_PAYROLL','Payroll Results Export','PAYROLL_RESULTS')]:
        existing=db.scalar(select(m.ExtractDefinition).where(m.ExtractDefinition.code==code))
        if existing:
            if existing.extract_type!=kind:raise Conflict('Reserved demo extract has a conflicting type.')
        else:extracts.create(db,s.ExtractCreate(code=code,name=name,extract_type=kind));count+=1
    return count

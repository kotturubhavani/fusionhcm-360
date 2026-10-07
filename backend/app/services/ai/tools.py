"""Allowlisted read-only HCM queries. Authorization is independent of routing/LLM."""
import re
from datetime import date
from sqlalchemy import select
from app import models as m
from app.services.core_hr.queries import worker_summary
from app.services.core_hr.common import NotFound,InvalidOperation
from app.services.payroll.service import result_detail
from app.services.fbp.service import budget_view
from app.services.imports.templates import TEMPLATES,required
from .documents import authorized,staff,AccessDenied

SELF={'get_my_worker_summary','get_my_payroll','get_my_fbp'}
STAFF={'search_workers','get_worker_summary','get_payroll_result','get_payroll_history','get_fbp_status','get_import_job_status','get_report_run_status','get_extract_run_status','get_integration_run_status'}

def resolve_person(db,user,request):
    if not staff(user):
        if request.person_number or request.reference_id:raise AccessDenied('Employees can query only their linked worker using self-service tools.')
        if not user.person_id:raise NotFound('No worker is linked to this account.')
        return user.person_id
    if request.person_number:
        person=db.scalar(select(m.Person).where(m.Person.person_number==request.person_number))
        if not person:raise NotFound('Worker not found.')
        return person.id
    if re.search(r'\b(my|own|me)\b',request.message,re.I) and user.person_id:return user.person_id
    # Deterministic name/code resolution, staff only; ambiguous names require an identifier.
    words=request.message.casefold()
    matches=[p for p in db.scalars(select(m.Person).order_by(m.Person.person_number).limit(501)) if p.person_number.casefold() in words or (p.first_name+' '+p.last_name).casefold() in words]
    if len(matches)!=1:raise InvalidOperation('Specify one person number or full worker name.')
    return matches[0].id

def summary(db,person_id,day):
    worker=worker_summary(db,person_id,day)
    return {'person_number':worker.person.person_number,'name':worker.person.first_name+' '+worker.person.last_name,'is_active':worker.person.is_active,'as_of':day.isoformat(),
        'assignments':[{'assignment_number':p.assignment.assignment_number,'employment_type':p.work_relationship.employment_type,'joining_date':str(p.work_relationship.start_date),
        'status':p.version.status if p.version else None,'department':p.department.name if p.department else None,'job':p.job.name if p.job else None,
        'annual_base_salary':str(p.compensation.annual_base_salary) if p.compensation else None,'currency':p.compensation.currency if p.compensation else None} for p in worker.placements]}

def payroll(db,person_id,reference=None):
    query=select(m.PayrollResult).join(m.PayrollRun,m.PayrollResult.payroll_run_id==m.PayrollRun.id).join(m.PayPeriod,m.PayrollRun.pay_period_id==m.PayPeriod.id).where(m.PayrollRun.status=='COMPLETED')
    if person_id:query=query.where(m.PayrollResult.person_id==person_id)
    if reference:query=query.where(m.PayrollResult.id==reference)
    rows=db.scalars(query.order_by(m.PayPeriod.payment_date.desc(),m.PayrollRun.run_number.desc(),m.PayrollResult.assignment_number).limit(10)).all()
    results=[]
    for row in rows:
        detail=result_detail(db,row)
        results.append({'person_number':row.person_number,'assignment_number':row.assignment_number,'period':detail.period.period_name,'payment_date':str(detail.period.payment_date),'gross':str(row.gross_pay),'deductions':str(row.total_deductions),'net':str(row.net_pay),'currency':row.currency,
            'lines':[{'code':l.code,'name':l.name,'type':l.line_type,'amount':str(l.amount)} for l in detail.lines]})
    return {'results':results,'limit':10,'order':'latest payment date first'}

def fbp(db,person_id,question):
    query=select(m.FBPWorkerBudget)
    if person_id:query=query.where(m.FBPWorkerBudget.person_id==person_id)
    if re.search(r'not submitted|unsubmitted|pending',question,re.I):query=query.where(m.FBPWorkerBudget.status=='OPEN')
    rows=db.scalars(query.order_by(m.FBPWorkerBudget.created_at.desc(),m.FBPWorkerBudget.id).limit(10)).all()
    result=[]
    for row in rows:
        view=budget_view(db,row);plan=db.get(m.FBPPlan,row.plan_id)
        result.append({'person_number':row.person_number,'assignment_number':row.assignment_number,'plan':plan.code,'status':row.status,'budget':str(row.eligible_budget),'allocated':str(view.allocated),'remaining':str(view.remaining),'currency':row.currency,
            'elections':[{'component':db.get(m.FBPComponent,e.component_id).name,'amount':str(e.amount)} for e in view.elections]})
    return {'budgets':result,'limit':10}

def execute(db,user,tool,request):
    authorized(user)
    if tool not in SELF|STAFF:raise AccessDenied('Unsupported assistant tool.')
    is_staff=staff(user)
    if not is_staff and (tool not in SELF or request.person_number or request.reference_id):raise AccessDenied('Employees can query only their linked worker using self-service tools.')
    if tool in SELF:
        if not user.person_id:raise NotFound('No worker is linked to this account.')
        person_id=user.person_id
    else:person_id=None
    if tool=='search_workers':
        query=select(m.Person).where(m.Person.is_active.is_(True)).order_by(m.Person.person_number)
        workers=[];day=request.as_of or date.today()
        match=re.search(r'\bin\s+([\w -]+)',request.message,re.I)
        department=match.group(1).strip().casefold() if match else None
        for person in db.scalars(query.limit(501)):
            view=summary(db,person.id,day)
            if not view['assignments']:continue
            if 'active' in request.message.lower() and not any(p['status']=='ACTIVE' for p in view['assignments']):continue
            if department and not any(department in (p['department'] or '').casefold() for p in view['assignments']):continue
            # Workforce search does not include compensation.
            workers.append({'person_number':view['person_number'],'name':view['name'],'departments':sorted({p['department'] for p in view['assignments'] if p['department']})})
            if len(workers)==20:break
        return {'workers':workers,'limit':20,'as_of':str(day)}
    if tool in ('get_worker_summary','get_my_worker_summary'):
        return summary(db,person_id or resolve_person(db,user,request),request.as_of or date.today())
    if tool in ('get_payroll_result','get_payroll_history','get_my_payroll'):
        if tool=='get_payroll_result' and request.reference_id:return payroll(db,None,request.reference_id)
        return payroll(db,person_id or resolve_person(db,user,request))
    if tool in ('get_fbp_status','get_my_fbp'):
        if is_staff and not person_id and not request.person_number and re.search(r'workers|pending|not submitted|unsubmitted',request.message,re.I):return fbp(db,None,request.message)
        return fbp(db,person_id or resolve_person(db,user,request),request.message)
    if tool=='get_import_job_status':
        if not request.reference_id:raise InvalidOperation('Select an import job ID and optional row number.')
        job=db.get(m.ImportJob,request.reference_id)
        if not job:raise NotFound('Import job not found.')
        query=select(m.ImportRow).where(m.ImportRow.import_job_id==job.id)
        number=request.row_number
        if not number:
            match=re.search(r'\brow\s+(\d+)\b',request.message,re.I);number=int(match.group(1)) if match else None
        if number:query=query.where(m.ImportRow.row_number==number)
        else:query=query.where(m.ImportRow.status.in_(['INVALID','FAILED']))
        rows=db.scalars(query.order_by(m.ImportRow.row_number).limit(10)).all()
        return {'object_type':job.object_type,'status':job.status,'total_rows':job.total_rows,'rows':[{'row_number':r.row_number,'status':r.status,'error_code':r.error_code,'safe_error':r.error_message} for r in rows],
            'allowed_columns':TEMPLATES[job.object_type],'required_columns':required(job.object_type),'rules':'Use exact template columns, existing readable identifiers, ISO dates and nonnegative decimal salaries. Correct the failed row in a new import; do not repeat successful rows.'}
    model={'get_report_run_status':m.ReportRun,'get_extract_run_status':m.ExtractRun,'get_integration_run_status':m.IntegrationRun}[tool]
    if not request.reference_id:raise InvalidOperation('Provide the run ID from its history page.')
    row=db.get(model,request.reference_id)
    if not row:raise NotFound('Run not found.')
    allowed=('status','started_at','completed_at','row_count','records_read','records_succeeded','records_failed','error_message','safe_error_message')
    return {k:str(getattr(row,k)) if k.endswith('_at') and getattr(row,k) else getattr(row,k) for k in allowed if hasattr(row,k)}

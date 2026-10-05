"""Readable domain rows. Core HR uses the existing dated worker query rules."""
from decimal import Decimal
from sqlalchemy import select,func
from app import models as m
from app.core.config import settings
from app.services.core_hr.queries import worker_summary
from app.services.core_hr.common import InvalidOperation
from app.services.fbp.service import budget_view


def bounded(db,model):
    if db.scalar(select(func.count()).select_from(model))>settings.analytics_max_rows:
        raise InvalidOperation('Source exceeds the configured simulator row limit.')
    return db.scalars(select(model).order_by(model.id)).all()


def stamp(*rows):return max(r.updated_at for r in rows if r is not None)
def name(row):return row.name if row else None


def worker_rows(db,as_of,changes=False):
    result=[]
    for person in bounded(db,m.Person):
        summary=worker_summary(db,person.id,as_of)
        # Changes includes ended assignments, exposing latest dated values and end date.
        placements={p.assignment.id:p for p in summary.placements}
        if changes:
            assignments=db.scalars(select(m.Assignment).join(m.WorkRelationship).where(m.WorkRelationship.person_id==person.id)).all()
            for assignment in assignments:
                if assignment.id not in placements:
                    day=assignment.end_date or assignment.start_date
                    historical=worker_summary(db,person.id,day)
                    placements.update({p.assignment.id:p for p in historical.placements if p.assignment.id==assignment.id})
        for p in placements.values():
            a=db.get(m.Assignment,p.assignment.id);wr=db.get(m.WorkRelationship,p.work_relationship.id)
            versions=db.scalars(select(m.AssignmentVersion).where(m.AssignmentVersion.assignment_id==a.id)).all()
            salaries=db.scalars(select(m.AssignmentCompensation).where(m.AssignmentCompensation.assignment_id==a.id)).all()
            v=p.version;c=p.compensation
            references=[db.get(m.LegalEmployer,wr.legal_employer_id)]
            for model,key in [(m.BusinessUnit,'business_unit_id'),(m.Department,'department_id'),(m.Job,'job_id'),(m.Grade,'grade_id'),(m.Location,'location_id')]:
                if v and getattr(v,key):references.append(db.get(model,getattr(v,key)))
            result.append(dict(_key=str(a.id),_changed=stamp(person,a,wr,*versions,*salaries,*references),person_number=person.person_number,
                employee_name=f'{person.first_name} {person.last_name}',assignment_number=a.assignment_number,legal_employer=references[0].name,
                business_unit=name(p.business_unit),department=name(p.department),job=name(p.job),grade=name(p.grade),location=name(p.location),
                employment_type=wr.employment_type,assignment_status=v.status if v else None,work_time_type=v.work_time_type if v else None,
                manager=p.manager.person_number if p.manager else None,annual_base_salary=c.annual_base_salary if c else None,currency=c.currency if c else None,
                start_date=a.start_date,end_date=a.end_date))
            if len(result)>settings.analytics_max_rows:raise InvalidOperation('Result exceeds the configured simulator row limit.')
    return result


def domain_rows(db,domain,as_of):
    if domain=='CORE_HR_WORKERS':return worker_rows(db,as_of)
    result=[]
    if domain=='PAYROLL_RESULTS':
        for r in bounded(db,m.PayrollResult):
            run=db.get(m.PayrollRun,r.payroll_run_id)
            if run.status!='COMPLETED':continue
            period=db.get(m.PayPeriod,run.pay_period_id)
            result.append(dict(_key=str(r.id),_changed=stamp(r,run),period=period.period_name,person_number=r.person_number,employee_name=r.worker_name,assignment_number=r.assignment_number,gross_pay=r.gross_pay,total_deductions=r.total_deductions,net_pay=r.net_pay,currency=r.currency))
    elif domain=='FBP_ALLOCATIONS':
        for b in bounded(db,m.FBPWorkerBudget):
            view=budget_view(db,b);plan=db.get(m.FBPPlan,b.plan_id)
            elections=db.scalars(select(m.FBPElection).where(m.FBPElection.worker_budget_id==b.id)).all()
            result.append(dict(_key=str(b.id),_changed=stamp(b,plan,*elections),plan=plan.code,person_number=b.person_number,employee_name=b.worker_name,assignment_number=b.assignment_number,eligible_budget=b.eligible_budget,elected_amount=view.allocated,remaining_amount=view.remaining,currency=b.currency,status=b.status))
    else:
        for j in bounded(db,m.ImportJob):
            result.append(dict(_key=str(j.id),_changed=j.updated_at,filename=j.original_filename,object_type=j.object_type,status=j.status,total_rows=j.total_rows,valid_rows=j.valid_rows,invalid_rows=j.invalid_rows,processed_rows=j.processed_rows,failed_rows=j.failed_rows,created_at=j.created_at))
    return result


def election_rows(db,as_of):
    results=[]
    for e in bounded(db,m.FBPElection):
        b=db.get(m.FBPWorkerBudget,e.worker_budget_id)
        if b.status not in ('SUBMITTED','FINALIZED'):continue
        p=db.get(m.FBPPlan,b.plan_id);c=db.get(m.FBPComponent,e.component_id)
        results.append(dict(_key=str(e.id),_changed=stamp(e,b,p,c),plan=p.code,person_number=b.person_number,employee_name=b.worker_name,assignment_number=b.assignment_number,eligible_budget=b.eligible_budget,elected_amount=e.amount,remaining_amount=Decimal('0.00'),currency=b.currency,status=b.status,component=c.code,component_name=c.name))
    return results

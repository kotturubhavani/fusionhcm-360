"""Readable exports from existing dated queries and immutable result snapshots."""
from datetime import date
from app import models as m
from app.services.analytics import data,reports
from app.services.fbp.service import budget_view


def outbound(db,definition):
    c=definition.configuration;kind=definition.integration_type;result=[]
    if kind=='WORKER_EXPORT':
        for row in data.worker_rows(db,c.as_of or date.today()):
            assignment=db.get(m.Assignment,row['_key']);relationship=db.get(m.WorkRelationship,assignment.work_relationship_id)
            person=db.get(m.Person,relationship.person_id)
            from app.services.core_hr.employment import current_version
            version=current_version(db,assignment.id,c.as_of or date.today())
            if c.active_workers_only and (not person.is_active or row['assignment_status']!='ACTIVE'):continue
            codes={'legal_employer_code':db.get(m.LegalEmployer,relationship.legal_employer_id).code,
                'business_unit_code':db.get(m.BusinessUnit,version.business_unit_id).code if version else None,
                'department_code':db.get(m.Department,version.department_id).code if version else None}
            if any(getattr(c,key) and getattr(c,key)!=value for key,value in codes.items()):continue
            result.append({**{k:v for k,v in row.items() if not k.startswith('_') and k not in ('annual_base_salary','currency')},**codes})
    elif kind=='PAYROLL_EXPORT':
        for item in data.bounded(db,m.PayrollResult):
            run=db.get(m.PayrollRun,item.payroll_run_id)
            if run.status!='COMPLETED':continue
            period=db.get(m.PayPeriod,run.pay_period_id);payroll=db.get(m.PayrollDefinition,period.payroll_definition_id)
            if c.payroll_definition_code and c.payroll_definition_code!=payroll.code:continue
            if c.period_name and c.period_name!=period.period_name:continue
            if c.completed_run_number and c.completed_run_number!=run.run_number:continue
            result.append(dict(payroll=payroll.code,period=period.period_name,run_number=run.run_number,payment_date=period.payment_date,person_number=item.person_number,assignment_number=item.assignment_number,gross_pay=item.gross_pay,total_deductions=item.total_deductions,net_pay=item.net_pay,currency=item.currency))
    else:
        for budget in data.bounded(db,m.FBPWorkerBudget):
            if budget.status not in ('SUBMITTED','FINALIZED'):continue
            plan=db.get(m.FBPPlan,budget.plan_id)
            if c.fbp_plan_code and plan.code!=c.fbp_plan_code:continue
            view=budget_view(db,budget)
            elections=[]
            for item in view.elections:
                component=db.get(m.FBPComponent,item.component_id)
                elections.append(dict(component=component.code,amount=item.amount))
            result.append(dict(plan=plan.code,person_number=budget.person_number,assignment_number=budget.assignment_number,eligible_budget=budget.eligible_budget,elected_amount=view.allocated,remaining_amount=view.remaining,status=budget.status,currency=budget.currency,components=sorted(elections,key=lambda e:e['component'])))
    return reports.json_safe(result)

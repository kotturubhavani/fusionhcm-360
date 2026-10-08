"""Explicit synthetic benefit plans; no accounts and no startup enrollment."""
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from app import models as m
from app.schemas import fbp as s
from app.services.core_hr.common import atomic, InvalidOperation
from app.services.fbp import service as f

PREFIX='DEMO360_'
COMPONENTS=[('FLEX','Meal Benefit','BENEFIT'),('LEARNING','Learning Allowance','ALLOWANCE'),('WELLNESS','Wellness Allowance','BENEFIT'),('COMMUTE','Transport Allowance','REIMBURSEMENT')]


@atomic
def seed_demo(db):
    employer=db.scalar(select(m.LegalEmployer).where(m.LegalEmployer.code==PREFIX+'LE0'))
    if not employer:raise InvalidOperation('Run the synthetic Core HR seed first.')
    outsiders=db.scalar(select(m.Person.id).join(m.WorkRelationship).where(m.WorkRelationship.legal_employer_id==employer.id,~m.Person.person_number.startswith(PREFIX)).limit(1))
    if outsiders:raise InvalidOperation('Demo employer contains non-demo workers; benefits seed stopped.')
    existing=db.scalars(select(m.FBPPlan).where(m.FBPPlan.code.in_([PREFIX+'FBP2025',PREFIX+'FBP2026']))).all()
    if existing:
        if len(existing)!=2:raise InvalidOperation('Demo benefit plans are incomplete; existing history was not changed.')
        for plan in existing:
            comps=f.components(db,plan.id)
            budgets=db.scalars(select(m.FBPWorkerBudget).where(m.FBPWorkerBudget.plan_id==plan.id)).all()
            if plan.legal_employer_id!=employer.id or plan.currency!='INR' or not plan.budgets_generated_at or len(comps)!=4 or not budgets or (plan.plan_year==2025 and (plan.status!='CLOSED' or any(b.status!='FINALIZED' for b in budgets))):
                raise InvalidOperation('Demo benefits data is incomplete or conflicting; existing history was not changed.')
            if {c.code for c in comps}!={code for code,_,_ in COMPONENTS}:raise InvalidOperation('Demo component set is incomplete.')
            for budget in budgets:
                view=f.budget_view(db,budget)
                if budget.status in ('SUBMITTED','FINALIZED') and view.remaining!=0:raise InvalidOperation('Demo allocation history is incomplete.')
        return {'created':False,'plans':2}
    for year in (2025,2026):
        plan=f.create_plan(db,s.PlanCreate(code=PREFIX+f'FBP{year}',name=f'Annual Benefits {year}',legal_employer_id=employer.id,
            plan_year=year,effective_from=date(year,1,1),effective_to=date(year,12,31),currency='INR'))
        comps=[f.create_component(db,plan.id,s.ComponentCreate(code=code,name=name,description='Synthetic flexible benefit; no statutory or tax treatment.',component_type=kind,max_amount='999999999999.99',display_order=index)) for index,(code,name,kind) in enumerate(COMPONENTS)]
        f.open_plan(db,plan.id);f.generate_budgets(db,plan.id)
        for index,budget in enumerate(f.workers(db,plan.id,0,100)):
            amount=budget.eligible_budget if year==2025 or index==0 else (budget.eligible_budget/2).quantize(Decimal('0.01'))
            saved=f.save_elections(db,plan.id,budget.person_id,s.ElectionsSave(worker_budget_id=budget.id,expected_revision=budget.revision,elections=[s.ElectionInput(component_id=comps[0].id,amount=amount)]))
            if year==2025 or index==0:f.submit(db,plan.id,budget.person_id,s.BudgetAction(worker_budget_id=budget.id,expected_revision=saved.revision))
        if year==2025:f.close_plan(db,plan.id)
    return {'created':True,'plans':2}

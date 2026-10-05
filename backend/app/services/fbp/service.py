"""FBP transitions use the shared HR lock plus row locks and revision checks."""
from datetime import UTC, datetime
from decimal import Decimal
from sqlalchemy import select
from app import models as m
from app.schemas import fbp as s
from app.services.core_hr.common import atomic, active, get, Conflict, InvalidOperation, NotFound
from app.services.core_hr.employment import covers, current_version, current_compensation
from app.services.fbp import rules


def plans(db, offset=0, limit=50):
    return db.scalars(select(m.FBPPlan).order_by(m.FBPPlan.plan_year.desc(),m.FBPPlan.code).offset(offset).limit(limit)).all()


def components(db, plan_id):
    get(db,m.FBPPlan,plan_id)
    return db.scalars(select(m.FBPComponent).where(m.FBPComponent.plan_id==plan_id).order_by(m.FBPComponent.display_order,m.FBPComponent.code)).all()


def require_draft(plan):
    if plan.status != 'DRAFT':
        raise Conflict('Plan and component settings are frozen after opening.')


def require_open(plan):
    if plan.status != 'OPEN' or not plan.is_active:
        raise Conflict('The plan is not open for elections.')


@atomic
def create_plan(db,payload):
    active(db,m.LegalEmployer,payload.legal_employer_id)
    row=m.FBPPlan(**payload.model_dump());db.add(row);db.flush()
    return row


@atomic
def update_plan(db,plan_id,payload):
    plan=get(db,m.FBPPlan,plan_id,lock=True);require_draft(plan)
    merged={key:getattr(plan,key) for key in s.PlanCreate.model_fields}
    merged.update(payload.model_dump(exclude_unset=True))
    valid=s.PlanCreate(**merged)
    active(db,m.LegalEmployer,valid.legal_employer_id)
    for key,value in valid.model_dump().items():setattr(plan,key,value)
    db.flush();return plan


@atomic
def create_component(db,plan_id,payload):
    plan=get(db,m.FBPPlan,plan_id,lock=True);require_draft(plan)
    if len(components(db,plan_id))>=100:raise InvalidOperation('A plan supports at most 100 components.')
    row=m.FBPComponent(plan_id=plan_id,**payload.model_dump());db.add(row);db.flush();return row


@atomic
def update_component(db,component_id,payload):
    row=get(db,m.FBPComponent,component_id,lock=True)
    plan=get(db,m.FBPPlan,row.plan_id,lock=True);require_draft(plan)
    merged={key:getattr(row,key) for key in s.ComponentCreate.model_fields};merged.update(payload.model_dump(exclude_unset=True))
    valid=s.ComponentCreate(**merged)
    for key,value in valid.model_dump().items():setattr(row,key,value)
    db.flush();return row


@atomic
def open_plan(db,plan_id):
    plan=get(db,m.FBPPlan,plan_id,lock=True);require_draft(plan)
    if not plan.is_active:raise InvalidOperation('Activate the draft plan before opening.')
    active(db,m.LegalEmployer,plan.legal_employer_id)
    if not any(c.is_active and c.max_amount>0 for c in components(db,plan_id)):
        raise InvalidOperation('Add an active component with a positive maximum before opening.')
    plan.status='OPEN';db.flush();return plan


def budget_view(db,row):
    elections=db.scalars(select(m.FBPElection).where(m.FBPElection.worker_budget_id==row.id).order_by(m.FBPElection.component_id)).all()
    allocated=sum((e.amount for e in elections),Decimal('0.00'))
    values={key:getattr(row,key) for key in s.BudgetRead.model_fields if key not in ('allocated','remaining','elections')}
    return s.BudgetRead(**values,allocated=allocated,remaining=row.eligible_budget-allocated,elections=[s.ElectionRead.model_validate(e) for e in elections])


def workers(db,plan_id,offset=0,limit=50):
    get(db,m.FBPPlan,plan_id)
    rows=db.scalars(select(m.FBPWorkerBudget).where(m.FBPWorkerBudget.plan_id==plan_id).order_by(m.FBPWorkerBudget.person_number,m.FBPWorkerBudget.assignment_number).offset(offset).limit(limit)).all()
    return [budget_view(db,row) for row in rows]


@atomic
def generate_budgets(db,plan_id):
    plan=get(db,m.FBPPlan,plan_id,lock=True);require_open(plan)
    if plan.budgets_generated_at:return summary(db,plan_id)
    active(db,m.LegalEmployer,plan.legal_employer_id)
    day=plan.effective_from
    candidates=db.execute(select(m.Assignment,m.WorkRelationship,m.Person).join(m.WorkRelationship,m.Assignment.work_relationship_id==m.WorkRelationship.id).join(m.Person,m.WorkRelationship.person_id==m.Person.id).where(m.WorkRelationship.legal_employer_id==plan.legal_employer_id,m.Person.is_active.is_(True)).order_by(m.Person.person_number,m.Assignment.assignment_number)).all()
    enabled=[c for c in components(db,plan_id) if c.is_active]
    count=0
    for assignment,relationship,person in candidates:
        if not covers(relationship.start_date,relationship.end_date,day) or not covers(assignment.start_date,assignment.end_date,day):continue
        version=current_version(db,assignment.id,day);compensation=current_compensation(db,assignment.id,day)
        if not version or version.status!='ACTIVE' or not compensation:continue
        if compensation.currency!=plan.currency:raise InvalidOperation('Eligible compensation currency differs from plan currency; no budgets were generated.')
        amount=rules.budget(compensation.annual_base_salary,plan.budget_rate)
        if amount<=0:continue
        # A zero-minimum component able to absorb the entire budget guarantees exact allocation is possible.
        if not any(c.min_amount==0 and c.max_amount>=amount for c in enabled):
            raise InvalidOperation('Provide an active zero-minimum component whose maximum can cover each full worker budget.')
        db.add(m.FBPWorkerBudget(plan_id=plan.id,person_id=person.id,assignment_id=assignment.id,compensation_id=compensation.id,
            person_number=person.person_number,worker_name=f'{person.first_name} {person.last_name}',assignment_number=assignment.assignment_number,
            annual_base_salary=compensation.annual_base_salary,budget_rate=plan.budget_rate,eligible_budget=amount,currency=plan.currency))
        count+=1
    if not count:raise InvalidOperation('No active eligible assignments with positive compensation at the plan start date.')
    plan.budgets_generated_at=datetime.now(UTC);db.flush();return summary(db,plan_id)


def own_budget(db,plan_id,person_id,budget_id,lock=False):
    query = select(m.FBPWorkerBudget).where(
        m.FBPWorkerBudget.id == budget_id,
        m.FBPWorkerBudget.plan_id == plan_id,
        m.FBPWorkerBudget.person_id == person_id,
    )
    if lock:
        query = query.with_for_update()
    row = db.scalar(query)
    if row is None:raise NotFound('Benefit budget not found.')
    db.refresh(row)
    return row


def check_edit(plan,budget,revision):
    require_open(plan)
    if budget.status!='OPEN':raise Conflict('Submitted or finalized allocations are read-only.')
    if budget.revision!=revision:raise Conflict('This allocation changed in another session. Reload before saving.')


def validate_elections(db,plan,budget,entries,exact=False):
    enabled={c.id:c for c in components(db,plan.id) if c.is_active}
    total=Decimal('0.00')
    for entry in entries:
        component=enabled.get(entry.component_id)
        if component is None:raise InvalidOperation('Every election must reference an active component of this plan.')
        if entry.amount>component.max_amount or (entry.amount>0 and entry.amount<component.min_amount):
            raise InvalidOperation(f'{component.name}: amount must be zero or within component limits.')
        total+=entry.amount
    if budget.currency!=plan.currency:raise InvalidOperation('Budget currency does not match plan currency.')
    if total>budget.eligible_budget:raise InvalidOperation('Total elections exceed the available benefit budget.')
    if exact and total!=budget.eligible_budget:raise InvalidOperation('Allocate the exact budget before submitting; unused balance must be zero.')


@atomic
def save_elections(db,plan_id,person_id,payload):
    plan=get(db,m.FBPPlan,plan_id,lock=True)
    budget=own_budget(db,plan_id,person_id,payload.worker_budget_id,lock=True);check_edit(plan,budget,payload.expected_revision)
    validate_elections(db,plan,budget,payload.elections)
    existing={e.component_id:e for e in db.scalars(select(m.FBPElection).where(m.FBPElection.worker_budget_id==budget.id)).all()}
    incoming={e.component_id:e.amount for e in payload.elections}
    # Full replacement semantics retain zero-valued rows; no history is hard deleted.
    for component_id,row in existing.items():row.amount=incoming.get(component_id,Decimal('0.00'))
    for component_id,amount in incoming.items():
        if component_id not in existing:db.add(m.FBPElection(plan_id=plan.id,worker_budget_id=budget.id,component_id=component_id,amount=amount))
    budget.revision+=1;db.flush();return budget_view(db,budget)


@atomic
def submit(db,plan_id,person_id,payload):
    plan=get(db,m.FBPPlan,plan_id,lock=True)
    budget=own_budget(db,plan_id,person_id,payload.worker_budget_id,lock=True);check_edit(plan,budget,payload.expected_revision)
    rows=db.scalars(select(m.FBPElection).where(m.FBPElection.worker_budget_id==budget.id)).all()
    validate_elections(db,plan,budget,rows,exact=True)
    budget.status='SUBMITTED';budget.submitted_at=datetime.now(UTC);budget.revision+=1;db.flush();return budget_view(db,budget)


@atomic
def close_plan(db,plan_id):
    plan=get(db,m.FBPPlan,plan_id,lock=True);require_open(plan)
    budgets=db.scalars(select(m.FBPWorkerBudget).where(m.FBPWorkerBudget.plan_id==plan.id).with_for_update()).all()
    if not budgets or any(b.status!='SUBMITTED' for b in budgets):raise Conflict('All worker budgets must be submitted before closing the plan.')
    for budget in budgets:
        rows=db.scalars(select(m.FBPElection).where(m.FBPElection.worker_budget_id==budget.id)).all()
        validate_elections(db,plan,budget,rows,exact=True)
        budget.status='FINALIZED';budget.finalized_at=datetime.now(UTC);budget.revision+=1
    plan.status='CLOSED';db.flush();return plan


def summary(db,plan_id):
    plan=get(db,m.FBPPlan,plan_id)
    budgets=db.scalars(select(m.FBPWorkerBudget).where(m.FBPWorkerBudget.plan_id==plan.id)).all()
    views=[budget_view(db,b) for b in budgets]
    total=sum((b.eligible_budget for b in budgets),Decimal('0.00'));allocated=sum((v.allocated for v in views),Decimal('0.00'))
    return s.Summary(workers=len({b.person_id for b in budgets}),budgets=len(budgets),open=sum(b.status=='OPEN' for b in budgets),submitted=sum(b.status=='SUBMITTED' for b in budgets),finalized=sum(b.status=='FINALIZED' for b in budgets),eligible_budget=total,allocated=allocated,remaining=total-allocated,currency=plan.currency)


def my_plan(db,person_id,plan_id):
    rows=db.scalars(select(m.FBPWorkerBudget).where(m.FBPWorkerBudget.person_id==person_id,m.FBPWorkerBudget.plan_id==plan_id).order_by(m.FBPWorkerBudget.assignment_number)).all()
    if not rows:raise NotFound('No benefit budget is linked to you for this plan.')
    plan=get(db,m.FBPPlan,plan_id)
    return s.PlanView(plan=s.PlanRead.model_validate(plan),components=[s.ComponentRead.model_validate(c) for c in components(db,plan_id) if c.is_active],budgets=[budget_view(db,b) for b in rows])


def my_plans(db,person_id,offset=0,limit=50):
    rows=db.scalars(select(m.FBPPlan).where(m.FBPPlan.id.in_(select(m.FBPWorkerBudget.plan_id).where(m.FBPWorkerBudget.person_id==person_id))).order_by(m.FBPPlan.plan_year.desc(),m.FBPPlan.code).offset(offset).limit(limit)).all()
    return [my_plan(db,person_id,p.id) for p in rows]

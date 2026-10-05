"""Benefits oversight and ownership-bound self-service."""
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app import models as m
from app.api.dependencies import require_hr, get_current_user
from app.api.core_hr import CoreHRRoute, save
from app.api.payroll import own_person
from app.core.database import get_db
from app.services.core_hr.common import get
from app.services.fbp import service as f
from app.schemas import fbp as s
router=APIRouter(prefix='/fbp',tags=['Benefits simulation'],route_class=CoreHRRoute)
staff=[Depends(require_hr)]


@router.get('/plans',response_model=list[s.PlanRead],dependencies=staff)
def plans(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=Depends(get_db)):
    return f.plans(db,offset,limit)


@router.post('/plans',response_model=s.PlanRead,status_code=201,dependencies=staff)
def create(payload:s.PlanCreate,db:Session=Depends(get_db)):
    return save(db,f.create_plan,payload)


@router.get('/plans/{identifier}',response_model=s.PlanRead,dependencies=staff)
def detail(identifier:UUID,db:Session=Depends(get_db)):
    return get(db,m.FBPPlan,identifier)


@router.patch('/plans/{identifier}',response_model=s.PlanRead,dependencies=staff)
def update(identifier:UUID,payload:s.PlanUpdate,db:Session=Depends(get_db)):
    return save(db,f.update_plan,identifier,payload)


@router.get('/plans/{identifier}/components',response_model=list[s.ComponentRead],dependencies=staff)
def components(identifier:UUID,db:Session=Depends(get_db)):
    return f.components(db,identifier)


@router.post('/plans/{identifier}/components',response_model=s.ComponentRead,status_code=201,dependencies=staff)
def add_component(identifier:UUID,payload:s.ComponentCreate,db:Session=Depends(get_db)):
    return save(db,f.create_component,identifier,payload)


@router.patch('/components/{identifier}',response_model=s.ComponentRead,dependencies=staff)
def update_component(identifier:UUID,payload:s.ComponentUpdate,db:Session=Depends(get_db)):
    return save(db,f.update_component,identifier,payload)


@router.post('/plans/{identifier}/open',response_model=s.PlanRead,dependencies=staff)
def open_plan(identifier:UUID,db:Session=Depends(get_db)):
    return save(db,f.open_plan,identifier)


@router.post('/plans/{identifier}/generate-budgets',response_model=s.Summary,dependencies=staff)
def generate(identifier:UUID,db:Session=Depends(get_db)):
    return save(db,f.generate_budgets,identifier)


@router.post('/plans/{identifier}/close',response_model=s.PlanRead,dependencies=staff)
def close(identifier:UUID,db:Session=Depends(get_db)):
    return save(db,f.close_plan,identifier)


@router.get('/plans/{identifier}/workers',response_model=list[s.BudgetRead],dependencies=staff)
def workers(identifier:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=Depends(get_db)):
    return f.workers(db,identifier,offset,limit)


@router.get('/plans/{identifier}/summary',response_model=s.Summary,dependencies=staff)
def summary(identifier:UUID,db:Session=Depends(get_db)):
    return f.summary(db,identifier)


@router.get('/me',response_model=list[s.PlanView])
def mine(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),user:m.User=Depends(get_current_user),db:Session=Depends(get_db)):
    return f.my_plans(db,own_person(user),offset,limit)


@router.get('/me/{identifier}',response_model=s.PlanView)
def my_detail(identifier:UUID,user:m.User=Depends(get_current_user),db:Session=Depends(get_db)):
    return f.my_plan(db,own_person(user),identifier)


@router.post('/me/{identifier}/elections',response_model=s.BudgetRead)
def elections(identifier:UUID,payload:s.ElectionsSave,user:m.User=Depends(get_current_user),db:Session=Depends(get_db)):
    return save(db,f.save_elections,identifier,own_person(user),payload)


@router.post('/me/{identifier}/submit',response_model=s.BudgetRead)
def submit(identifier:UUID,payload:s.BudgetAction,user:m.User=Depends(get_current_user),db:Session=Depends(get_db)):
    return save(db,f.submit,identifier,own_person(user),payload)

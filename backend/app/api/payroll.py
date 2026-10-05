"""Payroll management and self-service, secured by the existing auth layer."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app import models as m
from app.api.dependencies import get_current_user, require_hr
from app.api.core_hr import CoreHRRoute, save
from app.core.database import get_db
from app.schemas import payroll as s
from app.services.core_hr.common import get
from app.services.payroll import service as p

router = APIRouter(prefix='/payroll', tags=['Payroll simulation'], route_class=CoreHRRoute)
staff = [Depends(require_hr)]


@router.get('/definitions', response_model=list[s.DefinitionRead], dependencies=staff)
def definitions(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    return p.listing(db, m.PayrollDefinition, offset, limit)


@router.post('/definitions', response_model=s.DefinitionRead, status_code=201, dependencies=staff)
def create_definition(payload: s.DefinitionCreate, db: Session = Depends(get_db)):
    return save(db, p.create_definition, payload)


@router.get('/definitions/{identifier}', response_model=s.DefinitionRead, dependencies=staff)
def definition(identifier: UUID, db: Session = Depends(get_db)):
    return get(db, m.PayrollDefinition, identifier)


@router.get('/periods', response_model=list[s.PeriodRead], dependencies=staff)
def periods(payroll_definition_id: UUID | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    return p.listing(db, m.PayPeriod, offset, limit, payroll_definition_id=payroll_definition_id)


@router.post('/periods', response_model=s.PeriodRead, status_code=201, dependencies=staff)
def create_period(payload: s.PeriodCreate, db: Session = Depends(get_db)):
    return save(db, p.create_period, payload)


@router.get('/periods/{identifier}', response_model=s.PeriodRead, dependencies=staff)
def period(identifier: UUID, db: Session = Depends(get_db)):
    return get(db, m.PayPeriod, identifier)


@router.post('/periods/{identifier}/process', response_model=s.RunRead, status_code=201)
def process(identifier: UUID, user: m.User = Depends(require_hr), db: Session = Depends(get_db)):
    return save(db, p.process, identifier, user.id)


@router.get('/runs', response_model=list[s.RunRead], dependencies=staff)
def runs(pay_period_id: UUID | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    return p.listing(db, m.PayrollRun, offset, limit, pay_period_id=pay_period_id)


@router.get('/runs/{identifier}', response_model=s.RunDetail, dependencies=staff)
def run(identifier: UUID, db: Session = Depends(get_db)):
    return p.run_detail(db, identifier)


@router.get('/runs/{identifier}/results', response_model=list[s.ResultRead], dependencies=staff)
def results(identifier: UUID, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    get(db, m.PayrollRun, identifier)
    return p.listing(db, m.PayrollResult, offset, limit, payroll_run_id=identifier)


@router.get('/results/{identifier}', response_model=s.ResultDetail, dependencies=staff)
def result(identifier: UUID, db: Session = Depends(get_db)):
    return p.result_detail(db, get(db, m.PayrollResult, identifier))


def own_person(user):
    if not {r.name for r in user.roles} & {'EMPLOYEE', 'HR', 'ADMIN'}:
        raise HTTPException(403, 'Insufficient permissions.')
    if not user.person_id:
        raise HTTPException(404, 'No person is linked to this account.')
    return user.person_id


@router.get('/me', response_model=list[s.ResultDetail])
def my_results(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), user: m.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [p.result_detail(db, row) for row in p.listing(db, m.PayrollResult, offset, limit, person_id=own_person(user))]


@router.get('/me/{identifier}', response_model=s.ResultDetail)
def my_result(identifier: UUID, user: m.User = Depends(get_current_user), db: Session = Depends(get_db)):
    person_id = own_person(user)
    result = get(db, m.PayrollResult, identifier)
    if result.person_id != person_id:
        raise HTTPException(404, 'Payroll result not found.')
    return p.result_detail(db, result)

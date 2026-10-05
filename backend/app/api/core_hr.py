"""Core HR endpoints. Staff manage data; employees resolve their own linked identity."""
from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app import models as m
from app.api.dependencies import get_current_user, require_hr
from app.core.database import get_db
from app.schemas import core_hr as s
from app.services.core_hr import employment as e, queries, records
from app.services.core_hr.common import Conflict, HRError, InvalidOperation, NotFound, get

class CoreHRRoute(APIRoute):
    """Keep database failures safe for reads, dependencies, and response loading too."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except SQLAlchemyError:
                raise HTTPException(500, 'The request could not be completed.') from None

        return handler


router = APIRouter(prefix='/core-hr', tags=['Core HR'], route_class=CoreHRRoute)


async def hr_error_handler(request, exc: HRError):
    status = 404 if isinstance(exc, NotFound) else 409 if isinstance(exc, Conflict) else 422 if isinstance(exc, InvalidOperation) else 500
    return JSONResponse(status_code=status, content={'detail': str(exc)})


def save(db, operation, *args):
    try:
        result = operation(db, *args)
        db.commit()
        return result
    except HRError:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, 'The change could not be saved.') from None


def allowed_person(user, person_id):
    roles = {r.name for r in user.roles}
    if roles & {'HR', 'ADMIN'}:
        return
    if 'EMPLOYEE' not in roles or user.person_id != person_id:
        raise HTTPException(403, 'Insufficient permissions.')


def visible_summary(db, person_id, as_of, user):
    summary = queries.worker_summary(db, person_id, as_of)
    if not {r.name for r in user.roles} & {'HR', 'ADMIN'}:
        # Self-service exposes the employee's reporting link, not another worker's
        # personal/contact fields or employment history.
        for placement in summary.placements:
            placement.manager = None
            placement.manager_assignment = None
    return summary


# Generate the same small, typed CRUD surface for each named reference resource.
def reference_routes(slug, model):
    create_schema, read_schema, update_schema = s.REFERENCE_SCHEMAS[model.__name__]
    def listing(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
        return [read_schema.model_validate(row) for row in records.list_records(db, model, offset, limit)]
    def detail(identifier: UUID, db: Session = Depends(get_db)):
        return read_schema.model_validate(get(db, model, identifier))
    def create(payload: create_schema, db: Session = Depends(get_db)):
        return read_schema.model_validate(save(db, records.create_reference, model, payload))
    def update(identifier: UUID, payload: update_schema, db: Session = Depends(get_db)):
        return read_schema.model_validate(save(db, records.update_reference, model, identifier, payload))
    prefix = '/reference/' + slug
    for path, method, handler, response, status in [(prefix, 'GET', listing, list[read_schema], 200),
        (prefix, 'POST', create, read_schema, 201), (prefix + '/{identifier}', 'GET', detail, read_schema, 200),
        (prefix + '/{identifier}', 'PATCH', update, read_schema, 200)]:
        router.add_api_route(path, handler, methods=[method], response_model=response, status_code=status,
            dependencies=[Depends(require_hr)], name=f'{method.lower()}_{slug.replace("-", "_")}_{handler.__name__}')


for slug, model in records.REFERENCES.items():
    reference_routes(slug, model)


@router.post('/persons', response_model=s.PersonRead, status_code=201, dependencies=[Depends(require_hr)])
def create_person(payload: s.PersonCreate, db: Session = Depends(get_db)):
    return s.PersonRead.model_validate(save(db, records.create_person, payload))


@router.get('/persons', response_model=list[s.PersonRead], dependencies=[Depends(require_hr)])
def persons(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    return [s.PersonRead.model_validate(row) for row in records.list_records(db, m.Person, offset, limit)]


@router.get('/persons/{person_id}', response_model=s.PersonRead)
def person(person_id: UUID, user: m.User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed_person(user, person_id)
    return s.PersonRead.model_validate(get(db, m.Person, person_id))


@router.patch('/persons/{person_id}', response_model=s.PersonRead, dependencies=[Depends(require_hr)])
def update_person(person_id: UUID, payload: s.PersonUpdate, db: Session = Depends(get_db)):
    return s.PersonRead.model_validate(save(db, records.update_person, person_id, payload))


@router.post('/workers/hire', response_model=s.HireResult, status_code=201, dependencies=[Depends(require_hr)])
def hire(payload: s.HireRequest, db: Session = Depends(get_db)):
    return save(db, e.hire, payload)


@router.post('/workers/{person_id}/rehire', response_model=s.HireResult, status_code=201, dependencies=[Depends(require_hr)])
def rehire(person_id: UUID, payload: s.RehireRequest, db: Session = Depends(get_db)):
    return save(db, e.rehire, person_id, payload)


@router.get('/workers', response_model=list[s.WorkerSummary], dependencies=[Depends(require_hr)])
def workers(as_of: s.Day = Query(default_factory=date.today), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    return [queries.worker_summary(db, p.id, as_of) for p in records.list_records(db, m.Person, offset, limit)]


@router.get('/workers/{person_id}', response_model=s.WorkerSummary)
def worker(person_id: UUID, as_of: s.Day = Query(default_factory=date.today), user: m.User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed_person(user, person_id)
    return visible_summary(db, person_id, as_of, user)


@router.get('/me', response_model=s.WorkerSummary)
def me(as_of: s.Day = Query(default_factory=date.today), user: m.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.person_id:
        raise HTTPException(404, 'No person is linked to this account.')
    allowed_person(user, user.person_id)
    return visible_summary(db, user.person_id, as_of, user)


@router.get('/persons/{person_id}/work-relationships', response_model=list[s.WorkRelationshipRead], dependencies=[Depends(require_hr)])
def relationships(person_id: UUID, db: Session = Depends(get_db)):
    return [s.WorkRelationshipRead.model_validate(row) for row in e.relationships_for_person(db, person_id)]


@router.post('/assignments/{assignment_id}/changes', response_model=s.AssignmentVersionRead, status_code=201, dependencies=[Depends(require_hr)])
def change_assignment(assignment_id: UUID, payload: s.AssignmentVersionCreate, db: Session = Depends(get_db)):
    return s.AssignmentVersionRead.model_validate(save(db, e.change_version, assignment_id, payload))


@router.post('/assignments/{assignment_id}/compensation', response_model=s.AssignmentCompensationRead, status_code=201, dependencies=[Depends(require_hr)])
def change_compensation(assignment_id: UUID, payload: s.AssignmentCompensationCreate, db: Session = Depends(get_db)):
    return s.AssignmentCompensationRead.model_validate(save(db, e.change_compensation, assignment_id, payload))


@router.post('/assignments/{assignment_id}/end', response_model=s.AssignmentRead, dependencies=[Depends(require_hr)])
def end_assignment(assignment_id: UUID, payload: s.EndRequest, db: Session = Depends(get_db)):
    return s.AssignmentRead.model_validate(save(db, e.end_assignment, assignment_id, payload))


@router.post('/work-relationships/{relationship_id}/terminate', response_model=s.WorkRelationshipRead, dependencies=[Depends(require_hr)])
def terminate(relationship_id: UUID, payload: s.EndRequest, db: Session = Depends(get_db)):
    return s.WorkRelationshipRead.model_validate(save(db, e.terminate_relationship, relationship_id, payload))

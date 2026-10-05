"""Reference and person operations. No hard-delete entry points."""
from sqlalchemy import select
from app import models as m
from app.schemas import core_hr as s
from .common import Conflict, InvalidOperation, active, atomic, get

REFERENCES = {
    'legal-employers': m.LegalEmployer, 'business-units': m.BusinessUnit,
    'departments': m.Department, 'jobs': m.Job, 'grades': m.Grade, 'locations': m.Location,
}


def list_records(db, model, offset=0, limit=50):
    return list(db.scalars(select(model).order_by(model.id).offset(offset).limit(limit)))


@atomic
def create_reference(db, model, payload):
    if model is m.Department:
        active(db, m.BusinessUnit, payload.business_unit_id)
    row = model(**payload.model_dump())
    db.add(row)
    db.flush()
    return row


@atomic
def update_reference(db, model, identifier, payload):
    row = get(db, model, identifier, lock=True)
    create = s.REFERENCE_SCHEMAS[model.__name__][0]
    data = create.model_validate(row).model_dump()
    data.update(payload.model_dump(exclude_unset=True))
    valid = create.model_validate(data)
    if model is m.Department and valid.business_unit_id != row.business_unit_id:
        active(db, m.BusinessUnit, valid.business_unit_id)
    for key, value in valid.model_dump().items():
        setattr(row, key, value)
    db.flush()
    return row


@atomic
def create_person(db, payload):
    if db.scalar(select(m.Person.id).where(m.Person.person_number == payload.person_number)):
        raise Conflict('Person number already exists.')
    person = m.Person(**payload.model_dump())
    db.add(person)
    db.flush()
    return person


@atomic
def update_person(db, identifier, payload):
    person = get(db, m.Person, identifier, lock=True)
    data = s.PersonCreate.model_validate(person).model_dump()
    changes = payload.model_dump(exclude_unset=True)
    if 'person_number' in changes:
        raise InvalidOperation('Person number is immutable.')
    data.update(changes)
    for key, value in s.PersonCreate.model_validate(data).model_dump().items():
        setattr(person, key, value)
    db.flush()
    return person

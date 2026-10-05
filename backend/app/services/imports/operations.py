"""Resolve CSV identifiers and execute existing Core HR domain operations."""
import re
from datetime import date
from sqlalchemy import select
from pydantic import ValidationError
from app import models as m
from app.schemas import core_hr as s
from app.services.core_hr import employment, records
from app.services.core_hr.common import InvalidOperation, Conflict, NotFound, StorageError
from .templates import required


class RowError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def resolve(db, model, field, value, code='REFERENCE_NOT_FOUND', business_unit=None):
    query = select(model).where(getattr(model, field) == value.upper())
    if business_unit is not None:
        query = query.where(model.business_unit_id == business_unit)
    row = db.scalar(query)
    if row is None:
        raise RowError(code, f'{field}: reference was not found in the selected context.')
    return row.id


def prepare(db, kind, raw):
    data = {k: v.strip() for k, v in raw.items()}
    for key in required(kind):
        if not data.get(key):
            raise RowError('MISSING_REQUIRED_FIELD', f'{key} is required.')
    for key in ('start_date','effective_date','date_of_birth'):
        if data.get(key):
            try:
                if date.fromisoformat(data[key]).isoformat() != data[key]:
                    raise ValueError()
            except ValueError:
                raise RowError('INVALID_DATE', f'{key} must use YYYY-MM-DD.') from None
    if 'annual_base_salary' in data and not re.fullmatch(r'\d+(?:\.\d{1,2})?', data['annual_base_salary']):
        raise RowError('INVALID_DECIMAL', 'annual_base_salary must be a nonnegative decimal with at most two decimal places.')
    for key, choices in {'employment_type': ('REGULAR','FIXED_TERM','INTERN'), 'status': ('ACTIVE','ON_LEAVE','SUSPENDED'), 'work_time_type': ('FULL_TIME','PART_TIME')}.items():
        if key in data:
            data[key] = data[key].upper()
            if data[key] and data[key] not in choices:
                raise RowError('INVALID_ENUM', f'{key} must be one of: {", ".join(choices)}.')
    if kind == 'PERSON_UPDATE':
        identifier = resolve(db,m.Person,'person_number',data.pop('person_number'))
        # Blank cells leave fields unchanged; <CLEAR> explicitly clears nullable fields.
        changes = {k: None if v == '<CLEAR>' else v for k,v in data.items() if v}
        if not changes:
            raise RowError('MISSING_REQUIRED_FIELD', 'Provide at least one changed person field.')
        return identifier, s.PersonUpdate(**changes)
    identifier = None
    if kind != 'WORKER_HIRE':
        identifier = resolve(db,m.Assignment,'assignment_number',data.pop('assignment_number'),'ASSIGNMENT_NOT_FOUND')
    if kind == 'COMPENSATION_CHANGE':
        return identifier, s.AssignmentCompensationCreate(effective_from=data['effective_date'],annual_base_salary=data['annual_base_salary'],currency=data['currency'])
    bu = resolve(db,m.BusinessUnit,'code',data['business_unit_code'])
    version = dict(business_unit_id=bu,
        department_id=resolve(db,m.Department,'code',data['department_code'],business_unit=bu),
        job_id=resolve(db,m.Job,'code',data['job_code']),
        location_id=resolve(db,m.Location,'code',data['location_code']),
        grade_id=resolve(db,m.Grade,'code',data['grade_code']) if data.get('grade_code') else None,
        manager_assignment_id=resolve(db,m.Assignment,'assignment_number',data['manager_assignment_number'],'INVALID_MANAGER') if data.get('manager_assignment_number') else None,
        status=data.get('status') or 'ACTIVE',work_time_type=data['work_time_type'])
    if kind == 'ASSIGNMENT_CHANGE':
        return identifier, s.AssignmentVersionCreate(effective_from=data['effective_date'], **version)
    for model, field, code in [(m.Person,'person_number','DUPLICATE_PERSON_NUMBER'),(m.Assignment,'assignment_number','DUPLICATE_ASSIGNMENT_NUMBER')]:
        if db.scalar(select(model.id).where(getattr(model,field)==data[field].upper())):
            raise RowError(code, f'{field} already exists; this importer does not rehire existing people.')
    person = s.PersonCreate(**{k: v for k,v in data.items() if k in s.PersonCreate.model_fields and v})
    return None, s.HireRequest(person=person, legal_employer_id=resolve(db,m.LegalEmployer,'code',data['legal_employer_code']),
        employment_type=data['employment_type'],joining_date=data['start_date'],assignment_number=data['assignment_number'],
        annual_base_salary=data['annual_base_salary'],currency=data['currency'],**version)


def apply(db, kind, identifier, payload):
    if kind == 'WORKER_HIRE':
        result = employment.hire(db,payload)
        return {'person_id':str(result.person.id),'assignment_id':str(result.assignment.id),'work_relationship_id':str(result.work_relationship.id)}
    operation = {'PERSON_UPDATE':records.update_person,'ASSIGNMENT_CHANGE':employment.change_version,'COMPENSATION_CHANGE':employment.change_compensation}[kind]
    result = operation(db,identifier,payload)
    return {'id':str(result.id),'target_id':str(identifier)}


def safe_error(exc):
    if isinstance(exc, RowError):
        return exc.code, exc.message
    if isinstance(exc, ValidationError):
        fields = ', '.join('.'.join(map(str,e['loc'])) for e in exc.errors(include_input=False))
        return 'INVALID_FIELD', 'Invalid field values: ' + fields[:350]
    if isinstance(exc, StorageError):
        return 'PROCESSING_ERROR', 'The row could not be saved. No changes from this row were retained.'
    if isinstance(exc, (InvalidOperation,Conflict,NotFound)):
        message = str(exc)
        code = 'INVALID_MANAGER' if any(x in message.lower() for x in ('manager','reporting','manage')) else 'BUSINESS_RULE_VIOLATION'
        return code, message[:500]
    return 'PROCESSING_ERROR', 'The row could not be processed. No changes from this row were retained.'

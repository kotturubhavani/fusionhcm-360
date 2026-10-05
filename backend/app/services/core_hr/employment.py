"""Employment timelines and atomic hiring. History changes append dated snapshots."""
from datetime import date, timedelta
from sqlalchemy import select
from app import models as m
from app.schemas import core_hr as s
from .common import Conflict, InvalidOperation, active, atomic, get
from .records import create_person

DAY = timedelta(days=1)


def covers(start, end, at):
    return start <= at and (end is None or at <= end)


def inside(start, end, parent_start, parent_end):
    if start < parent_start or (end is not None and end < start) or (parent_end is not None and (end is None or end > parent_end)):
        raise InvalidOperation('Dates must fall within the parent employment period.')


def relationship_status(row, as_of):
    return 'UPCOMING' if as_of < row.start_date else 'ENDED' if row.end_date and as_of > row.end_date else 'ACTIVE'


def relationships_for_person(db, person_id):
    get(db, m.Person, person_id)
    return list(db.scalars(select(m.WorkRelationship).where(m.WorkRelationship.person_id == person_id).order_by(m.WorkRelationship.start_date, m.WorkRelationship.id).execution_options(populate_existing=True)))


def assignments_for_relationship(db, relationship_id):
    get(db, m.WorkRelationship, relationship_id)
    return list(db.scalars(select(m.Assignment).where(m.Assignment.work_relationship_id == relationship_id).order_by(m.Assignment.start_date, m.Assignment.id).execution_options(populate_existing=True)))


def current_relationships(db, person_id, as_of):
    return [r for r in relationships_for_person(db, person_id) if relationship_status(r, as_of) == 'ACTIVE']


def current_history(db, model, assignment_id, as_of):
    rows = list(db.scalars(select(model).where(model.assignment_id == assignment_id, model.effective_from <= as_of,
        (model.effective_to.is_(None)) | (model.effective_to >= as_of)).execution_options(populate_existing=True)))
    if len(rows) > 1:
        raise Conflict('Overlapping history requires correction.')
    return rows[0] if rows else None


def current_version(db, assignment_id, as_of):
    return current_history(db, m.AssignmentVersion, assignment_id, as_of)


def current_compensation(db, assignment_id, as_of):
    return current_history(db, m.AssignmentCompensation, assignment_id, as_of)


@atomic
def create_relationship(db, payload):
    active(db, m.Person, payload.person_id)
    active(db, m.LegalEmployer, payload.legal_employer_id)
    get(db, m.Person, payload.person_id, lock=True)
    for existing in relationships_for_person(db, payload.person_id):
        if existing.legal_employer_id == payload.legal_employer_id and max(existing.start_date, payload.start_date) <= min(existing.end_date or date.max, payload.end_date or date.max):
            raise Conflict('Employment periods overlap for this person and legal employer.')
    row = m.WorkRelationship(**payload.model_dump())
    db.add(row)
    db.flush()
    return row


@atomic
def create_assignment(db, payload):
    parent = get(db, m.WorkRelationship, payload.work_relationship_id, lock=True)
    inside(payload.start_date, payload.end_date, parent.start_date, parent.end_date)
    if db.scalar(select(m.Assignment.id).where(m.Assignment.assignment_number == payload.assignment_number)):
        raise Conflict('Assignment number already exists.')
    row = m.Assignment(**payload.model_dump())
    db.add(row)
    db.flush()
    return row


def history_rows(db, model, assignment_id):
    return list(db.scalars(select(model).where(model.assignment_id == assignment_id).order_by(model.effective_from).execution_options(populate_existing=True).with_for_update()))


def check_coverage(assignment, rows):
    if not rows:
        return
    if rows[0].effective_from != assignment.start_date or rows[-1].effective_to != assignment.end_date:
        raise Conflict('History must cover the complete assignment period.')
    for previous, following in zip(rows, rows[1:]):
        if previous.effective_to is None or previous.effective_to + DAY != following.effective_from:
            raise Conflict('History contains an overlap or gap.')


def validate_reporting(db):
    """Validate each constant interval of the dated reporting graph, not just today."""
    assignments = {a.id: a for a in db.scalars(select(m.Assignment).execution_options(populate_existing=True))}
    relationships = {r.id: r for r in db.scalars(select(m.WorkRelationship))}
    versions = list(db.scalars(select(m.AssignmentVersion).execution_options(populate_existing=True)))
    boundaries = {v.effective_from for v in versions}
    for v in versions:
        if v.effective_to and v.effective_to < date.max:
            boundaries.add(v.effective_to + DAY)
    for a in assignments.values():
        boundaries.add(a.start_date)
        if a.end_date and a.end_date < date.max:
            boundaries.add(a.end_date + DAY)
    for at in sorted(boundaries):
        current = {v.assignment_id: v for v in versions if covers(v.effective_from, v.effective_to, at)}
        edges = {}
        for child_id, version in current.items():
            manager_id = version.manager_assignment_id
            if manager_id is None:
                continue
            manager = assignments.get(manager_id)
            manager_version = current.get(manager_id)
            if not manager or not covers(manager.start_date, manager.end_date, at) or not manager_version or manager_version.status != 'ACTIVE':
                raise InvalidOperation('Manager must have an ACTIVE assignment version throughout the reporting period.')
            child = assignments[child_id]
            if relationships[child.work_relationship_id].person_id == relationships[manager.work_relationship_id].person_id:
                raise InvalidOperation('A person cannot manage their own assignment.')
            edges[child_id] = manager_id
        for child in edges:
            visited = set()
            people = set()
            while True:
                if child in visited:
                    raise InvalidOperation('Reporting cycle detected.')
                person_id = relationships[assignments[child].work_relationship_id].person_id
                if person_id in people:
                    raise InvalidOperation('A reporting chain cannot return to the same person through another assignment.')
                visited.add(child)
                people.add(person_id)
                if child not in edges:
                    break
                child = edges[child]


def append_history(db, assignment, model, payload):
    rows = history_rows(db, model, assignment.id)
    check_coverage(assignment, rows)
    start = payload.effective_from
    inside(start, assignment.end_date, assignment.start_date, assignment.end_date)
    if not rows and start != assignment.start_date:
        raise InvalidOperation('Initial history must begin on the assignment start date.')
    if rows:
        if start <= rows[-1].effective_from:
            raise Conflict('Dated changes must follow the latest history start; duplicate or overlapping changes are not allowed.')
        rows[-1].effective_to = start - DAY
    row = model(assignment_id=assignment.id, effective_to=assignment.end_date, **payload.model_dump())
    db.add(row)
    db.flush()
    check_coverage(assignment, rows + [row])
    return row


@atomic
def change_version(db, assignment_id, payload):
    assignment = get(db, m.Assignment, assignment_id, lock=True)
    department = active(db, m.Department, payload.department_id)
    active(db, m.BusinessUnit, payload.business_unit_id)
    active(db, m.Job, payload.job_id)
    active(db, m.Location, payload.location_id)
    if payload.grade_id:
        active(db, m.Grade, payload.grade_id)
    if department.business_unit_id != payload.business_unit_id:
        raise InvalidOperation('Department does not belong to the selected business unit.')
    if payload.manager_assignment_id:
        get(db, m.Assignment, payload.manager_assignment_id)
        if payload.manager_assignment_id == assignment.id:
            raise InvalidOperation('An assignment cannot manage itself.')
    row = append_history(db, assignment, m.AssignmentVersion, payload)
    validate_reporting(db)
    return row


@atomic
def change_compensation(db, assignment_id, payload):
    assignment = get(db, m.Assignment, assignment_id, lock=True)
    return append_history(db, assignment, m.AssignmentCompensation, payload)


def close_assignment(db, assignment, end):
    if end < assignment.start_date or (assignment.end_date and end > assignment.end_date):
        raise InvalidOperation('Invalid assignment end date.')
    for model in (m.AssignmentVersion, m.AssignmentCompensation):
        rows = history_rows(db, model, assignment.id)
        check_coverage(assignment, rows)
        if rows:
            if rows[-1].effective_from > end:
                raise Conflict('A scheduled history change exists after the proposed end date.')
            rows[-1].effective_to = end
    assignment.end_date = end
    db.flush()


@atomic
def end_assignment(db, assignment_id, payload):
    assignment = get(db, m.Assignment, assignment_id, lock=True)
    close_assignment(db, assignment, payload.end_date)
    validate_reporting(db)
    return assignment


@atomic
def terminate_relationship(db, relationship_id, payload):
    row = get(db, m.WorkRelationship, relationship_id, lock=True)
    if payload.end_date < row.start_date or (row.end_date and payload.end_date > row.end_date):
        raise InvalidOperation('Invalid relationship end date.')
    for assignment in assignments_for_relationship(db, row.id):
        if assignment.end_date is None or assignment.end_date > payload.end_date:
            close_assignment(db, assignment, payload.end_date)
    row.end_date = payload.end_date
    row.termination_reason = payload.reason
    db.flush()
    validate_reporting(db)
    return row


@atomic
def hire(db, payload):
    person = get(db, m.Person, payload.person_id) if payload.person_id else create_person(db, payload.person)
    relationship = create_relationship(db, s.WorkRelationshipCreate(person_id=person.id, legal_employer_id=payload.legal_employer_id,
        employment_type=payload.employment_type, start_date=payload.joining_date, end_date=payload.end_date))
    assignment = create_assignment(db, s.AssignmentCreate(work_relationship_id=relationship.id, assignment_number=payload.assignment_number,
        start_date=payload.joining_date, end_date=payload.end_date))
    version = change_version(db, assignment.id, s.AssignmentVersionCreate(effective_from=payload.joining_date,
        **{key: getattr(payload, key) for key in s.VersionDetails.model_fields}))
    compensation = change_compensation(db, assignment.id, s.AssignmentCompensationCreate(effective_from=payload.joining_date,
        annual_base_salary=payload.annual_base_salary, currency=payload.currency))
    return s.HireResult(person=person, work_relationship=relationship, assignment=assignment, version=version, compensation=compensation)


@atomic
def rehire(db, person_id, payload):
    if not relationships_for_person(db, person_id):
        raise InvalidOperation('Rehire requires an existing employment relationship.')
    data = payload.model_dump(exclude={'person', 'person_id'})
    return hire(db, s.HireRequest(person_id=person_id, **data))

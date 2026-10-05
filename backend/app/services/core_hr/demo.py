"""Explicit, atomic synthetic demo seed. No accounts or startup hooks."""
from datetime import date
from sqlalchemy import select
from app import models as m
from app.schemas import core_hr as s
from app.services.core_hr import employment as e, records
from app.services.core_hr.common import Conflict, atomic

PREFIX = 'DEMO360_'


def validate_existing_demo(db, people):
    """Check seed identity and history coverage without overwriting later edits."""
    by_number = {person.person_number: person for person in people}
    expected = {f'{PREFIX}A{i:02}': by_number[f'{PREFIX}P{i:02}'].id for i in range(10)}
    expected[f'{PREFIX}A09R'] = by_number[f'{PREFIX}P09'].id
    assignments = list(db.scalars(select(m.Assignment).where(m.Assignment.assignment_number.in_(expected))))
    if len(assignments) != len(expected):
        raise Conflict('Incomplete demo assignments; refusing to overwrite HR history.')
    for assignment in assignments:
        if assignment.work_relationship.person_id != expected[assignment.assignment_number]:
            raise Conflict('Demo assignment identity mismatch; refusing to overwrite HR history.')
        for model in (m.AssignmentVersion, m.AssignmentCompensation):
            rows = e.history_rows(db, model, assignment.id)
            if not rows:
                raise Conflict('Incomplete demo history; refusing to overwrite HR history.')
            e.check_coverage(assignment, rows)
    for model, stem, count in [(m.LegalEmployer, 'LE', 2), (m.BusinessUnit, 'BU', 2),
                               (m.Department, 'D', 2), (m.Job, 'J', 3),
                               (m.Grade, 'G', 2), (m.Location, 'L', 2)]:
        codes = {f'{PREFIX}{stem}{i}' for i in range(count)}
        if set(db.scalars(select(model.code).where(model.code.in_(codes)))) != codes:
            raise Conflict('Incomplete demo reference data; refusing to overwrite HR history.')


@atomic
def seed_demo(db):
    existing = list(db.scalars(select(m.Person).where(m.Person.person_number.in_([f'{PREFIX}P{i:02}' for i in range(10)]))))
    if existing:
        if len(existing) != 10:
            raise Conflict('Partial demo dataset exists; refusing to overwrite HR history.')
        validate_existing_demo(db, existing)
        return {'created': False, 'persons': 10}

    def ref(model, code, name, **extra):
        row = db.scalar(select(model).where(model.code == PREFIX + code))
        if row:
            raise Conflict('Reserved demo reference codes already exist without the workforce.')
        contract = s.REFERENCE_SCHEMAS[model.__name__][0]
        return records.create_reference(db, model, contract(code=PREFIX + code, name=name, **extra))

    employers = [ref(m.LegalEmployer, f'LE{i}', f'Synthetic Meridian {i} Ltd', country_code='IN') for i in range(2)]
    units = [ref(m.BusinessUnit, f'BU{i}', name) for i, name in enumerate(['Demo Engineering', 'Demo Operations'])]
    departments = [ref(m.Department, f'D{i}', name, business_unit_id=units[i].id) for i, name in enumerate(['Demo Product', 'Demo Delivery'])]
    jobs = [ref(m.Job, f'J{i}', name) for i, name in enumerate(['Demo Team Lead', 'Demo Engineer', 'Demo Analyst'])]
    grades = [ref(m.Grade, f'G{i}', f'Demo Level {i + 1}') for i in range(2)]
    locations = [ref(m.Location, f'L{i}', name, country_code='IN', city=city) for i, (name, city) in enumerate([('Demo South Office', 'Bengaluru'), ('Demo West Office', 'Pune')])]
    names = ['Aster', 'Birch', 'Cedar', 'Dahlia', 'Elm', 'Fern', 'Grove', 'Hazel', 'Iris', 'Juniper']
    hires = []
    for i, name in enumerate(names):
        unit = i % 2
        payload = s.HireRequest(person=s.PersonCreate(person_number=f'{PREFIX}P{i:02}', first_name=name, last_name='Synthetic', personal_email=f'{name.lower()}@example.com'),
            legal_employer_id=employers[unit].id, employment_type=['REGULAR', 'FIXED_TERM', 'INTERN'][i % 3],
            joining_date=date(2024, 1, 1), assignment_number=f'{PREFIX}A{i:02}', business_unit_id=units[unit].id,
            department_id=departments[unit].id, job_id=jobs[0 if i < 2 else 1 + i % 2].id,
            grade_id=grades[1 if i < 2 else 0].id, location_id=locations[unit].id,
            manager_assignment_id=None if i < 2 else hires[unit].assignment.id,
            work_time_type='PART_TIME' if i == 8 else 'FULL_TIME', annual_base_salary=str(600000 + i * 50000), currency='INR')
        hires.append(e.hire(db, payload))
    changed = hires[2]
    details = {key: getattr(changed.version, key) for key in s.VersionDetails.model_fields}
    details.update(business_unit_id=units[1].id, department_id=departments[1].id, manager_assignment_id=hires[1].assignment.id)
    e.change_version(db, changed.assignment.id, s.AssignmentVersionCreate(effective_from=date(2025, 1, 1), **details))
    e.change_compensation(db, changed.assignment.id, s.AssignmentCompensationCreate(effective_from=date(2025, 4, 1), annual_base_salary='850000.00', currency='INR'))
    for i in (8, 9):
        e.terminate_relationship(db, hires[i].work_relationship.id, s.EndRequest(end_date=date(2024, 12, 31), reason='Synthetic demo employment ended'))
    previous = hires[9]
    e.rehire(db, previous.person.id, s.RehireRequest(legal_employer_id=employers[1].id, employment_type='REGULAR', joining_date=date(2025, 2, 1),
        assignment_number=f'{PREFIX}A09R', business_unit_id=units[1].id, department_id=departments[1].id, job_id=jobs[2].id,
        grade_id=grades[0].id, location_id=locations[1].id, manager_assignment_id=hires[1].assignment.id,
        work_time_type='FULL_TIME', annual_base_salary='1100000.00', currency='INR'))
    return {'created': True, 'persons': 10}

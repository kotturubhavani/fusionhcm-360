"""As-of views preserve multiple concurrent employment/assignment contexts."""
from app import models as m
from app.schemas import core_hr as s
from .common import get
from .employment import assignments_for_relationship, covers, current_compensation, current_relationships, current_version, relationship_status


def worker_summary(db, person_id, as_of):
    person = get(db, m.Person, person_id)
    placements = []
    for relationship in current_relationships(db, person_id, as_of):
        for assignment in assignments_for_relationship(db, relationship.id):
            if not covers(assignment.start_date, assignment.end_date, as_of):
                continue
            version = current_version(db, assignment.id, as_of)
            compensation = current_compensation(db, assignment.id, as_of)
            manager_assignment = get(db, m.Assignment, version.manager_assignment_id) if version and version.manager_assignment_id else None
            manager = manager_assignment.work_relationship.person if manager_assignment else None
            placements.append(s.WorkerPlacement(work_relationship=relationship, relationship_status=relationship_status(relationship, as_of),
                assignment=assignment, version=version, compensation=compensation,
                business_unit=version.business_unit if version else None, department=version.department if version else None,
                job=version.job if version else None, grade=version.grade if version else None,
                location=version.location if version else None, manager_assignment=manager_assignment, manager=manager))
    return s.WorkerSummary(person=person, as_of=as_of, placements=placements)

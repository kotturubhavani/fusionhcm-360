"""Local seed-label maintenance preserves financial and identity history."""
import pytest
from sqlalchemy import select
from app import models as m
from test_core_hr import db
from scripts.refresh_seed_labels import label_plan, policy_plan, protected_snapshot


def test_label_update_is_idempotent_and_preserves_protected_values(db):
    plan=label_plan(db)
    policies,_=policy_plan(db)
    plan+=policies
    before=protected_snapshot(db,plan)
    for row,field,old,new in plan:
        setattr(row,field,new)
    db.flush()
    assert protected_snapshot(db,plan)==before
    assert label_plan(db)==[]
    assert policy_plan(db)[0]==[]


def test_label_update_refuses_manual_worker_edits(db):
    person=db.scalar(select(m.Person).where(m.Person.person_number=='DEMO360_P02'))
    person.first_name='Naveen'
    db.flush()
    with pytest.raises(ValueError,match='refusing to overwrite edits'):
        label_plan(db)
    assert person.first_name=='Naveen'


def test_policy_update_refuses_unknown_content(db):
    doc=db.scalar(select(m.Document).where(m.Document.filename=='leave-policy.md'))
    doc.checksum='0'*64
    db.flush()
    with pytest.raises(ValueError,match='Policy has been edited'):
        policy_plan(db)

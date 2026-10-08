"""Rename only the reserved local seed dataset; dry-run by default.

Run from backend/: python scripts/refresh_seed_labels.py --apply
Then reindex policies with --reindex-provider mock (and gemini if used).
No rows are deleted. Row IDs, financial amounts and employment dates stay unchanged.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, UTC
from pathlib import Path
from sqlalchemy import select, text
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import models as m
from app.core.database import SessionLocal, engine
from app.core.config import settings
from app.services.core_hr.seed import WORKERS, EMPLOYERS
from app.services.ai import documents, providers

OLD_WORKERS = ['Aster', 'Birch', 'Cedar', 'Dahlia', 'Elm', 'Fern', 'Grove', 'Hazel', 'Iris', 'Juniper']
LABELS = {'Synthetic Meridian monthly payroll': 'Asterion India Monthly Payroll',
 'Monthly Payroll Summary': 'Monthly Payroll Results',
 'FBP Allocation Status': 'Benefits Allocation Status',
 'Worker Full Snapshot': 'Worker Master Export',
 'Worker Incremental Changes': 'Worker Changes Export',
 'Worker Snapshot File Export': 'Worker Master Outbound',
 'Payroll Results File Export': 'Payroll Results Outbound',
 'FBP Elections File Export': 'Benefits Elections Outbound'}
POLICY_CHECKSUMS = {'benefits-guide.md': '338004452e1f361740b873eb79265ad62085c6973383748ca8c27385977fd491',
 'leave-policy.md': '1122efdd804c0643366dc39f30860f756c5226c038479ab0e4f7ffd9d85c078c',
 'payroll-faq.md': '42eb028696dc6e6421c8242c24f9a2a9655444642887a2bd6492a8df577ad822',
 'remote-work-policy.md': 'e6d6441057095e6d69c43bfeaad5c1a06c9b1cc3988c8ac810ca20210a206615',
 'transfer-policy.md': '08ce464fa0b3934a06d38342ce4da535554d7141e69194009e5e8e6b1a1712a8'}


def change(plan, row, field, old, new):
    current = getattr(row, field)
    if current == new:
        return
    if current != old:
        raise ValueError(f'Unexpected {row.__tablename__}.{field}; refusing to overwrite edits.')
    plan.append((row, field, old, new))


def one(db, model, code):
    return db.scalars(select(model).where(model.code == code)).one()


def label_plan(db):
    plan = []
    people = list(db.scalars(select(m.Person)))
    if {p.person_number for p in people} != {f'DEMO360_P{i:02}' for i in range(10)}:
        raise ValueError('Expected only the ten reserved seed people; no changes made.')
    for i, (first, last) in enumerate(WORKERS):
        person = next(p for p in people if p.person_number == f'DEMO360_P{i:02}')
        change(plan, person, 'first_name', OLD_WORKERS[i], first)
        change(plan, person, 'last_name', 'Synthetic', last)
        change(plan, person, 'personal_email', OLD_WORKERS[i].lower()+'@example.com', first.lower().replace(' ','.')+'.'+last.lower()+'@example.com')
        for model in (m.PayrollResult, m.FBPWorkerBudget):
            for row in db.scalars(select(model).where(model.person_id == person.id)):
                change(plan, row, 'worker_name', OLD_WORKERS[i]+' Synthetic', first+' '+last)
    refs = [
        (m.LegalEmployer, 'LE', [('Synthetic Meridian 0 Ltd', EMPLOYERS[0]), ('Synthetic Meridian 1 Ltd', EMPLOYERS[1])]),
        (m.BusinessUnit, 'BU', [('Demo Engineering','Digital Engineering'), ('Demo Operations','Business Operations')]),
        (m.Department, 'D', [('Demo Product','Product Engineering'), ('Demo Delivery','Delivery Operations')]),
        (m.Job, 'J', [('Demo Team Lead','Technical Lead'), ('Demo Engineer','Software Engineer'), ('Demo Analyst','Business Analyst')]),
        (m.Grade, 'G', [('Demo Level 1','Professional'), ('Demo Level 2','Lead')]),
        (m.Location, 'L', [('Demo South Office','Hyderabad - HITEC City'), ('Demo West Office','Bengaluru - Whitefield')]),
    ]
    for model, stem, labels in refs:
        for i,(old,new) in enumerate(labels):
            change(plan,one(db,model,f'DEMO360_{stem}{i}'),'name',old,new)
    for i,(old,new) in enumerate([('Bengaluru','Hyderabad'),('Pune','Bengaluru')]):
        change(plan,one(db,m.Location,f'DEMO360_L{i}'),'city',old,new)
    for row in db.scalars(select(m.WorkRelationship).where(m.WorkRelationship.person_id.in_([p.id for p in people]), m.WorkRelationship.end_date.is_not(None))):
        change(plan,row,'termination_reason','Synthetic demo employment ended','End of employment')
    definitions=[(m.PayrollDefinition,'PAYROLL','Synthetic Meridian monthly payroll')]
    definitions += [(m.ReportDefinition,c,n) for c,n in [('R_WORKFORCE','Active Workforce by Department'),('R_PAYROLL','Monthly Payroll Summary'),('R_FBP','FBP Allocation Status')]]
    definitions += [(m.ExtractDefinition,c,n) for c,n in [('E_WORKFORCE','Worker Full Snapshot'),('E_CHANGES','Worker Incremental Changes'),('E_PAYROLL','Payroll Results Export')]]
    definitions += [(m.IntegrationDefinition,c,n) for c,n in [('I_WORKERS','Worker Snapshot File Export'),('I_PAYROLL','Payroll Results File Export'),('I_FBP','FBP Elections File Export')]]
    for model,code,old in definitions:
        change(plan,one(db,model,'DEMO360_'+code),'name',old,LABELS.get(old,old))
    for year in (2025,2026):
        benefit=one(db,m.FBPPlan,f'DEMO360_FBP{year}')
        change(plan,benefit,'name',f'Synthetic annual benefits {year}',f'Annual Benefits {year}')
        for row in db.scalars(select(m.FBPComponent).where(m.FBPComponent.plan_id==benefit.id)):
            pairs={'FLEX':('Flexible lifestyle benefit','Meal Benefit'),'LEARNING':('Learning allowance','Learning Allowance'),'WELLNESS':('Wellness benefit','Wellness Allowance'),'COMMUTE':('Commute reimbursement','Transport Allowance')}
            old,new=pairs[row.code]
            change(plan,row,'name',old,new)
    for row in db.scalars(select(m.PayrollResultLine).join(m.PayrollResult).where(m.PayrollResult.person_id.in_([p.id for p in people]))):
        pairs={'BASE_PAY':('Prorated monthly base pay','Basic Pay'),'STANDARD_ALLOWANCE':('Demo standard allowance','Standard Allowance'),'DEMO_RETIREMENT':('Demo retirement deduction','Retirement Contribution'),'DEMO_WITHHOLDING':('Demo withholding deduction','Income Tax Withholding')}
        old,new=pairs[row.code]
        change(plan,row,'name',old,new)
    return plan


def policy_plan(db):
    plan=[]
    sources=db.scalars(select(m.DocumentSource).where(m.DocumentSource.name.in_(['Synthetic demo policies (ALL)','Asterion Policies (ALL)']))).all()
    if len(sources)!=1:
        raise ValueError('Expected exactly one reserved policy source.')
    source=sources[0]
    change(plan,source,'name','Synthetic demo policies (ALL)','Asterion Policies (ALL)')
    docs=db.scalars(select(m.Document).where(m.Document.source_id==source.id)).all()
    if {d.filename for d in docs}!=set(POLICY_CHECKSUMS) or len(docs)!=5:
        raise ValueError('Unexpected policy set; refusing to overwrite documents.')
    for doc in docs:
        content=(Path(__file__).resolve().parents[2]/'synthetic-data'/'policies'/doc.filename).read_bytes()
        checksum=hashlib.sha256(content).hexdigest()
        if doc.checksum==checksum:
            continue
        if doc.checksum!=POLICY_CHECKSUMS[doc.filename]:
            raise ValueError('Policy has been edited; refusing to overwrite it.')
        value,_=documents.extract(doc.filename,content)
        chunks=db.scalars(select(m.DocumentChunk).where(m.DocumentChunk.document_id==doc.id).order_by(m.DocumentChunk.chunk_index)).all()
        new_chunks=documents.chunk_text(value)
        if len(chunks)!=len(new_chunks):
            raise ValueError('Chunk count changed; review policy boundaries before updating.')
        for row,new in zip(chunks,new_chunks,strict=True):
            change(plan,row,'text_content',row.text_content,new)
            change(plan,row,'details',row.details,{'character_start':row.chunk_index*750,'embedding_spaces':[]})
            change(plan,row,'embedding_reference',row.embedding_reference,None)
        change(plan,doc,'checksum',doc.checksum,checksum)
        change(plan,doc,'status',doc.status,'FAILED')
        change(plan,doc,'details',doc.details,{'audience':source.audience,'chunk_count':len(chunks)})
        change(plan,doc,'safe_error_message',doc.safe_error_message,'Reindex updated policy text before retrieval.')
    return plan,docs


def protected_snapshot(db,plan):
    allowed={}
    for row,field,_,_ in plan:
        attr=row.__mapper__.attrs[field]
        allowed.setdefault(row.__tablename__,set()).add(attr.columns[0].name)
    result={}
    for table in m.User.metadata.sorted_tables:
        columns=[c for c in table.columns if c.name not in allowed.get(table.name,set()) and c.name!='updated_at']
        result[table.name]=sorted([tuple(str(v) for v in row) for row in db.execute(select(*columns))])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--reindex-provider',choices=['mock','gemini'])
    parser.add_argument('--actor-email')
    args=parser.parse_args()
    if engine.url.host not in ('localhost','127.0.0.1','::1') or engine.url.database!='fusionhcm360':
        raise ValueError('This command is restricted to the local fusionhcm360 database.')
    if args.reindex_provider and (not args.apply or not args.actor_email):
        parser.error('Reindexing requires --apply and --actor-email.')
    with SessionLocal() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(360,1)'))
        plan=label_plan(db)
        policies,docs=policy_plan(db)
        plan+=policies
        document_ids=[doc.id for doc in docs]
        before=protected_snapshot(db,plan)
        print(f'Planned label/policy field changes: {len(plan)}')
        if not args.apply:
            return
        if plan:
            backup=Path(__file__).resolve().parents[2]/'local-data'/('seed-label-backup-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')+'.json')
            backup.parent.mkdir(exist_ok=True)
            backup.write_text(json.dumps([{'table':r.__tablename__,'id':str(r.id),'field':f,'before':old,'after':new} for r,f,old,new in plan],indent=2),encoding='utf-8')
            print('Saved a changed-field backup under ignored local-data/.')
        for row,field,old,new in plan:
            setattr(row,field,new)
        db.flush()
        if protected_snapshot(db,plan)!=before:
            raise ValueError('A protected value changed; rolling back.')
        db.commit()
        print('Applied. Row IDs, links, dates, amounts and all protected values unchanged.')
    if args.reindex_provider:
        settings.ai_provider=args.reindex_provider
        with SessionLocal() as db:
            actor=db.scalar(select(m.User).where(m.User.email==args.actor_email))
            if not actor:
                raise ValueError('Existing HR/ADMIN actor required.')
            documents.require_staff(actor)
            signature=providers.provider().signature
            for document_id in document_ids:
                chunks=db.scalars(select(m.DocumentChunk).where(m.DocumentChunk.document_id==document_id)).all()
                if all(signature in c.details.get('embedding_spaces',[]) for c in chunks):
                    continue
                row=documents.reindex(db,actor,document_id)
                db.commit()
                if row.status!='INDEXED':
                    raise ValueError('Policy indexing failed; retry reindexing after provider recovery.')
                print('Indexed',row.filename,'with',args.reindex_provider)


if __name__=='__main__':
    main()

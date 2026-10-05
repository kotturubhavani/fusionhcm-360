"""Synchronous bounded jobs. Domain changes and row outcomes commit together."""
import csv
import io
import re
from datetime import UTC, datetime
from sqlalchemy import select
from app import models as m
from app.services.core_hr.common import atomic, get, Conflict, InvalidOperation
from . import templates, operations


def jobs(db, offset=0, limit=50):
    return db.scalars(select(m.ImportJob).order_by(m.ImportJob.created_at.desc(),m.ImportJob.id).offset(offset).limit(limit)).all()


def rows(db, job_id, status=None, offset=0, limit=100):
    get(db,m.ImportJob,job_id)
    query=select(m.ImportRow).where(m.ImportRow.import_job_id==job_id)
    if status:query=query.where(m.ImportRow.status==status)
    return db.scalars(query.order_by(m.ImportRow.row_number).offset(offset).limit(limit)).all()


@atomic
def upload(db, kind, filename, content, user_id):
    parsed=templates.parse(kind,content)
    # Treat the supplied filename only as a display label; never open a path.
    filename=re.split(r'[/\\]',filename or '')[-1]
    filename=''.join(c for c in filename if c.isprintable())[:255]
    if not filename.lower().endswith('.csv'):
        raise InvalidOperation('Upload a .csv file.')
    job=m.ImportJob(object_type=kind,original_filename=filename,total_rows=len(parsed),created_by_user_id=user_id)
    db.add(job);db.flush()
    db.add_all([m.ImportRow(import_job_id=job.id,row_number=n,raw_data=data) for n,data in parsed])
    db.flush()
    return job


@atomic
def validate(db, job_id):
    job=get(db,m.ImportJob,job_id,lock=True)
    if job.status not in ('UPLOADED','VALIDATED'):
        raise Conflict('Processed jobs cannot be validated again. Upload a corrected file as a new job.')
    seen=set();valid=invalid=0
    for row in rows(db,job.id,limit=5000):
        row.normalized_data=None;row.error_code=None;row.error_message=None
        try:
            keys = ['person_number','assignment_number'] if job.object_type=='WORKER_HIRE' else ['person_number' if job.object_type=='PERSON_UPDATE' else 'assignment_number']
            identities=[(key,row.raw_data.get(key,'').strip().upper()) for key in keys]
            if any(identity in seen for identity in identities if identity[1]):
                raise operations.RowError('DUPLICATE_ROW','Only one operation per person/assignment target is allowed in a file.')
            seen.update(identity for identity in identities if identity[1])
            # Run the real rules, then always roll back every Core HR write.
            # Each row sees the existing database, never another preview row.
            with db.begin_nested() as preview:
                identifier,payload=operations.prepare(db,job.object_type,row.raw_data)
                normalized=payload.model_dump(mode='json',exclude_unset=True)
                operations.apply(db,job.object_type,identifier,payload)
                preview.rollback()
            row.normalized_data=normalized
            row.status='VALID';valid+=1
        except Exception as exc:
            row.status='INVALID';row.error_code,row.error_message=operations.safe_error(exc);invalid+=1
        db.flush()
    job.valid_rows=valid;job.invalid_rows=invalid;job.status='VALIDATED';job.validated_at=datetime.now(UTC)
    db.flush();return job


@atomic
def process(db, job_id):
    job=get(db,m.ImportJob,job_id,lock=True)
    if job.status!='VALIDATED':
        raise Conflict('Validate first. A processed job cannot be processed again.')
    if not job.valid_rows:
        raise Conflict('No valid rows to process. Upload a corrected file.')
    try:
        with db.begin_nested():
            _process_rows(db,job)
    except Exception:
        # A job-level failure rolls back this attempt, including successful rows.
        # If the connection itself is lost, the request fails safely and remains retryable.
        job=get(db,m.ImportJob,job_id,lock=True)
        job.status='FAILED'
        job.processed_at=datetime.now(UTC)
        db.flush()
    return job


def _process_rows(db,job):
    job.status='PROCESSING';db.flush()
    for row in rows(db,job.id,'VALID',limit=5000):
        try:
            with db.begin_nested():
                # Re-resolve and revalidate against current data at processing time.
                identifier,payload=operations.prepare(db,job.object_type,row.raw_data)
                result=operations.apply(db,job.object_type,identifier,payload)
            row.created_record_reference=result;row.status='PROCESSED';job.processed_rows+=1
        except Exception as exc:
            row.status='FAILED';row.error_code,row.error_message=operations.safe_error(exc);job.failed_rows+=1
        db.flush()
    job.status='COMPLETED_WITH_ERRORS' if job.invalid_rows or job.failed_rows else 'COMPLETED'
    job.processed_at=datetime.now(UTC);db.flush();return job


def errors_csv(db,job_id):
    output=io.StringIO(newline='');writer=csv.writer(output)
    writer.writerow(['row_number','status','error_code','error_message'])
    for row in rows(db,job_id,limit=5000):
        if row.status in ('INVALID','FAILED'):
            writer.writerow([templates.csv_safe(v) for v in (row.row_number,row.status,row.error_code or '',row.error_message or '')])
    return output.getvalue()

"""Synchronous payroll with immutable results and serialized Core HR reads."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from app import models as m
from app.schemas import payroll as s
from app.services.core_hr.common import atomic, active, get, Conflict, InvalidOperation
from app.services.payroll import rules


@atomic
def create_definition(db, payload: s.DefinitionCreate):
    employer = active(db, m.LegalEmployer, payload.legal_employer_id)
    if employer.country_code != payload.country_code:
        raise InvalidOperation('Payroll and legal employer country must match.')
    row = m.PayrollDefinition(**payload.model_dump())
    db.add(row)
    db.flush()
    return row


@atomic
def create_period(db, payload: s.PeriodCreate):
    active(db, m.PayrollDefinition, payload.payroll_definition_id)
    overlap = db.scalar(select(m.PayPeriod.id).where(
        m.PayPeriod.payroll_definition_id == payload.payroll_definition_id,
        m.PayPeriod.period_start <= payload.period_end,
        m.PayPeriod.period_end >= payload.period_start))
    if overlap:
        raise Conflict('A pay period already covers this month for this payroll definition.')
    row = m.PayPeriod(**payload.model_dump())
    db.add(row)
    db.flush()
    return row


def listing(db, model, offset=0, limit=50, **filters):
    query = select(model).filter_by(**{key: value for key, value in filters.items() if value is not None})
    if model is m.PayrollResult:
        query = query.join(m.PayrollRun, m.PayrollResult.payroll_run_id == m.PayrollRun.id).join(m.PayPeriod, m.PayrollRun.pay_period_id == m.PayPeriod.id)
        ordering = (m.PayPeriod.period_end.desc(), model.person_number, model.assignment_number, model.id)
    elif model is m.PayPeriod:
        ordering = (model.period_start.desc(), model.id)
    elif model is m.PayrollRun:
        ordering = (model.started_at.desc(), model.completed_at.desc().nullslast(), model.id)
    else:
        ordering = (model.code, model.id)
    return db.scalars(query.order_by(*ordering).offset(offset).limit(limit)).all()


def applicable(rows, day):
    matches = [row for row in rows if row.effective_from <= day and (row.effective_to is None or row.effective_to >= day)]
    if len(matches) > 1:
        raise InvalidOperation('Overlapping assignment or compensation history prevents processing.')
    return matches[0] if matches else None


def calculate_assignment(db, definition, period, assignment, relationship):
    start = max(period.period_start, relationship.start_date, assignment.start_date)
    end = min(period.period_end, relationship.end_date or period.period_end, assignment.end_date or period.period_end)
    total_days = (period.period_end - period.period_start).days + 1
    versions = db.scalars(select(m.AssignmentVersion).where(m.AssignmentVersion.assignment_id == assignment.id,
        m.AssignmentVersion.effective_from <= end, or_(m.AssignmentVersion.effective_to.is_(None), m.AssignmentVersion.effective_to >= start))).all()
    compensation = db.scalars(select(m.AssignmentCompensation).where(m.AssignmentCompensation.assignment_id == assignment.id,
        m.AssignmentCompensation.effective_from <= end, or_(m.AssignmentCompensation.effective_to.is_(None), m.AssignmentCompensation.effective_to >= start))).all()
    weighted_annual = Decimal('0')
    paid_days = unpaid_days = 0
    segments = []
    day = start
    while day <= end:
        version, salary = applicable(versions, day), applicable(compensation, day)
        if version and version.status in rules.PAID_STATUSES and salary:
            if salary.currency != definition.currency:
                raise InvalidOperation('Compensation currency differs from payroll currency. No currency conversion is supported.')
            weighted_annual += salary.annual_base_salary
            paid_days += 1
            key = (str(salary.id), str(version.id))
            if segments and segments[-1]['source'] == list(key) and segments[-1]['to'] == (day - timedelta(days=1)).isoformat():
                segments[-1]['to'] = day.isoformat()
                segments[-1]['days'] += 1
            else:
                segments.append(dict(source=list(key), annual_base_salary=str(salary.annual_base_salary),
                    status=version.status, currency=salary.currency, **{'from': day.isoformat(), 'to': day.isoformat(), 'days': 1}))
        else:
            unpaid_days += 1
        day += timedelta(days=1)
    base = weighted_annual / (rules.MONTHS_PER_YEAR * Decimal(total_days))
    allowance = definition.standard_allowance * Decimal(paid_days) / Decimal(total_days)
    return paid_days, total_days, unpaid_days, segments, rules.calculate(base, allowance, definition.retirement_rate, definition.withholding_rate)


def populate_results(db, run, period, definition):
    candidates = db.execute(select(m.Assignment, m.WorkRelationship, m.Person).join(
        m.WorkRelationship, m.Assignment.work_relationship_id == m.WorkRelationship.id).join(
        m.Person, m.WorkRelationship.person_id == m.Person.id).where(
        m.WorkRelationship.legal_employer_id == definition.legal_employer_id,
        m.WorkRelationship.start_date <= period.period_end,
        or_(m.WorkRelationship.end_date.is_(None), m.WorkRelationship.end_date >= period.period_start),
        m.Assignment.start_date <= period.period_end,
        or_(m.Assignment.end_date.is_(None), m.Assignment.end_date >= period.period_start)
    ).order_by(m.Person.person_number, m.Assignment.assignment_number)).all()
    count = 0
    for assignment, relationship, person in candidates:
        days, period_days, unpaid, segments, calculated = calculate_assignment(db, definition, period, assignment, relationship)
        run.unpaid_day_count += unpaid
        if not days:
            run.excluded_assignment_count += 1
            continue
        lines, gross, deductions, net = calculated
        if net < 0:
            raise InvalidOperation('Rounded deductions exceed gross pay. Review the demo rates.')
        result = m.PayrollResult(payroll_run_id=run.id, person_id=person.id, work_relationship_id=relationship.id,
            assignment_id=assignment.id, person_number=person.person_number,
            worker_name=f'{person.first_name} {person.last_name}', assignment_number=assignment.assignment_number,
            gross_pay=gross, total_deductions=deductions, net_pay=net, currency=definition.currency,
            eligible_days=days, period_days=period_days, calculation_snapshot=segments)
        db.add(result)
        db.flush()
        db.add_all([m.PayrollResultLine(payroll_result_id=result.id, line_type=kind, code=code, name=name, amount=amount)
                    for kind, code, name, amount in lines])
        count += 1
    if not count:
        raise InvalidOperation('No eligible assignments with payable compensation were found.')


@atomic
def process(db, period_id, initiated_by=None):
    period = get(db, m.PayPeriod, period_id, lock=True)
    definition = active(db, m.PayrollDefinition, period.payroll_definition_id)
    active(db, m.LegalEmployer, definition.legal_employer_id)
    if period.status != 'OPEN' or db.scalar(select(m.PayrollRun.id).where(m.PayrollRun.pay_period_id == period.id, m.PayrollRun.status == 'COMPLETED')):
        raise Conflict('This period has already been processed or is currently processing.')
    sequence = (db.scalar(select(func.max(m.PayrollRun.run_number)).where(m.PayrollRun.pay_period_id == period.id)) or 0) + 1
    run = m.PayrollRun(pay_period_id=period.id, run_number=sequence, status='PROCESSING',
        initiated_by_user_id=initiated_by, rules_snapshot=rules.snapshot(definition),
        excluded_assignment_count=0, unpaid_day_count=0)
    db.add(run)
    period.status = 'PROCESSING'
    db.flush()
    # A failed attempt retains only safe metadata, never partial payroll results.
    try:
        with db.begin_nested():
            populate_results(db, run, period, definition)
            db.flush()
    except (InvalidOperation, SQLAlchemyError) as exc:
        run.status = 'FAILED'
        run.failure_reason = str(exc) if isinstance(exc, InvalidOperation) else 'Payroll could not be stored. No results were saved.'
        period.status = 'OPEN'
    else:
        run.status = 'COMPLETED'
        period.status = 'PROCESSED'
    run.completed_at = datetime.now(UTC)
    db.flush()
    return run


def run_detail(db, run_id):
    run = get(db, m.PayrollRun, run_id)
    period = get(db, m.PayPeriod, run.pay_period_id)
    definition = get(db, m.PayrollDefinition, period.payroll_definition_id)
    totals = db.execute(select(func.count(m.PayrollResult.id), func.sum(m.PayrollResult.gross_pay),
        func.sum(m.PayrollResult.total_deductions), func.sum(m.PayrollResult.net_pay)).where(m.PayrollResult.payroll_run_id == run_id)).one()
    return s.RunDetail(run=s.RunRead.model_validate(run), period=s.PeriodRead.model_validate(period),
        definition_name=definition.name, currency=definition.currency, result_count=totals[0],
        gross_pay=totals[1] or Decimal('0.00'), total_deductions=totals[2] or Decimal('0.00'), net_pay=totals[3] or Decimal('0.00'))


def result_detail(db, result):
    run = get(db, m.PayrollRun, result.payroll_run_id)
    period = get(db, m.PayPeriod, run.pay_period_id)
    definition = get(db, m.PayrollDefinition, period.payroll_definition_id)
    lines = db.scalars(select(m.PayrollResultLine).where(m.PayrollResultLine.payroll_result_id == result.id).order_by(m.PayrollResultLine.line_type.desc(), m.PayrollResultLine.code)).all()
    return s.ResultDetail(result=s.ResultRead.model_validate(result), period=s.PeriodRead.model_validate(period),
        definition_name=definition.name, lines=[s.LineRead.model_validate(row) for row in lines])

"""Explicit, atomic synthetic payroll seed using the existing DEMO360 workforce."""
from datetime import date
from sqlalchemy import select, func
from app import models as m
from app.schemas import payroll as s
from app.services.core_hr.common import atomic, InvalidOperation
from app.services.payroll import service as p

PREFIX = 'DEMO360_'
MONTHS = [(2025, 7, True), (2025, 8, True), (2026, 10, False)]


@atomic
def seed_demo(db):
    employer = db.scalar(select(m.LegalEmployer).where(m.LegalEmployer.code == PREFIX + 'LE0'))
    if employer is None:
        raise InvalidOperation('Run the synthetic Core HR seed first.')
    outsiders = db.scalar(select(func.count()).select_from(m.Person).join(m.WorkRelationship).where(
        m.WorkRelationship.legal_employer_id == employer.id, ~m.Person.person_number.startswith(PREFIX)))
    if outsiders:
        raise InvalidOperation('Demo employer contains non-demo people; payroll seed stopped without changes.')
    definition = db.scalar(select(m.PayrollDefinition).where(m.PayrollDefinition.code == PREFIX + 'PAYROLL'))
    created = definition is None
    if created:
        definition = p.create_definition(db, s.DefinitionCreate(code=PREFIX + 'PAYROLL', name='Asterion India Monthly Payroll',
            legal_employer_id=employer.id, country_code='IN', currency='INR', retirement_rate='0.0500', withholding_rate='0.1000', standard_allowance='1000.00'))
    elif definition.legal_employer_id != employer.id or definition.currency != 'INR':
        raise InvalidOperation('Existing demo payroll definition does not match the demo employer/currency.')
    from calendar import monthrange
    for year, month, processed in MONTHS:
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        period = db.scalar(select(m.PayPeriod).where(m.PayPeriod.payroll_definition_id == definition.id, m.PayPeriod.period_start == start))
        if period is None:
            if not created:
                raise InvalidOperation('Demo payroll is incomplete; existing history was not changed.')
            period = p.create_period(db, s.PeriodCreate(payroll_definition_id=definition.id, period_name=f'{year}-{month:02d}',
                period_start=start, period_end=end, payment_date=end))
            if processed:
                run = p.process(db, period.id)
                if run.status != 'COMPLETED':
                    raise InvalidOperation('Demo payroll could not complete; no seed changes were saved.')
        elif processed:
            run = db.scalar(select(m.PayrollRun).where(m.PayrollRun.pay_period_id == period.id, m.PayrollRun.status == 'COMPLETED'))
            if period.status != 'PROCESSED' or not run or not db.scalar(select(m.PayrollResult.id).where(m.PayrollResult.payroll_run_id == run.id).limit(1)):
                raise InvalidOperation('Demo payroll history is incomplete; existing records were not changed.')
    return {'created': created, 'definition': definition.code, 'periods': len(MONTHS)}

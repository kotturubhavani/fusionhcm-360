"""Our CSV format; no Oracle HDL compatibility."""
import csv
import io
from app.core.config import settings
from app.services.core_hr.common import InvalidOperation

PERSON = ['person_number','first_name','last_name','preferred_name','date_of_birth','personal_email','phone']
VERSION = ['business_unit_code','department_code','job_code','grade_code','location_code','manager_assignment_number','status','work_time_type']
TEMPLATES = {
    'WORKER_HIRE': PERSON + ['legal_employer_code','employment_type','start_date','assignment_number'] + VERSION + ['annual_base_salary','currency'],
    'PERSON_UPDATE': PERSON,
    'ASSIGNMENT_CHANGE': ['assignment_number','effective_date'] + VERSION,
    'COMPENSATION_CHANGE': ['assignment_number','effective_date','annual_base_salary','currency'],
}
OPTIONAL = {'preferred_name','date_of_birth','personal_email','phone','grade_code','manager_assignment_number','status'}


def required(kind):
    return ['person_number'] if kind == 'PERSON_UPDATE' else [x for x in TEMPLATES[kind] if x not in OPTIONAL]


def template(kind):
    if kind not in TEMPLATES:
        raise InvalidOperation('Unsupported import object type.')
    output = io.StringIO(newline='')
    csv.writer(output).writerow(TEMPLATES[kind])
    return output.getvalue()


def parse(kind, content):
    template(kind)
    if len(content) > settings.import_max_file_bytes:
        raise InvalidOperation('CSV exceeds the configured file size limit.')
    try:
        decoded = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise InvalidOperation('CSV must be UTF-8.') from None
    if '\x00' in decoded:
        raise InvalidOperation('CSV contains a null character.')
    try:
        reader = csv.reader(io.StringIO(decoded, newline=''), strict=True)
        headers = next(reader, [])
        if not headers or len(headers) != len(set(headers)):
            raise InvalidOperation('CSV is empty or has duplicate headers.')
        if set(headers) - set(TEMPLATES[kind]):
            raise InvalidOperation('CSV has unknown headers.')
        if set(required(kind)) - set(headers):
            raise InvalidOperation('CSV is missing required headers.')
        rows = []
        for number, values in enumerate(reader, 2):
            if len(values) != len(headers):
                raise InvalidOperation(f'CSV record {number} has an incorrect field count.')
            if any(len(value) > 10000 for value in values):
                raise InvalidOperation('A CSV field exceeds 10,000 characters.')
            rows.append((number, dict(zip(headers, values))))
            if len(rows) > settings.import_max_rows:
                raise InvalidOperation('CSV exceeds the configured row count limit.')
        if not rows:
            raise InvalidOperation('CSV must contain at least one data row.')
        return rows
    except csv.Error:
        raise InvalidOperation('Malformed CSV quoting or field size.') from None


def csv_safe(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value

"""Validated Core HR contracts. History changes are complete dated snapshots."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, StrictBool, StringConstraints, create_model, field_validator, model_validator


def trimmed(value):
    return value.strip() if isinstance(value, str) else value


def upper(value):
    return value.strip().upper() if isinstance(value, str) else value


def iso_date(value):
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError()
            return parsed
        except ValueError:
            raise ValueError('Use YYYY-MM-DD dates') from None
    if type(value) is not date:
        raise ValueError('Use a date, not a timestamp or number')
    return value


Day = Annotated[date, BeforeValidator(iso_date)]
Code = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=30), BeforeValidator(upper)]
Name = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100), BeforeValidator(trimmed)]
Label = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=150), BeforeValidator(trimmed)]
Country = Annotated[str, StringConstraints(strict=True, pattern=r'^[A-Z]{2}$'), BeforeValidator(upper)]
Currency = Annotated[str, StringConstraints(strict=True, pattern=r'^[A-Z]{3}$'), BeforeValidator(upper)]
Email = Annotated[EmailStr, BeforeValidator(lambda v: v.strip().lower() if isinstance(v, str) else v)]
Salary = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)]
EmploymentType = Literal['REGULAR', 'FIXED_TERM', 'INTERN']
Status = Literal['ACTIVE', 'ON_LEAVE', 'SUSPENDED']
WorkTime = Literal['FULL_TIME', 'PART_TIME']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)


class ReadRecord(Contract):
    id: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ReferenceCreate(Contract):
    code: Code
    name: Label
    is_active: StrictBool = True


class LegalEmployerCreate(ReferenceCreate):
    country_code: Country


class BusinessUnitCreate(ReferenceCreate):
    pass


class DepartmentCreate(ReferenceCreate):
    business_unit_id: UUID


class JobCreate(ReferenceCreate):
    description: Annotated[str, StringConstraints(strict=True, max_length=10000)] | None = None


class GradeCreate(JobCreate):
    pass


class LocationCreate(ReferenceCreate):
    country_code: Country
    city: Annotated[str, StringConstraints(strict=True, max_length=100)] | None = None
    address_line: Annotated[str, StringConstraints(strict=True, max_length=255)] | None = None


class PersonCreate(Contract):
    person_number: Code
    first_name: Name
    last_name: Name
    preferred_name: Name | None = None
    date_of_birth: Day | None = None
    personal_email: Email | None = None
    phone: Annotated[str, StringConstraints(strict=True, max_length=30)] | None = None
    is_active: StrictBool = True

    @field_validator('date_of_birth')
    @classmethod
    def not_future(cls, value):
        if value and value > date.today():
            raise ValueError('Date of birth cannot be in the future')
        return value


class PersonRead(PersonCreate, ReadRecord):
    pass


# PATCH contracts preserve omitted-vs-null semantics; merged records are revalidated.
def patch_contract(name, base, excluded=()):
    return create_model(name, __base__=Contract, **{
        key: (field.rebuild_annotation() | None, None)
        for key, field in base.model_fields.items() if key not in excluded
    })


PersonUpdate = patch_contract('PersonUpdate', PersonCreate, ('person_number',))
REFERENCE_SCHEMAS = {}
for _name, _create in [('LegalEmployer', LegalEmployerCreate), ('BusinessUnit', BusinessUnitCreate), ('Department', DepartmentCreate), ('Job', JobCreate), ('Grade', GradeCreate), ('Location', LocationCreate)]:
    _read = create_model(_name + 'Read', __base__=(_create, ReadRecord))
    _update = patch_contract(_name + 'Update', _create)
    globals()[_name + 'Read'] = _read
    globals()[_name + 'Update'] = _update
    REFERENCE_SCHEMAS[_name] = (_create, _read, _update)


class WorkRelationshipCreate(Contract):
    person_id: UUID
    legal_employer_id: UUID
    employment_type: EmploymentType
    start_date: Day
    end_date: Day | None = None

    @model_validator(mode='after')
    def dates(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError('End date precedes start date')
        return self


class WorkRelationshipRead(WorkRelationshipCreate, ReadRecord):
    termination_reason: str | None = None


class AssignmentCreate(Contract):
    work_relationship_id: UUID
    assignment_number: Code
    start_date: Day
    end_date: Day | None = None

    @model_validator(mode='after')
    def dates(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError('End date precedes start date')
        return self


class AssignmentRead(AssignmentCreate, ReadRecord):
    pass


class VersionDetails(Contract):
    business_unit_id: UUID
    department_id: UUID
    job_id: UUID
    grade_id: UUID | None = None
    location_id: UUID
    manager_assignment_id: UUID | None = None
    status: Status = 'ACTIVE'
    work_time_type: WorkTime


class AssignmentVersionCreate(VersionDetails):
    effective_from: Day


class AssignmentVersionRead(AssignmentVersionCreate, ReadRecord):
    assignment_id: UUID
    effective_to: Day | None


class AssignmentCompensationCreate(Contract):
    effective_from: Day
    annual_base_salary: Salary
    currency: Currency

    @field_validator('annual_base_salary', mode='before')
    @classmethod
    def exact_salary(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError('Supply salary as a decimal string or integer')
        return value


class AssignmentCompensationRead(AssignmentCompensationCreate, ReadRecord):
    assignment_id: UUID
    effective_to: Day | None


class EndRequest(Contract):
    end_date: Day
    reason: Annotated[str, StringConstraints(strict=True, max_length=255)] | None = None


class HireRequest(VersionDetails):
    person: PersonCreate | None = None
    person_id: UUID | None = None
    legal_employer_id: UUID
    employment_type: EmploymentType
    joining_date: Day
    end_date: Day | None = None
    assignment_number: Code
    annual_base_salary: Salary
    currency: Currency

    @model_validator(mode='after')
    def identity_and_dates(self):
        if (self.person is None) == (self.person_id is None):
            raise ValueError('Supply exactly one of person or person_id')
        if self.end_date and self.end_date < self.joining_date:
            raise ValueError('End date precedes joining date')
        return self

    _salary = field_validator('annual_base_salary', mode='before')(AssignmentCompensationCreate.exact_salary.__func__)


class RehireRequest(HireRequest):
    # The route supplies identity; clients cannot substitute another person.
    person: None = None
    person_id: None = None

    @model_validator(mode='after')
    def identity_and_dates(self):
        if self.end_date and self.end_date < self.joining_date:
            raise ValueError('End date precedes joining date')
        return self


class HireResult(Contract):
    person: PersonRead
    work_relationship: WorkRelationshipRead
    assignment: AssignmentRead
    version: AssignmentVersionRead
    compensation: AssignmentCompensationRead


class WorkerPlacement(Contract):
    work_relationship: WorkRelationshipRead
    relationship_status: Literal['UPCOMING', 'ACTIVE', 'ENDED']
    assignment: AssignmentRead
    version: AssignmentVersionRead | None
    compensation: AssignmentCompensationRead | None
    business_unit: BusinessUnitRead | None
    department: DepartmentRead | None
    job: JobRead | None
    grade: GradeRead | None
    location: LocationRead | None
    manager_assignment: AssignmentRead | None
    manager: PersonRead | None


class WorkerSummary(Contract):
    person: PersonRead
    as_of: Day
    placements: list[WorkerPlacement]

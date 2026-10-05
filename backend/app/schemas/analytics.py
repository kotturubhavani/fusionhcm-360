"""Controlled report and extract contracts; no query text accepted."""
from datetime import date,datetime
from decimal import Decimal,InvalidOperation
from typing import Literal
from uuid import UUID
from pydantic import Field,StrictBool,model_validator,AwareDatetime
from app.schemas.core_hr import Contract,ReadRecord,Code,Label,Day
from app.services.analytics.metadata import DOMAINS,OPERATORS,EXTRACT_DOMAINS


def typed(value,kind):
    if not isinstance(value,str) or len(value)>255:raise ValueError('Filter values must be strings of at most 255 characters')
    if kind=='decimal':
        number=Decimal(value)
        if not number.is_finite():raise ValueError('Use a finite decimal')
        return number
    if kind=='integer':return int(value)
    if kind=='date':
        parsed=date.fromisoformat(value)
        if parsed.isoformat()!=value:raise ValueError('Use YYYY-MM-DD')
        return parsed
    if kind=='datetime':
        parsed=datetime.fromisoformat(value)
        if parsed.tzinfo is None:raise ValueError('Include a timezone')
        return parsed
    return value


class Filter(Contract):
    field:str=Field(max_length=50)
    operator:str=Field(max_length=30)
    value:str|list[str]


class Sort(Contract):
    field:str=Field(max_length=50)
    direction:Literal['asc','desc']='asc'


def validate_scope(domain,columns,filters,sorts):
    fields=DOMAINS[domain]
    if not columns or len(columns)!=len(set(columns)) or any(c not in fields for c in columns):raise ValueError('Select unique allowed columns')
    if len({s.field for s in sorts})!=len(sorts) or any(s.field not in fields for s in sorts):raise ValueError('Invalid or duplicate sort fields')
    for f in filters:
        if f.field not in fields or f.operator not in OPERATORS[fields[f.field]]:raise ValueError('Invalid field or operator')
        values=f.value if isinstance(f.value,list) else [f.value]
        if (f.operator=='in')!=isinstance(f.value,list) or not 1<=len(values)<=100:raise ValueError('IN requires 1 to 100 values; other operators require a single value')
        try:
            for value in values:typed(value,fields[f.field])
        except (ValueError,InvalidOperation):raise ValueError('Invalid typed filter value') from None


Domain=Literal['CORE_HR_WORKERS','PAYROLL_RESULTS','FBP_ALLOCATIONS','IMPORT_HISTORY']
ExtractType=Literal['WORKER_SNAPSHOT','WORKER_CHANGES','PAYROLL_RESULTS','FBP_ELECTIONS']
class ReportCreate(Contract):
    code:Code
    name:Label
    description:str|None=Field(default=None,max_length=2000)
    domain:Domain
    selected_columns:list[str]=Field(min_length=1,max_length=30)
    filters:list[Filter]=Field(default_factory=list,max_length=20)
    sort_definition:list[Sort]=Field(default_factory=list,max_length=5)
    is_active:StrictBool=True
    @model_validator(mode='after')
    def scope(self):
        validate_scope(self.domain,self.selected_columns,self.filters,self.sort_definition);return self
class ReportRead(ReportCreate,ReadRecord):
    created_by_user_id:UUID|None
class ReportRequest(Contract):
    as_of:Day=Field(default_factory=date.today)
class ReportRunRead(ReadRecord):
    report_definition_id:UUID
    status:str
    requested_by_user_id:UUID|None
    started_at:AwareDatetime
    completed_at:AwareDatetime|None
    row_count:int
    error_message:str|None
    definition_snapshot:dict
class ExtractConfig(Contract):
    filters:list[Filter]=Field(default_factory=list,max_length=20)
class ExtractCreate(Contract):
    code:Code
    name:Label
    extract_type:ExtractType
    output_format:Literal['CSV','JSON']='CSV'
    is_active:StrictBool=True
    configuration:ExtractConfig=Field(default_factory=ExtractConfig)
    @model_validator(mode='after')
    def scope(self):
        domain=EXTRACT_DOMAINS[self.extract_type]
        validate_scope(domain,list(DOMAINS[domain]),self.configuration.filters,[]);return self
class ExtractRead(ExtractCreate,ReadRecord):
    last_successful_run_at:AwareDatetime|None
class ExtractRequest(Contract):
    mode:Literal['FULL','INCREMENTAL']='FULL'
class ExtractRunRead(ReadRecord):
    extract_definition_id:UUID
    requested_by_user_id:UUID|None
    status:str
    mode:str
    watermark_from:AwareDatetime|None
    watermark_to:AwareDatetime
    started_at:AwareDatetime
    completed_at:AwareDatetime|None
    row_count:int
    output_filename:str|None
    error_message:str|None
    definition_snapshot:dict

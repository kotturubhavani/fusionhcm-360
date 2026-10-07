"""Controlled configuration; credential values are never API fields."""
from typing import Literal
from uuid import UUID
from pydantic import Field,StrictBool,AwareDatetime,model_validator
from app.schemas.core_hr import Contract,ReadRecord,Code,Label,Day
from app.services.integrations.security import endpoint
from app.services.core_hr.common import InvalidOperation

class Configuration(Contract):
    auth_type:Literal['NONE','BEARER_ENV']='NONE'
    credential_env_key:str|None=Field(default=None,pattern=r'^INTEGRATION_TOKEN_[A-Z0-9_]{1,64}$')
    as_of:Day|None=None
    legal_employer_code:Code|None=None
    business_unit_code:Code|None=None
    department_code:Code|None=None
    active_workers_only:StrictBool=True
    payroll_definition_code:Code|None=None
    period_name:str|None=Field(default=None,min_length=1,max_length=100)
    completed_run_number:int|None=Field(default=None,strict=True,ge=1)
    fbp_plan_code:Code|None=None

class DefinitionCreate(Contract):
    code:Code
    name:Label
    description:str|None=Field(default=None,max_length=2000)
    direction:Literal['INBOUND','OUTBOUND']
    integration_type:Literal['WORKER_EXPORT','PAYROLL_EXPORT','FBP_EXPORT','PERSON_UPDATE','ASSIGNMENT_CHANGE','COMPENSATION_CHANGE']
    transport_type:Literal['HTTP_REST','FILE']
    endpoint_url:str|None=Field(default=None,max_length=2000)
    http_method:Literal['POST']|None=None
    output_format:Literal['JSON','CSV']='JSON'
    configuration:Configuration=Field(default_factory=Configuration)
    is_active:StrictBool=True
    @model_validator(mode='after')
    def consistent(self):
        inbound=self.direction=='INBOUND';c=self.configuration
        if inbound!=(self.integration_type in ('PERSON_UPDATE','ASSIGNMENT_CHANGE','COMPENSATION_CHANGE')):raise ValueError('Direction and type do not match')
        http_out=not inbound and self.transport_type=='HTTP_REST'
        if http_out:
            if not self.endpoint_url or self.http_method!='POST' or self.output_format!='JSON':raise ValueError('Outbound REST requires URL, POST and JSON')
            try:endpoint(self.endpoint_url)
            except InvalidOperation as exc:raise ValueError(str(exc)) from None
        elif self.endpoint_url is not None or self.http_method is not None:raise ValueError('Only outbound REST accepts an endpoint/method')
        if inbound and c.auth_type!='BEARER_ENV':raise ValueError('Inbound requires BEARER_ENV authentication')
        if (c.auth_type=='BEARER_ENV')!=(c.credential_env_key is not None):raise ValueError('Select a credential reference only for BEARER_ENV')
        if not inbound and self.transport_type=='FILE' and c.auth_type!='NONE':raise ValueError('Outbound FILE does not use credentials')
        if inbound and self.output_format!=('CSV' if self.transport_type=='FILE' else 'JSON'):raise ValueError('Inbound FILE uses CSV; REST uses JSON')
        worker_fields=(c.as_of,c.legal_employer_code,c.business_unit_code,c.department_code)
        payroll_fields=(c.payroll_definition_code,c.period_name,c.completed_run_number)
        if self.integration_type!='WORKER_EXPORT' and any(x is not None for x in worker_fields):raise ValueError('Worker filters require WORKER_EXPORT')
        if self.integration_type!='PAYROLL_EXPORT' and any(x is not None for x in payroll_fields):raise ValueError('Payroll filters require PAYROLL_EXPORT')
        if self.integration_type!='FBP_EXPORT' and c.fbp_plan_code:raise ValueError('Plan filter requires FBP_EXPORT')
        if c.department_code and not c.business_unit_code:raise ValueError('Department filter requires a business unit')
        if c.completed_run_number and not (c.payroll_definition_code and c.period_name):raise ValueError('Run number requires payroll definition and period')
        return self
class DefinitionRead(DefinitionCreate,ReadRecord):
    @model_validator(mode="after")
    def consistent(self):
        # Persisted definitions remain readable after deployment security settings change.
        return self
    created_by_user_id:UUID|None
class RunRequest(Contract):
    request_key:str=Field(min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_.:-]+$')
    records:list[dict[str,str]]|None=Field(default=None,max_length=100)
    csv_content:str|None=Field(default=None,max_length=1000000)
class RunRead(ReadRecord):
    integration_definition_id:UUID
    requested_by_user_id:UUID|None
    retry_of_run_id:UUID|None
    retry_depth:int
    request_key:str
    status:str
    trigger_type:str
    started_at:AwareDatetime
    completed_at:AwareDatetime|None
    records_read:int
    records_succeeded:int
    records_failed:int
    definition_snapshot:dict
    request_metadata:dict|None
    response_metadata:dict|None
    output_filename:str|None
    safe_error_message:str|None
class ItemRead(ReadRecord):
    integration_run_id:UUID
    sequence_number:int
    delivery_key:str
    business_reference:str
    payload:dict
    status:str
    response_status:int|None
    safe_error_message:str|None

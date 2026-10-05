"""Allowlisted field metadata shared by report validation and UI."""
DOMAINS={
 'CORE_HR_WORKERS':dict(person_number='text',employee_name='text',assignment_number='text',legal_employer='text',business_unit='text',department='text',job='text',grade='text',location='text',employment_type='text',assignment_status='text',work_time_type='text',manager='text',annual_base_salary='decimal',currency='text',start_date='date',end_date='date'),
 'PAYROLL_RESULTS':dict(period='text',person_number='text',employee_name='text',assignment_number='text',gross_pay='decimal',total_deductions='decimal',net_pay='decimal',currency='text'),
 'FBP_ALLOCATIONS':dict(plan='text',person_number='text',employee_name='text',assignment_number='text',eligible_budget='decimal',elected_amount='decimal',remaining_amount='decimal',currency='text',status='text'),
 'IMPORT_HISTORY':dict(filename='text',object_type='text',status='text',total_rows='integer',valid_rows='integer',invalid_rows='integer',processed_rows='integer',failed_rows='integer',created_at='datetime'),
}
OPERATORS={'text':['equals','not_equals','contains','in'],'decimal':['equals','not_equals','in','greater_than','less_than'],'integer':['equals','not_equals','in','greater_than','less_than'],'date':['equals','not_equals','in','date_on_or_after','date_on_or_before'],'datetime':['equals','not_equals','in','date_on_or_after','date_on_or_before']}
EXTRACT_DOMAINS={'WORKER_SNAPSHOT':'CORE_HR_WORKERS','WORKER_CHANGES':'CORE_HR_WORKERS','PAYROLL_RESULTS':'PAYROLL_RESULTS','FBP_ELECTIONS':'FBP_ALLOCATIONS'}

def label(column):return column.replace('_',' ').title()
def metadata():
    return {domain:[{'key':key,'label':label(key),'type':kind,'operators':OPERATORS[kind]} for key,kind in fields.items()] for domain,fields in DOMAINS.items()}

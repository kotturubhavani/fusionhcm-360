"""Deterministic bounded planning; no model may select tools or change scope."""
import re
from .documents import safe_input,staff,AccessDenied,authorized
from .guardrails import normalize,unsafe

AGENTS={
 'HR_CORE_AGENT':{'search_workers','get_worker_summary','get_my_worker_summary'},
 'PAYROLL_AGENT':{'get_payroll_result','get_payroll_history','get_my_payroll','get_payroll_population'},
 'BENEFITS_AGENT':{'get_fbp_status','get_my_fbp','get_unsubmitted_benefits'},
 'DATA_IMPORT_AGENT':{'get_import_job_status'},
 'REPORTING_AGENT':{'get_report_run_status','get_extract_run_status'},
 'INTEGRATION_AGENT':{'get_integration_run_status'},
 'POLICY_AGENT':{'retrieve_policies'},
}

def agent_for(tool):
    for agent,allowed in AGENTS.items():
        if tool in allowed:return agent
    raise AccessDenied('Unsupported assistant tool.')

def plan(user,request):
    authorized(user);safe_input(request.message);q=normalize(request.message).strip()
    if not q:raise AccessDenied('Supply a specific HCM or policy question.')
    if unsafe(q):raise AccessDenied('This read-only assistant cannot expose secrets, internal prompts, execute commands or access arbitrary URLs.')
    is_staff=staff(user)
    if not is_staff and (request.person_number or request.reference_id or re.search(r"\b(other|another|everyone|colleague|coworker|someone else)\b|\bdemo360_[a-z0-9]+\b|\b\w+\s+\w+['\u2019]s\b",q)):
        raise AccessDenied('Employees can query only their own linked worker.')
    rag=bool(re.search(r'\b(policy|policies|handbook|guide|faq|remote|leave|vacation|transfer)\b',q)) or bool(request.source_id or request.document_id)
    selected=[];composition=None
    if request.tool:selected=[request.tool]
    else:
        comparison=bool(re.search(r'\b(?:which|list|show)\s+(?:employees|workers)\b',q) and re.search('payroll',q) and re.search(r'not submitted|unsubmitted',q) and re.search(r'benefits|fbp',q))
        if comparison:selected=['get_payroll_population','get_unsubmitted_benefits'];composition='PAYROLL_WITH_UNSUBMITTED_BENEFITS'
        else:
            operational=bool(re.search(r'\b(import|integration|extract|report)\b|\brow\s+\d+\b',q))
            for pattern,tool in [(r'\bimport\b|\brow\s+\d+\b','get_import_job_status'),(r'\bintegration\b','get_integration_run_status'),(r'\bextract\b','get_extract_run_status'),(r'\breport\b','get_report_run_status')]:
                if re.search(pattern,q) and not (tool=='get_extract_run_status' and 'integration' in q):selected.append(tool)
            if not operational:
                if re.search(r'\b(payroll|payslip|net|gross|deductions)\b',q):selected.append('get_payroll_history')
                if re.search(r'\b(fbp|benefits?)\b',q):selected.append('get_fbp_status')
                if re.search(r'\b(profile|employment|salary|assignment|assigned|location|department)\b',q):selected.append('get_worker_summary')
                elif not selected and re.search(r'\b(workers|employees|workforce)\b',q):selected.append('search_workers')
                elif not selected and (re.search(r'\bworker\b',q) or request.person_number):selected.append('get_worker_summary')
            if rag and not request.person_number and not re.search(r'\b(my|own|me|i|workers|employees|latest|current|currently)\b',q):selected=[]
    if not is_staff and selected:
        if not re.search(r'\b(my|own|me|i)\b',q):raise AccessDenied('Use a self-scoped question, such as "Show my latest payroll".')
        if request.tool and request.tool not in ('get_my_worker_summary','get_my_payroll','get_my_fbp'):raise AccessDenied('This tool requires HR or ADMIN.')
        selected=[{'get_worker_summary':'get_my_worker_summary','get_payroll_history':'get_my_payroll','get_fbp_status':'get_my_fbp'}.get(t,t) for t in selected]
        if any(t not in ('get_my_worker_summary','get_my_payroll','get_my_fbp') for t in selected):raise AccessDenied('This request requires HR or ADMIN.')
    if rag:selected.append('retrieve_policies')
    selected=list(dict.fromkeys(selected))
    if len(selected)>4:raise AccessDenied('Ask about at most four domain sources at once.')
    steps=[{'agent':agent_for(t),'tool':t} for t in selected]
    kind='HYBRID' if rag and len(selected)>1 else 'DOCUMENT_RAG' if rag else 'STRUCTURED_HCM_QUERY' if selected else 'GENERAL_CHAT'
    return {'query_type':kind,'steps':steps,'composition':composition,'orchestrator_route':'MULTI_AGENT' if len({s['agent'] for s in steps})>1 else 'SINGLE_AGENT' if steps else 'GENERAL_CHAT'}

def route(user,request):
    """Compatibility for callers that only need the primary intent."""
    result=plan(user,request)
    return result['query_type'],next((s['tool'] for s in result['steps'] if s['tool']!='retrieve_policies'),None)

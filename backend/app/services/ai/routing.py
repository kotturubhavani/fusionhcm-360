"""Deterministic intent selection; the model has no tool-calling capabilities."""
import re
from .documents import INJECTION,safe_input,staff,AccessDenied

def route(user,request):
    q=request.message.lower().strip();safe_input(q)
    if not q:raise ValueError('Empty query')
    if INJECTION.search(q) or re.search(r'\b(drop table|execute sql|delete from|read file|environment variable)\b|\bselect\s+\*',q):raise AccessDenied('This assistant supports read-only HCM questions and policy lookup.')
    rag=bool(re.search(r'\b(policy|policies|handbook|guide|faq|remote|leave|vacation|transfer)\b',q)) or bool(request.source_id or request.document_id)
    tool=request.tool
    if not tool:
        for pattern,name in [(r'\bimport\b|\brow \d+\b','get_import_job_status'),(r'\bintegration\b','get_integration_run_status'),(r'\bextract\b','get_extract_run_status'),(r'\breport\b','get_report_run_status'),(r'\bpayroll\b|\bpayslip\b|\bnet\b|\bgross\b','get_payroll_history'),(r'\bfbp\b|\bbenefits?\b','get_fbp_status'),(r'\bworkers\b|\bworkforce\b','search_workers'),(r'\bworker\b|\bprofile\b|\bemployment\b|\bsalary\b|\bassignment\b','get_worker_summary')]:
            if re.search(pattern,q):tool=name;break
        if rag and not request.person_number and not re.search(r'\b(my|own|workers|latest)\b',q):tool=None
    if not staff(user) and tool:
        if request.person_number or request.reference_id or re.search(r'\b(other|another|everyone|all workers|colleague|coworker)\b',q):raise AccessDenied('Employees can query only their own linked worker.')
        if not re.search(r'\b(my|own|me|i)\b',q):raise AccessDenied('Use a self-scoped question, such as "Show my latest payroll".')
        if request.tool and request.tool not in ('get_my_worker_summary','get_my_payroll','get_my_fbp'):raise AccessDenied('This tool requires HR or ADMIN.')
        tool={'get_worker_summary':'get_my_worker_summary','get_payroll_history':'get_my_payroll','get_fbp_status':'get_my_fbp'}.get(tool,tool)
    kind='HYBRID' if rag and tool else 'DOCUMENT_RAG' if rag else 'STRUCTURED_HCM_QUERY' if tool else 'GENERAL_CHAT'
    return kind,tool

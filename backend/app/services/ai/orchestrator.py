"""Bounded read-only orchestration with structured results and safe partial failure."""
import json
import time
from . import routing,tools,documents,providers
from app.services.core_hr.common import InvalidOperation,NotFound

LABELS={'HR_CORE_AGENT':'Core HR','PAYROLL_AGENT':'Payroll','BENEFITS_AGENT':'Benefits','DATA_IMPORT_AGENT':'Data imports','REPORTING_AGENT':'Reporting','INTEGRATION_AGENT':'Integrations','POLICY_AGENT':'Policies'}
EXPLANATIONS={
 'PAYROLL_AGENT':'Gross is earnings before deductions. Net is gross less the saved deduction lines. These are simulator calculations, not statutory payroll or tax advice.',
 'BENEFITS_AGENT':'Allocated is the sum of saved elections; remaining is the budget less allocated. OPEN budgets have not been submitted. This is a benefits-planning simulation, not benefits or tax advice.'}

def execute_agent(db,user,step,request):
    """Reject forged agent/tool pairings, even when called without the planner."""
    documents.authorized(user)
    if step.get('agent') not in routing.AGENTS or step.get('tool') not in routing.AGENTS[step['agent']]:raise documents.AccessDenied('Unsupported agent/tool pairing.')
    if step['tool']=='retrieve_policies':return documents.retrieve(db,user,request.message,request.source_id,request.document_id)
    return tools.execute(db,user,step['tool'],request)

def parameters(request):
    return {key:str(getattr(request,key)) for key in ('person_number','reference_id','row_number','as_of','source_id','document_id') if getattr(request,key) is not None}

def empty(data):
    return not data or any(key in data and not data[key] for key in ('results','budgets','workers','people'))

def run(db,user,request):
    plan=routing.plan(user,request)
    sections=[];trace=[];evidence=[]
    for step in plan['steps']:
        started=time.monotonic()
        section={**step,'label':LABELS[step['agent']],'status':'SUCCESS','data':{},'error':None,'explanation':EXPLANATIONS.get(step['agent'])}
        try:
            # Read wrappers may fail independently; a failed database statement
            # must not poison the remaining agents' transaction.
            with db.begin_nested():result=execute_agent(db,user,step,request)
            if step['tool']=='retrieve_policies':evidence=result;section['status']='SUCCESS' if result else 'EMPTY'
            else:
                if len(json.dumps(result,default=str))>24000:raise InvalidOperation('Narrow this query to one worker or run.')
                section['data']=result
                if empty(result):section['status']='EMPTY'
        except documents.AccessDenied:raise
        except (InvalidOperation,NotFound) as exc:section['status']='FAILED';section['error']=str(exc)
        except Exception:
            section['status']='FAILED';section['error']='This source is unavailable. Retry later or verify the source reference.'
        section['duration_ms']=max(0,round((time.monotonic()-started)*1000))
        trace.append({**step,'status':section['status'],'duration_ms':section['duration_ms'],'parameters':parameters(request)})
        sections.append(section)
    structured=[s for s in sections if s['data'] and s['status'] in ('SUCCESS','EMPTY')]
    data=structured[0]['data'] if len(structured)==1 else {s['tool']:s['data'] for s in structured}
    composition=None
    if plan['composition']:
        sources={s['tool']:s for s in sections}
        payroll=sources['get_payroll_population'];benefits=sources['get_unsubmitted_benefits']
        if all(s['status'] in ('SUCCESS','EMPTY') for s in (payroll,benefits)):
            people=set(payroll['data']['people'])
            matches=[b for b in benefits['data']['budgets'] if b['person_number'] in people]
            composition={'type':plan['composition'],'matches':matches,'as_of':benefits['data']['as_of'],'scope':'People with any completed payroll result and an OPEN benefits budget for the as-of plan year.'}
    selected=[];provider_error=None
    try:
        context=data if len(json.dumps(data,default=str))<=24000 else {'source_labels':[s['label'] for s in structured],'note':'Detailed values remain in the structured response.'}
        selection=providers.provider().select(request.message,[{'id':e['id'],'text':e['text']} for e in evidence],context)
        by_id={e['id']:e for e in evidence}
        if len(selection.selected_ids)!=len(set(selection.selected_ids)) or any(i not in by_id for i in selection.selected_ids):raise providers.ProviderError('Invalid references')
        selected=[by_id[i] for i in selection.selected_ids]
    except Exception:
        provider_error='Evidence selection failed or timed out. Verified structured records are retained where available.'
        for section in sections:
            if section['agent']=='POLICY_AGENT':section['status']='FAILED';section['error']='Policy evidence selection is unavailable.'
    for section in sections:
        if section['agent']=='POLICY_AGENT' and section['status']=='SUCCESS' and not selected:section['status']='EMPTY'
    # Traces describe execution outcomes, never model reasoning or source content.
    for t,s in zip(trace,sections):t['status']=s['status']
    useful=any(s['status']=='SUCCESS' and s['agent']!='POLICY_AGENT' for s in sections) or bool(selected)
    failed=any(s['status']=='FAILED' for s in sections) or provider_error is not None
    missing=any(s['status']=='EMPTY' for s in sections)
    status='PARTIAL' if useful and (failed or missing) else 'FAILED' if failed else 'SUCCESS'
    if plan['query_type']=='GENERAL_CHAT' and not provider_error:
        answer='I can read authorized worker, payroll and benefits records, explain import errors, inspect run statuses and retrieve policy excerpts. Include a worker or job reference where needed.'
    elif useful:answer='Here are the authorized source records and policy evidence.'
    else:answer='I could not find supporting evidence for that question. Check the worker, job/run reference or policy filters.'
    if status=='PARTIAL':answer+=' Some sources could not provide an answer; their status is shown below.'
    if status=='FAILED':answer='The requested sources could not complete this question. Check source references and retry.'
    for agent in dict.fromkeys(s['agent'] for s in sections):
        if agent in EXPLANATIONS:answer+='\n\n'+EXPLANATIONS[agent]
    return {'status':status,'error':provider_error if status in ('FAILED','PARTIAL') else None,'query_type':plan['query_type'],'tool':next((s['tool'] for s in sections if s['tool']!='retrieve_policies'),None),
        'orchestrator_route':plan['orchestrator_route'],'selected_agents':list(dict.fromkeys(s['agent'] for s in sections)),'sections':sections,'agent_trace':trace,
        'structured_data':data,'composition':composition,'citations':selected,'answer':answer}

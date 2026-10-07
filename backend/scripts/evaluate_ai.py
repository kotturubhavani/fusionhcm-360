"""Run synthetic read-only evaluations and write a local summary artifact."""
import argparse,json,sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime,UTC
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select,text
from app import models as m
from app.core.database import SessionLocal
from app.core.config import PROJECT_ROOT
from evals.runner import evaluate

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hr-email',required=True);parser.add_argument('--employee-email',required=True)
    args=parser.parse_args()
    with SessionLocal() as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        actors={role:db.scalar(select(m.User).where(m.User.email==email)) for role,email in [('HR',args.hr_email),('EMPLOYEE',args.employee_email)]}
        if any(user is None for user in actors.values()):raise SystemExit('Both existing QA actors are required.')
        report=evaluate(db,actors);db.rollback()
    report['created_at']=datetime.now(UTC).isoformat()
    root=PROJECT_ROOT/'local-data'/'evals';root.mkdir(parents=True,exist_ok=True)
    output=root/(str(uuid4())+'.json');output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'total':report['case_count'],'metrics':report['metrics'],'report':str(output)},indent=2))
    if report['passed']!=report['case_count']:raise SystemExit(1)

"""Explicit policy indexing with an existing active HR/ADMIN account."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app import models as m
from app.core.database import SessionLocal
from app.services.ai.demo import seed
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor-email',required=True)
    args=parser.parse_args()
    with SessionLocal.begin() as db:
        user=db.scalar(select(m.User).where(m.User.email==args.actor_email))
        if not user:raise SystemExit('An existing HR/ADMIN actor is required.')
        rows=seed(db,user)
        statuses=[r.status for r in rows]
    print(f'Synthetic policies: {len(statuses)}; indexed: {statuses.count("INDEXED")}; failed: {statuses.count("FAILED")}.')
    if any(s!='INDEXED' for s in statuses):raise SystemExit(1)

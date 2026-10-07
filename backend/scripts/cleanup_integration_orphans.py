"""Remove old unreferenced local output; never delete referenced run artifacts."""
import argparse
import sys
from pathlib import Path
from datetime import datetime,UTC,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select,text
from app.core.database import SessionLocal
from app.core.config import settings
from app.models.integrations import IntegrationRun
from app.services.integrations.service import output_path
from app.services.core_hr.common import InvalidOperation


def cleanup(db,days):
    if days<1:raise ValueError('Use at least one day')
    db.execute(text('SELECT pg_advisory_xact_lock(360, 1)'))
    retained=set(db.scalars(select(IntegrationRun.output_filename).where(IntegrationRun.output_filename.is_not(None))))
    cutoff=(datetime.now(UTC)-timedelta(days=days)).timestamp();removed=0
    for candidate in settings.integration_output_dir.glob('*'):
        if candidate.is_symlink() or not candidate.is_file() or candidate.name in retained:continue
        try:path=output_path(candidate.name)
        except InvalidOperation:continue
        if path.stat().st_mtime<cutoff:path.unlink();removed+=1
    return removed

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--older-than-days',type=int,default=7);args=parser.parse_args()
    with SessionLocal.begin() as db:count=cleanup(db,args.older_than_days)
    print(f'Old unreferenced integration artifacts removed: {count}')

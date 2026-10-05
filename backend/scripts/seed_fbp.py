"""Run explicitly from backend/: python scripts/seed_fbp.py."""
import logging
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy.exc import SQLAlchemyError
from app.core.database import SessionLocal
from app.services.core_hr.common import HRError
from app.services.fbp.demo import seed_demo


def main():
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    try:
        with SessionLocal.begin() as db:result=seed_demo(db)
        logging.info('Synthetic FBP demo: %s; %s plans; no login accounts.', 'created' if result['created'] else 'already present',result['plans'])
    except HRError as exc:
        logging.error('%s',exc);return 1
    except SQLAlchemyError:
        logging.error('Benefits seed could not be saved; no changes committed.');return 1
    return 0


if __name__=='__main__':raise SystemExit(main())

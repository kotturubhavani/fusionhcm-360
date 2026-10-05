"""Run explicitly from backend/: python scripts/seed_core_hr.py."""
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.exc import SQLAlchemyError
from app.core.database import SessionLocal
from app.services.core_hr.demo import seed_demo
from app.services.core_hr.common import HRError


def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        with SessionLocal() as db:
            result = seed_demo(db)
            db.commit()
        logging.info('Synthetic Core HR demo: %s; %s persons; no login accounts.', 'created' if result['created'] else 'already present', result['persons'])
    except HRError as exc:
        logging.error('%s', exc)
        return 1
    except SQLAlchemyError:
        logging.error('Synthetic seed could not be saved; no changes were committed.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

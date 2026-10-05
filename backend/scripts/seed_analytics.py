"""Run explicitly from backend: python scripts/seed_analytics.py."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.database import SessionLocal
from app.services.analytics.demo import seed
if __name__=='__main__':
    with SessionLocal.begin() as db:
        count=seed(db)
    print(f'Synthetic report/extract definitions created: {count}. No jobs executed.')

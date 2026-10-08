"""Explicit synthetic Integration Center definitions."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.database import SessionLocal
from app.services.integrations.seed import seed
if __name__=='__main__':
    with SessionLocal.begin() as db:count=seed(db)
    print(f'Synthetic integration definitions created: {count}; no runs executed.')

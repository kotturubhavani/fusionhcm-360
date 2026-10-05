# FusionHCM 360

A full-stack simulation of an Enterprise Human Capital Management platform, built as a portfolio project using a production-oriented architecture.

> **Independent project.** FusionHCM 360 is not affiliated with, endorsed by, or derived from Oracle Corporation or Oracle Fusion HCM. All HCM concepts are independently simulated. All data is entirely synthetic.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite 8, Tailwind CSS v4 |
| Backend | Python 3.11, FastAPI, Uvicorn |
| ORM | SQLAlchemy 2 |
| Database driver | psycopg 3 |
| Config | Pydantic Settings |
| Database | PostgreSQL 17 |
| Container | Docker Compose |

---

## What's working

- FastAPI backend with live PostgreSQL connectivity
- CORS configured for local development
- React frontend that verifies backend reachability on load
- Health endpoints at `/health` and `/health/database`
- Containerised PostgreSQL with Docker healthcheck

---

## Repository structure

```
fusionhcm-360/
├── architecture/
├── backend/
│   ├── app/
│   │   ├── api/health.py
│   │   ├── core/config.py
│   │   ├── core/database.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   └── requirements.txt
├── database/
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── index.css
│   │   └── main.tsx
│   └── vite.config.ts
├── policies/
├── synthetic-data/
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 20+ and npm
- Docker Desktop

### Environment

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD and DATABASE_URL in .env

cp .env.example frontend/.env.local
# Keep only VITE_API_BASE_URL in frontend/.env.local
```

Both files are git-ignored.

### PostgreSQL

```bash
docker compose up -d
```

### Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## URLs

| | |
|---|---|
| Frontend | http://localhost:5173 |
| Backend | http://127.0.0.1:8000 |
| Swagger UI | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |

---

## API

| Endpoint | Description |
|---|---|
| `GET /` | API root |
| `GET /health` | Service health |
| `GET /health/database` | Live database connectivity check |

---

## Planned capabilities

- Core HR — employee records, departments, positions
- Authentication — JWT, roles, permissions
- Payroll simulation
- Benefits administration
- Analytics and reporting

---

## Data

All data in this project is synthetic. No real employee records or personal information are used or stored.

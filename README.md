# FusionHCM 360

A portfolio simulation of an Enterprise Human Capital Management platform.

> **Independent project.** FusionHCM 360 is not affiliated with, endorsed by, or derived from Oracle Corporation or Oracle Fusion HCM. HCM concepts are independently simulated. Use synthetic data only.

## Current milestone

Backend and frontend authentication are implemented. Core HR and other business modules are not implemented yet.

- FastAPI, SQLAlchemy, PostgreSQL 17, Alembic, Argon2 password hashing, and JWT authentication.
- Registration assigns EMPLOYEE; HR and ADMIN are seeded roles. Role assignment is not accepted from registration requests.
- React 19, TypeScript, Vite 8, and Tailwind CSS v4 login and account screen.
- Access tokens stay in memory. Refresh tokens use an HttpOnly cookie scoped to `/auth`; fetch requests include credentials.
- Login loads `/auth/me`. Reload restores the session through refresh. An access-token 401 triggers one refresh and retry; visible signed-in tabs check the session every minute and on focus.
- Logout clears the in-memory session and requests cookie deletion. Failed server logout offers a retry.
- RBAC dependencies use explicit allowlists: EMPLOYEE only, HR or ADMIN, and ADMIN only. Temporary RBAC demonstration routes have been removed.
- Health endpoints and Docker PostgreSQL health checks remain available.

Refresh-token rotation and server-side token revocation are not implemented. Logout deletes the browser cookie; previously issued JWTs retain their normal validity. There is no frontend registration page or role dashboard.

## Repository structure

```text
backend/
  app/api/                 # Auth dependencies, auth and health routes
  app/core/                # Settings, database, password hashing and JWTs
  app/models/              # User, Role, UserRole
  app/schemas/             # Request and response validation
  app/services/            # Authentication service
  alembic/                 # Schema migrations
  scripts/seed_roles.py    # Idempotent role seeding; creates no users
  requirements.txt
frontend/
  src/App.tsx              # Login and authenticated account screen
  src/auth.ts              # Fetch client and in-memory token lifecycle
  src/auth.test.mjs        # Isolated auth regression tests (mocked fetch)
  .env.example             # Public frontend configuration only
database/
policies/
synthetic-data/
docker-compose.yml
.env.example
```

## Local setup

Prerequisites: Python 3.11+, Node.js 24 LTS (also used for the native TypeScript test runner), npm, and Docker Desktop.

From the project root, copy `.env.example` to `.env`. Set `POSTGRES_PASSWORD`, the matching `DATABASE_URL`, and a random `JWT_SECRET_KEY`; do not use the `change_me` placeholders. Generate a JWT secret with `python -c "import secrets; print(secrets.token_hex(32))"`.

Copy **`frontend/.env.example`** to `frontend/.env.local`. Do not copy database credentials or JWT secrets into the frontend. Any `VITE_` variable is public client configuration. Both local environment files are git-ignored and must never be force-added.

Use `http://localhost:5173` for the frontend and `http://localhost:8000` for `VITE_API_BASE_URL`. Keep the hostnames consistent for SameSite cookies. The backend allows the frontend origin with credentials. `REFRESH_COOKIE_SECURE=False` in the example is for local HTTP only; use Secure cookies with HTTPS outside local development. If an older local session left a duplicate `refresh_token` cookie at `/`, clear that stale cookie; the current cookie path is `/auth`.

Start PostgreSQL from the root:

```bash
docker compose up -d
```

Set up the backend:

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux instead: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python scripts/seed_roles.py
uvicorn app.main:app --reload
```

The current migration head is `87ec97bdf444`. Seeding creates EMPLOYEE, HR, and ADMIN only. No default account or development administrator is created. For local sign-in, register a synthetic account through `POST /auth/register` in Swagger UI, then use it on the frontend.

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

## URLs and API

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

| Endpoint | Purpose |
|---|---|
| `GET /` | API identity |
| `GET /health` | Service health |
| `GET /health/database` | Database connectivity |
| `POST /auth/register` | Register an EMPLOYEE using email, password, first_name, last_name |
| `POST /auth/login` | JSON email/password; access token response and HttpOnly refresh cookie |
| `POST /auth/refresh` | Refresh-cookie authentication; returns an access token |
| `GET /auth/me` | Current user; requires `Authorization: Bearer <access_token>` |
| `POST /auth/logout` | Delete the refresh cookie |

Login accepts JSON, not an OAuth2 password-form body. For manual API testing, obtain the bearer token with `/auth/login`.

## Verification

From `frontend/`:

```bash
npm test
npm run lint
npm run build
```

The five frontend regression tests cover login and user loading, access-token expiry recovery, invalid credentials, refresh failure, concurrent restoration, and local token cleanup on failed logout. They do not contact the database.

From `backend/`:

```bash
python -c "from app.main import app; from app.models import User, Role, UserRole; from app.services import auth; print('Backend imports OK')"
python -m pip check
alembic current
alembic check
```

There is currently no retained backend pytest suite. The disposable live-database verification scripts were removed after the auth milestone checks. The existing Starlette/httpx TestClient deprecation warning does not require a dependency change for this milestone.

Build output, virtual environments, dependency directories, Python caches, coverage, and local environment files are ignored. Only source, configuration examples, migrations, and reusable tests belong in a commit.

## Planned capabilities

Core HR, payroll simulation, benefits administration, analytics, and reporting remain future work. No real employee records or personal information should be used.

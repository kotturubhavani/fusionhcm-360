# FusionHCM 360

A portfolio simulation of an Enterprise Human Capital Management platform.

> **Independent project.** FusionHCM 360 is not affiliated with, endorsed by, or derived from Oracle Corporation or Oracle Fusion HCM. HCM concepts are independently simulated. Use synthetic data only.

## Current milestone

Authentication and Core HR are implemented across the backend and frontend. HR and ADMIN have workforce management screens; employees have a linked self-service view. Payroll simulation is implemented; benefits remain future work.

- FastAPI, SQLAlchemy, PostgreSQL 17, Alembic, Argon2 password hashing, and JWT authentication.
- Registration assigns EMPLOYEE; HR and ADMIN are seeded roles. Role assignment is not accepted from registration requests.
- React 19, TypeScript, React Router, Vite 8, and Tailwind CSS v4 application shell and role-aware navigation.
- Access tokens stay in memory. Refresh tokens use an HttpOnly cookie scoped to `/auth`; fetch requests include credentials.
- Login loads `/auth/me`. Reload restores the session through refresh. An access-token 401 triggers one refresh and retry; visible signed-in tabs check the session every minute and on focus.
- Logout clears the in-memory session and requests cookie deletion. Failed server logout offers a retry.
- RBAC dependencies use explicit allowlists: EMPLOYEE only, HR or ADMIN, and ADMIN only. Temporary RBAC demonstration routes have been removed.
- Core HR supports reference data, person identity, hire/rehire, dated assignments, independent salary history, termination, and as-of worker views.
- HR and ADMIN manage workers; EMPLOYEE access is limited to the linked person.
- Health endpoints and Docker PostgreSQL health checks remain available.

Refresh-token rotation and server-side token revocation are not implemented. Logout deletes the browser cookie; previously issued JWTs retain their normal validity. There is no frontend registration page.

## Repository structure

```text
backend/
  app/api/                 # Auth, health, and authorized Core HR routes
  app/core/                # Settings, database, password hashing and JWTs
  app/models/              # Auth, reference, worker, assignment, and compensation models
  app/schemas/             # Request and response validation
  app/services/            # Authentication and transactional Core HR services
  alembic/                 # Schema migrations
  scripts/seed_roles.py    # Idempotent role seeding; creates no users
  requirements.txt
frontend/
  src/App.tsx              # Authentication, application shell and guarded routes
  src/auth.ts              # Fetch client and in-memory token lifecycle
  src/core-hr/             # Typed API client, workforce screens and workflow forms
  src/components/          # Shared UI and async loading
  src/*.test.*             # Auth and component regression tests
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

The current migration head is `9085d55b6f98`. `seed_roles.py` creates EMPLOYEE, HR, and ADMIN only. No default account or development administrator is created. For local sign-in, register a synthetic account through `POST /auth/register` in Swagger UI, then use it on the frontend.

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

## Core HR workspace

HR and ADMIN can browse and search workers, view dated employment details, hire and rehire, append assignment and compensation changes, terminate employment with confirmation, and maintain all six reference resources. Dashboard counts use all fetched pages. Directory filtering is client-side and intended for the small synthetic dataset.

Employees see only `/core-hr/me`; management routes redirect to self-service. Backend authorization remains authoritative. Manager personal details and legal employer labels unavailable in the self-service response are shown as unavailable rather than inferred. As-of views retain historical employment and salary values; current person and reference labels are not historically versioned.

Salary inputs remain decimal strings. Access tokens stay in memory, and all API requests use the shared fetch client with one refresh-and-retry on 401. Production hosting must serve `index.html` for frontend route paths. No default HR/ADMIN credentials are supplied; assign roles through a controlled local administrative process, and use only synthetic accounts.

## Core HR API and demo data

Run `python scripts/seed_core_hr.py` from `backend/` after migrations to load a reusable synthetic demo. It creates 10 people, two legal employers, organizational references, reporting lines, dated assignment/salary changes, termination, and rehire. The script is atomic and rerunnable, uses reserved `DEMO360_` identifiers, and creates no login accounts. It never runs on startup. Reruns preserve existing records and reject incomplete demo data instead of overwriting history.

| Routes under `/core-hr` | Capability |
|---|---|
| `GET/POST /reference/{resource}`, `GET/PATCH /reference/{resource}/{id}` | Legal employers, business units, departments, jobs, grades, locations; PATCH also activates/deactivates |
| `POST/GET /persons`, `GET/PATCH /persons/{id}` | Person creation, listing, and demographic/contact updates |
| `GET /persons/{id}/work-relationships` | Employment episodes |
| `POST /workers/hire`, `POST /workers/{id}/rehire` | Atomic employment, assignment, and compensation creation |
| `GET /workers`, `GET /workers/{id}?as_of=YYYY-MM-DD` | Worker views with all current placements |
| `POST /assignments/{id}/changes`, `POST /assignments/{id}/compensation` | Independent dated organization and salary changes |
| `POST /assignments/{id}/end`, `POST /work-relationships/{id}/terminate` | End assignment or employment and close history |
| `GET /me` | Current account's linked person; no caller-supplied identity |

Mutation and listing routes require HR or ADMIN. Employees can read only their own linked person/worker detail; manager personal data is excluded from self-service. Person, worker, and reference lists accept `offset` and `limit` (maximum 100); the per-person relationship endpoint returns all employment episodes.

Dated changes are complete snapshots appended after the latest start date, with inclusive end dates. Arbitrary historical corrections are not supported. Termination rejects future scheduled changes and unresolved manager links instead of deleting history. Submit salary as a decimal string, such as `"750000.00"`. A worker with no employment on the requested date returns an empty `placements` list. As-of dates select employment and compensation history; person and reference labels reflect their current values.

Core HR writes use transaction-scoped PostgreSQL advisory locking plus record locks, deliberately serializing mutations for this simulator. Services use savepoints; the API commits successful requests. All HR writes must use these services for cross-row rules to hold. No hard-delete routes are provided.

## Payroll simulation

Payroll is a synthetic portfolio simulation, not a statutory payroll or tax engine. It does not reproduce proprietary Oracle behavior or claim legal accuracy. HR/ADMIN can create payroll definitions and monthly periods, confirm processing, and review run history, earning/deduction lines and saved totals. Employees can view only their linked person's payroll history and result details. No money is transferred and no PDF or statutory filings are generated.

Each legal employer has at most one payroll definition. Definitions store currency, demo retirement and withholding rates, and a monthly standard allowance. Definitions and completed results have no update/delete API. Periods cover exactly one calendar month; payment dates cannot precede period end. One successful run is permitted per period. Failed attempts keep safe failure metadata, roll back all result rows and reopen the period for retry. Processing is synchronous and uses the same transaction-scoped lock as Core HR writes, suitable for this small simulator.

Calculation rules (`DEMO_MONTHLY_V1`):

- Base earnings sum annual salary for each payable day, then divide by `12 ? calendar days in month`. This handles mid-month joining, termination and salary changes. Inclusive dates apply.
- ACTIVE and ON_LEAVE assignment days with compensation are paid. SUSPENDED days and history gaps are unpaid. Relationships/assignments outside the period are excluded. Current person/reference active flags do not rewrite historical eligibility; employment dates and dated assignment status govern eligibility.
- Standard allowance is prorated by payable days. Demo retirement applies to rounded base earnings; demo withholding applies to rounded gross earnings. Defaults are 0.05 and 0.10 respectively, stored as decimal fractions. No foreign-exchange conversion is performed; mismatched currency fails the entire run.
- Earnings and each deduction use Decimal half-up rounding to two decimal places. Gross is the sum of earning lines; net is gross less deduction lines. Negative net after rounding fails safely. Concurrent assignments each produce their own result and allowance; there is no person-level cap.
- Results snapshot worker labels, source history IDs, salary segments and applied rules. Subsequent Core HR changes do not recalculate completed payroll. No retroactive adjustments, tax bands, statutory limits, payment execution or server-side cancellation are implemented.

Run the explicit seed from `backend/` after migrations and the Core HR seed:

```bash
python scripts/seed_payroll.py
```

It creates `DEMO360_PAYROLL` for `DEMO360_LE0`, completed July/August 2025 periods, and an open October 2026 period. The seed uses a INR 1,000 standard allowance and synthetic deductions, creates no accounts, never runs on startup, and preserves existing history on rerun. Incomplete or conflicting demo data is rejected rather than overwritten.

Routes under `/payroll`: `GET/POST /definitions`, `GET /definitions/{id}`, `GET/POST /periods`, `GET /periods/{id}`, `POST /periods/{id}/process`, `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/results`, `GET /results/{id}`, and self-service `GET /me`, `GET /me/{id}`. Lists use offset/limit pagination; decimal amounts/rates are JSON strings. Processing returns the saved run with COMPLETED or FAILED status; duplicate processing returns 409. Management reads require HR/ADMIN; self-service ownership is enforced by the backend.

## Verification

From `frontend/`:

```bash
npm test
npm run lint
npm run build
```

Frontend tests use mocked fetch and React Testing Library to cover authentication restoration, refresh/retry, logout, role guards, worker views, workflow payloads, decimal salary handling, reference updates and pagination. They do not contact the database.

From `backend/`:

```bash
python -c "from app.main import app; from app.models import User, Role, UserRole; from app.services import auth; print('Backend imports OK')"
python -m pip check
alembic current
alembic check
```

Run `python -m pytest -q -W error tests` from `backend/` against the migrated local PostgreSQL database. Tests roll back their fixture data. The known upstream Starlette/httpx TestClient import deprecation is narrowly filtered in the API tests; other warnings are errors.

Build output, virtual environments, dependency directories, Python caches, coverage, and local environment files are ignored. Only source, configuration examples, migrations, and reusable tests belong in a commit.

## Planned capabilities

Benefits administration, analytics, and reporting remain future work. No real employee records or personal information should be used.

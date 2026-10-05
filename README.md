# FusionHCM 360

A portfolio simulation of an Enterprise Human Capital Management platform.

> **Independent project.** FusionHCM 360 is not affiliated with, endorsed by, or derived from Oracle Corporation or Oracle Fusion HCM. HCM concepts are independently simulated. Use synthetic data only.

## Current milestone

Authentication and Core HR are implemented across the backend and frontend. HR and ADMIN have workforce management screens; employees have a linked self-service view. Payroll and annual flexible-benefits planning simulations are implemented, including employee allocations and HR oversight.

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
  app/api/                 # Auth, health, Core HR, payroll and benefits routes
  app/core/                # Settings, database, password hashing and JWTs
  app/models/              # Auth, Core HR, payroll and benefits models
  app/schemas/             # Request and response validation
  app/services/            # Authentication and transactional domain services
  alembic/                 # Schema migrations
  scripts/seed_roles.py    # Idempotent role seeding; creates no users
  requirements.txt
frontend/
  src/App.tsx              # Authentication, application shell and guarded routes
  src/auth.ts              # Fetch client and in-memory token lifecycle
  src/core-hr/             # Typed API client, workforce screens and workflow forms
  src/payroll/             # Payroll simulation and employee results
  src/fbp/                 # Annual benefits plans and employee allocations
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

The current migration head is `57dcd64fceaa`. `seed_roles.py` creates EMPLOYEE, HR, and ADMIN only. No default account or development administrator is created. For local sign-in, register a synthetic account through `POST /auth/register` in Swagger UI, then use it on the frontend.

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

- Base earnings sum annual salary for each payable day, then divide by `12 * calendar days in month`. This handles mid-month joining, termination and salary changes. Inclusive dates apply.
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

## Flexible benefits planning (FBP)

FBP is an annual synthetic benefits-planning simulation, with no statutory, tax, payroll or proprietary Oracle treatment. HR/ADMIN create one plan per legal employer/year, configure components, open the plan, generate worker budgets and review allocations. Employees see only their linked person's eligible plans and allocation history.

The demo rule in `app/services/fbp/rules.py` defaults to **10% of annual base salary**, rounded half-up to two decimal places using Decimal. Salary is not CTC. Each plan stores its configurable rate; budget generation snapshots the source compensation, salary, rate, currency and worker labels once. Eligibility uses the January 1 plan start date: active person and legal employer, employment and assignment covering that date, ACTIVE assignment status, and positive compensation. Currency mismatches reject the whole operation. Each eligible assignment has its own budget; there is no person-level cap, proration or automatic midyear enrollment.

Plan settings/components can change only while DRAFT. Opening freezes them. Generation is atomic and idempotent. Include an active component with a zero minimum and a maximum large enough to accept each full budget, so exact allocation is possible. A component's default is a suggestion, not an automatic election. Zero opts out; positive amounts must meet that component's minimum/maximum. Drafts may be under-allocated but never over-allocated. Submission requires the exact budget and makes elections read-only. Closing requires all budgets submitted and finalizes them permanently; there is no reopen or hard-delete API. Plan status controls editing, without an automatic calendar cutoff.

The frontend provides plan creation, component management, worker totals/statuses, and My Benefits with draft/save/submit and finalized views. Money travels as decimal strings; display totals use integer cents and backend validation remains authoritative. Writes share the existing transaction lock, lock affected rows and check an expected revision to reject stale saves.

Run explicitly from `backend/` after migrations and the Core HR seed:

```bash
python scripts/seed_fbp.py
```

The rerunnable seed creates a closed 2025 plan and an open 2026 plan for `DEMO360_LE0`, four synthetic components per plan, eligible budgets, finalized historical elections and a mix of submitted/draft current elections. It creates no accounts, never runs on startup, preserves existing allocations and rejects incomplete/conflicting demo data.

Routes under `/fbp`: HR/ADMIN use `GET/POST /plans`, `GET/PATCH /plans/{id}`, `GET/POST /plans/{id}/components`, `PATCH /components/{id}`, `POST /plans/{id}/open`, `POST /plans/{id}/generate-budgets`, `POST /plans/{id}/close`, and `GET /plans/{id}/workers` or `/summary`. Self-service uses `GET /me`, `GET /me/{plan_id}`, `POST /me/{plan_id}/elections` and `POST /me/{plan_id}/submit`; ownership comes from the authenticated account. Plan, worker and self-service lists support offset/limit pagination.

## Enterprise HCM bulk imports

HR/ADMIN can upload and preview CSV files, inspect row errors, then explicitly process valid rows. This is our own bulk-import simulator format, with **no Oracle HDL compatibility**. Employees have no import access. Supported types are `WORKER_HIRE` (new people only), `PERSON_UPDATE`, `ASSIGNMENT_CHANGE` and `COMPENSATION_CHANGE`. Each job handles one type; rehire remains a separate Core HR workflow.

Download header-only templates from Data Imports or `GET /imports/templates/{object_type}`; `GET /imports/templates` describes required/optional columns. Use UTF-8 CSV, exact header names, YYYY-MM-DD dates and plain nonnegative decimal salaries with at most two decimal places. Codes/numbers resolve against existing records; department codes resolve within the specified business unit. One operation per target per file is allowed; rows cannot depend on other rows in the same file. Assignment changes are full snapshots. PERSON_UPDATE blanks leave fields unchanged; `<CLEAR>` clears optional person fields. No status/security fields can be imported into authentication.

Defaults are 5 MiB and 5,000 rows, configurable through `IMPORT_MAX_FILE_BYTES` (up to 20 MiB) and `IMPORT_MAX_ROWS` (up to 5,000). The entire multipart request is bounded to the file limit plus 64 KiB. Unknown/duplicate headers, invalid UTF-8, malformed quoting and incorrect field counts reject the upload. Parsed raw rows are retained as JSON; original files are not retained. Filenames are display labels only. Error CSV exports neutralize formula prefixes; uploaded values are never executed.

Validation runs the existing Core HR services inside rolled-back savepoints, so no Core HR changes persist. It stores normalized previews and safe row-level error codes. Processing rechecks current business rules, commits each successful operation with its row outcome, and isolates individual failures with savepoints. Invalid rows are skipped. The bounded synchronous job uses the shared domain transaction lock; successful rows and job results commit together at request completion. A fatal job failure rolls back that attempt and marks the job FAILED where the connection remains usable. A lost connection rolls back the transaction. There is no automatic retry or background queue; check history before submitting a new job after a network failure.

Completed jobs cannot be processed or validated again. Correct invalid/failed rows in a new file without repeating successful rows. No import-history deletion API is provided. Uploader IDs are recorded; deleting an account nulls that link while retaining import history. CSV record numbers count logical records (header is record 1), including quoted multiline fields.

Routes under `/imports`: `POST /` accepts multipart `object_type` and `file`; `GET /` lists jobs, `GET /{id}` shows metadata, `GET /{id}/rows` supports status filtering and pagination, `POST /{id}/validate` previews, `POST /{id}/process` applies valid rows, and `GET /{id}/errors.csv` downloads safe errors. These root routes are `/imports` without a trailing slash.

Reusable examples and execution order are documented in [`synthetic-data/imports/README.md`](synthetic-data/imports/README.md). They use only synthetic values, create distinct sample workers and never run automatically.

## Reports and extract simulator

HR/ADMIN can build saved reports using controlled columns, typed filters and sorting across Core HR workers, completed payroll results, FBP allocations and import history. There is no SQL editor or employee report-builder access. Core HR reports accept an as-of date and produce one row per assignment covering that date; people without a placement on that date are omitted. Person/reference labels reflect current values. FBP reports show one row per assignment budget. Payroll reports show detail rows, not cross-currency totals.

Filters are combined with AND. Operators are restricted by field type; IN uses an array, decimal values remain strings, dates use YYYY-MM-DD, and timestamps include a timezone. Null values do not match filters. Contains is case-insensitive; other text comparisons are exact. Sorting adds a stable record-ID tie-breaker (nulls last ascending, first descending). The UI supports one sort field; the API supports up to five. PATCH accepts the complete editable definition. Reports persist a bounded result snapshot and definition/as-of snapshot so pagination and exports remain consistent after later data changes. CSV and XLSX preserve selected column order and use readable headers. Amounts are exported as exact text, and spreadsheet formula prefixes are escaped. No PDF export is provided.

The separate outbound extract simulator supports WORKER_SNAPSHOT, WORKER_CHANGES, PAYROLL_RESULTS and FBP_ELECTIONS with CSV or JSON output. Worker snapshots use current placements; worker changes also include ended/future assignments using their end/start-date view and end_date. Changes are detected from person, relationship, assignment and salary/version histories plus included organization references. Submitted/finalized FBP output is one row per component election; payroll output includes completed result snapshots. Extract filters use the same controlled metadata.

FULL establishes a complete eligible baseline. INCREMENTAL uses **updated_at > last successful watermark and <= the upper watermark captured at run start**; its first run uses an unbounded lower watermark. Both modes advance the definition watermark only on success. Failed runs retain safe metadata and do not advance it. Scope/type changes after a successful run require a new definition. Files use run UUIDs in the controlled `local-data/extracts/` directory, excluded from Git, and downloads require HR/ADMIN authentication. `EXTRACT_OUTPUT_DIR` can configure local storage; clients cannot supply paths. No external delivery, scheduler, integration provider or automatic startup jobs are included.

This is application-timestamp extraction, **not CDC or Oracle HCM Extract compatibility**. It cannot recover intermediate changes or deleted records. Calendar-driven activation without a write does not produce a delta. Transactions whose application timestamp predates a watermark but commit afterward, direct database writes and out-of-band changes can be missed; use periodic FULL baselines. All application mutations and runs share the existing simulator lock. Generation is synchronous and bounded by `ANALYTICS_MAX_ROWS` (default 5,000; maximum 20,000 source/output rows). Reports retain snapshots; extract files require local retention management. There is no automatic deletion of audit history. A database commit failure after file creation can leave an unreferenced artifact; the cleanup script below handles these without touching referenced output.

Run explicitly from `backend/`:

```bash
python scripts/seed_analytics.py
python scripts/cleanup_extract_orphans.py --older-than-days 7
```

The idempotent seed adds three reports (Active Workforce by Department, Monthly Payroll Summary, FBP Allocation Status) and three extracts (Worker Full Snapshot, Worker Incremental Changes, Payroll Results Export). It preserves existing definitions and never runs them. Cleanup removes only unreferenced UUID-named output files older than the chosen threshold; completed referenced output is retained.

Report routes: `GET /reports/metadata`, `GET/POST /reports`, `GET/PATCH /reports/{id}`, `POST /reports/{id}/run`, `GET /reports/runs`, `GET /reports/runs/{id}`, `/results`, `/export.csv` and `/export.xlsx`. Extract routes: `GET/POST /extracts/definitions`, `GET/PATCH /extracts/definitions/{id}`, `POST /extracts/definitions/{id}/run`, `GET /extracts/runs`, `GET /extracts/runs/{id}` and `/download`. Lists/results are paginated. Repeated run requests create distinct audit runs; incremental repeats without changes produce empty output.

## Verification

From `frontend/`:

```bash
npm test
npm run lint
npm run build
```

Frontend tests use mocked fetch and React Testing Library to cover authentication restoration, refresh/retry, logout, role guards, worker views, workflow payloads, decimal salary handling, reference updates, payroll views, benefits workflows and pagination. They do not contact the database.

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

Benefits-provider integration, Integration Center and AI/RAG remain future work. No real employee records or personal information should be used.

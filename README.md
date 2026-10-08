# FusionHCM 360

FusionHCM 360 is an HCM simulator for managing synthetic workers, employment history, payroll, benefits and data exchange. It includes employee self-service and a read-only assistant for worker records and policies.

This is an independent project, not Oracle software or an Oracle-compatible implementation. All identities and employers are fictional; city names may be real. Use synthetic data only. Payroll and benefits calculations are illustrative rules, not statutory calculations, financial advice or payment instructions.

## Functional areas

| Area | Scope |
| --- | --- |
| Core HR | Organizations, people, work relationships, dated assignments, reporting lines and compensation history |
| Payroll | Monthly periods, processing, immutable results and employee result history |
| Benefits | Annual plans, assignment budgets, elections, submission and finalization |
| Imports | CSV upload, validation previews, row outcomes and explicit processing |
| Reports and extracts | Saved report definitions, CSV/XLSX exports, full and incremental file extracts |
| Integrations | Inbound changes, outbound file/HTTP delivery, item results and idempotent retries |
| AI assistant | Authorized record lookup, cited policy retrieval and deterministic routing across seven domains |

[Domain behavior and operational limits](docs/domain-reference.md) covers calculation rules, effective dates, transaction boundaries, API routes and failure handling. Interactive API documentation is available at `/docs` and `/redoc` when the backend is running.

## Architecture

The React application calls FastAPI through a shared fetch client. API dependencies enforce authentication and roles; domain services enforce ownership, business rules and transaction boundaries. SQLAlchemy stores records in PostgreSQL, and Alembic manages schema changes.

The assistant routes questions to allowlisted reads for Core HR, Payroll, Benefits, Imports, Reporting, Integrations and Policies. PostgreSQL authorizes document chunks before Qdrant retrieval. Gemini selects evidence; the application renders exact source values and citations. Agents cannot execute arbitrary SQL, URLs, code or record changes.

| Layer | Stack |
| --- | --- |
| Frontend | React, TypeScript, React Router, Vite, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Storage | PostgreSQL 17, Qdrant |
| Authentication | Argon2 passwords, JWT access/refresh tokens |
| Tests | pytest, React Testing Library, Vitest, Node test runner |

```text
backend/app/       API, schemas, models and domain services
backend/alembic/   Database migrations
backend/scripts/   Explicit seed, evaluation and artifact-cleanup commands
backend/tests/     PostgreSQL and provider-contract tests
backend/evals/     Deterministic synthetic evaluation cases
frontend/src/      Application screens, API clients and component tests
docs/              Domain rules and operational reference
synthetic-data/    Import examples and policy documents
```

## Local setup

Prerequisites: Python 3.11+, Node.js 24, npm and Docker. Commands below run from the repository root unless noted.

1. Copy `.env.example` to `.env`. Set the database password, matching `DATABASE_URL`, and a random `JWT_SECRET_KEY`. Generate a secret with `python -c "import secrets; print(secrets.token_hex(32))"`.
2. Copy `frontend/.env.example` to `frontend/.env.local`. Only public frontend configuration belongs there; `VITE_` values are exposed to the browser.
3. Start PostgreSQL and Qdrant:

```sh
docker compose up -d
```

Set up the backend:

```sh
cd backend
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` in PowerShell or `source .venv/bin/activate` on macOS/Linux, then run:

```sh
python -m pip install -r requirements.txt
python -m alembic upgrade head
python scripts/seed_roles.py
uvicorn app.main:app --reload
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`; the API runs at `http://localhost:8000`. Keep the frontend and API hostnames consistent for SameSite cookies. Local HTTP uses `REFRESH_COOKIE_SECURE=False`; HTTPS deployments require Secure cookies. Hosting must serve `index.html` for frontend routes. Environment files, generated files and dependency directories are ignored by Git.

## Authentication and roles

Registration through `POST /auth/register` creates an EMPLOYEE account. There is no registration screen, default password or seeded administrator. Assign HR/ADMIN roles and the optional employee-person link through a controlled local database administration process.

HR and ADMIN manage workforce records and operational workflows. EMPLOYEE can access only the linked person's employment, payroll and benefits records, plus shared policies. Backend checks enforce these boundaries independently of navigation or assistant routing.

Access tokens stay in memory. The browser holds the refresh token in an HttpOnly cookie scoped to `/auth`. Login loads `/auth/me`; reload restores the session through refresh. Requests retry once after an access-token 401. Logout clears local state and deletes the cookie. Refresh-token rotation and server-side revocation are not implemented, so issued JWTs retain their normal validity until expiry.

## Synthetic data

Run seeds explicitly from `backend/`, after migrations:

```sh
python scripts/seed_core_hr.py
python scripts/seed_payroll.py
python scripts/seed_fbp.py
python scripts/seed_analytics.py
python scripts/seed_integrations.py
```

The seeds use reserved `DEMO360_` identifiers and create no accounts. Reruns preserve existing records and reject incomplete or conflicting datasets. Nothing seeds on application startup. Core HR includes ten fictional workers, salary/assignment changes, termination and rehire. Payroll and benefits seeds include historical and open periods/plans; reports, extracts and integrations add reusable definitions.

[Import examples](synthetic-data/imports/README.md) use separate synthetic identities. They use this project's CSV format, not Oracle HDL.

## AI and policy retrieval

`AI_PROVIDER=mock` is the default for tests and evaluations. To use Gemini, set `AI_PROVIDER=gemini` in the backend environment and provide `GEMINI_API_KEY` through ignored `.env` or the process environment. The key is never sent to the frontend or included in model input.

Defaults are `gemini-3.5-flash-lite` for evidence selection and `gemini-embedding-001` with 768 dimensions for embeddings. Gemini is opt-in; errors do not silently fall back to mock. [Google's pricing and quotas](https://ai.google.dev/gemini-api/docs/pricing) apply, including free-tier limits and data-use terms. Use synthetic content only.

Index the five retained policies with an existing active HR/ADMIN account:

```sh
python scripts/seed_ai.py --actor-email admin.qa@fusionhcm.local
```

The example email identifies a locally provisioned QA account; the command does not create it. Staff can also upload and reindex documents in Policy Library. Switching embedding models or dimensions requires reindexing. Mock and Gemini vectors have separate Qdrant collections; PostgreSQL retains document identities, content and permissions.

The assistant is read-only, returns partial results when a source fails, and audits tool choices without storing model reasoning. Each question resolves its own context. Deterministic routing, independent tool authorization and constrained evidence selection supplement input screening; pattern matching is not a general injection-defense guarantee.

## Tests

Backend tests require migrated local PostgreSQL, Qdrant and the seeded synthetic data. The evaluation cases also require existing HR/ADMIN and EMPLOYEE QA accounts; the employee fixture links to `DEMO360_P02`. Tests roll back fixture writes, use isolated vector collections and mock hosted-provider requests. Real API calls are not required.

From `backend/`:

```sh
python -m pytest -q -W error
python -m pip check
python -m alembic current
python -m alembic check
python scripts/evaluate_ai.py --hr-email admin.qa@fusionhcm.local --employee-email employee.qa@fusionhcm.local
```

The existing narrow Starlette/httpx TestClient compatibility filter remains in place. Other warnings fail tests. The [57-case evaluation suite](backend/evals/README.md) checks routing, authorization, exact values, citations, refusals and injection attempts. Reports are written to ignored `local-data/evals/`.

From `frontend/`:

```sh
npm test
npm run lint
npm run build
```

The build includes TypeScript checks. Component and authentication tests use mocked requests.

## Operating limits

This is a local simulator. Domain writes share a transaction-scoped advisory lock; processing is synchronous and bounded. The local Qdrant endpoint binds to loopback and is not configured for public access. There are no automatic schedulers, bank payments or statutory filings.

Extracts and file integrations write to ignored `local-data/`. Explicit cleanup commands remove old unreferenced artifacts while preserving files linked to runs:

```sh
python scripts/cleanup_extract_orphans.py --older-than-days 7
python scripts/cleanup_integration_orphans.py --older-than-days 7
```

See the [operational reference](docs/domain-reference.md) for incremental-extract limitations, retry semantics, storage bounds and provider failure behavior.

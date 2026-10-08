# Domain behavior and operational limits

[Setup and tests](../README.md)

## Core HR workspace

HR and ADMIN can browse and search workers, view dated employment details, hire and rehire, append assignment and compensation changes, terminate employment with confirmation, and maintain all six reference resources. Dashboard counts use all fetched pages. Directory filtering is client-side and intended for the small synthetic dataset.

Employees see only `/core-hr/me`; management routes redirect to self-service. Backend authorization remains authoritative. Manager personal details and legal employer labels unavailable in the self-service response are shown as unavailable rather than inferred. As-of views retain historical employment and salary values; current person and reference labels are not historically versioned.

Salary inputs remain decimal strings. Access tokens stay in memory, and all API requests use the shared fetch client with one refresh-and-retry on 401. Production hosting must serve `index.html` for frontend route paths. No default HR/ADMIN credentials are supplied; assign roles through a controlled local administrative process, and use only synthetic accounts.

## Core HR API and demo data

Run `python scripts/seed_core_hr.py` from `backend/` after migrations to load a reusable synthetic demo. It creates 10 people, two legal employers, organizational references, reporting lines, dated assignment/salary changes, termination, and rehire. The script is atomic and rerunnable, uses reserved `DEMO360_` identifiers, and creates no login accounts. It never runs on startup. Reruns preserve existing records and reject incomplete demo data instead of overwriting history. Existing local seeds can be relabeled without resetting data: from `backend/`, preview with `python scripts/refresh_seed_labels.py`, then apply with `python scripts/refresh_seed_labels.py --apply --reindex-provider mock --actor-email admin.qa@fusionhcm.local`. If Gemini is used, repeat with `--reindex-provider gemini`. The command checks reserved identities, preserves IDs/history/amounts and backs up changed fields under ignored `local-data/`.

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

Payroll is a synthetic simulation, not a statutory payroll or tax engine. It does not reproduce proprietary Oracle behavior or claim legal accuracy. HR/ADMIN can create payroll definitions and monthly periods, confirm processing, and review run history, earning/deduction lines and saved totals. Employees can view only their linked person's payroll history and result details. No money is transferred and no PDF or statutory filings are generated.

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

It creates `DEMO360_PAYROLL` for `DEMO360_LE0`, completed July/August 2025 periods, and an open October 2026 period. The seed uses an INR 1,000 standard allowance and synthetic deductions, creates no accounts, never runs on startup, and preserves existing history on rerun. Incomplete or conflicting demo data is rejected rather than overwritten.

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

## Bulk imports

HR/ADMIN can upload and preview CSV files, inspect row errors, then explicitly process valid rows. This is our own bulk-import simulator format, with **no Oracle HDL compatibility**. Employees have no import access. Supported types are `WORKER_HIRE` (new people only), `PERSON_UPDATE`, `ASSIGNMENT_CHANGE` and `COMPENSATION_CHANGE`. Each job handles one type; rehire remains a separate Core HR workflow.

Download header-only templates from Data Imports or `GET /imports/templates/{object_type}`; `GET /imports/templates` describes required/optional columns. Use UTF-8 CSV, exact header names, YYYY-MM-DD dates and plain nonnegative decimal salaries with at most two decimal places. Codes/numbers resolve against existing records; department codes resolve within the specified business unit. One operation per target per file is allowed; rows cannot depend on other rows in the same file. Assignment changes are full snapshots. PERSON_UPDATE blanks leave fields unchanged; `<CLEAR>` clears optional person fields. No status/security fields can be imported into authentication.

Defaults are 5 MiB and 5,000 rows, configurable through `IMPORT_MAX_FILE_BYTES` (up to 20 MiB) and `IMPORT_MAX_ROWS` (up to 5,000). The entire multipart request is bounded to the file limit plus 64 KiB. Unknown/duplicate headers, invalid UTF-8, malformed quoting and incorrect field counts reject the upload. Parsed raw rows are retained as JSON; original files are not retained. Filenames are display labels only. Error CSV exports neutralize formula prefixes; uploaded values are never executed.

Validation runs the existing Core HR services inside rolled-back savepoints, so no Core HR changes persist. It stores normalized previews and safe row-level error codes. Processing rechecks current business rules, commits each successful operation with its row outcome, and isolates individual failures with savepoints. Invalid rows are skipped. The bounded synchronous job uses the shared domain transaction lock; successful rows and job results commit together at request completion. A fatal job failure rolls back that attempt and marks the job FAILED where the connection remains usable. A lost connection rolls back the transaction. There is no automatic retry or background queue; check history before submitting a new job after a network failure.

Completed jobs cannot be processed or validated again. Correct invalid/failed rows in a new file without repeating successful rows. No import-history deletion API is provided. Uploader IDs are recorded; deleting an account nulls that link while retaining import history. CSV record numbers count logical records (header is record 1), including quoted multiline fields.

Routes under `/imports`: `POST /` accepts multipart `object_type` and `file`; `GET /` lists jobs, `GET /{id}` shows metadata, `GET /{id}/rows` supports status filtering and pagination, `POST /{id}/validate` previews, `POST /{id}/process` applies valid rows, and `GET /{id}/errors.csv` downloads safe errors. These root routes are `/imports` without a trailing slash.

Reusable examples and execution order are documented in [`synthetic-data/imports/README.md`](../synthetic-data/imports/README.md). They use only synthetic values, create distinct sample workers and never run automatically.

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

The idempotent seed adds three reports (Active Workforce by Department, Monthly Payroll Results, Benefits Allocation Status) and three extracts (Worker Master Export, Worker Changes Export, Payroll Results Export). It preserves existing definitions and never runs them. Cleanup removes only unreferenced UUID-named output files older than the chosen threshold; completed referenced output is retained.

Report routes: `GET /reports/metadata`, `GET/POST /reports`, `GET/PATCH /reports/{id}`, `POST /reports/{id}/run`, `GET /reports/runs`, `GET /reports/runs/{id}`, `/results`, `/export.csv` and `/export.xlsx`. Extract routes: `GET/POST /extracts/definitions`, `GET/PATCH /extracts/definitions/{id}`, `POST /extracts/definitions/{id}/run`, `GET /extracts/runs`, `GET /extracts/runs/{id}` and `/download`. Lists/results are paginated. Repeated run requests create distinct audit runs; incremental repeats without changes produce empty output.

## Integrations

HR/ADMIN can configure inbound/outbound integrations, monitor item outcomes and download generated files. This independent simulator does not claim Oracle Fusion or Oracle Integration Cloud compatibility. Employees have no management or artifact access. Definitions can be edited or deactivated; direction and business type are fixed after creation. PATCH accepts the complete editable definition.

Outbound types are `WORKER_EXPORT`, `PAYROLL_EXPORT` and `FBP_EXPORT`, using local FILE (JSON/CSV) or HTTP_REST (POST JSON, one request per record). Workers use dated assignments and optional legal employer/business unit/department filters; current person/reference labels are used. Worker exports omit contact details and salary. Payroll exports use completed result snapshots and optional payroll code, period and run-number filters. FBP exports contain submitted/finalized assignment budgets and elected component totals. Amounts remain decimal strings. Business payloads use readable codes and person/assignment numbers.

Inbound types are `PERSON_UPDATE`, `ASSIGNMENT_CHANGE` and `COMPENSATION_CHANGE`. They reuse Data Imports columns, parsing and Core HR validation; REST takes `{"records":[{"person_number":"DEMO360_P02","preferred_name":"Nikhil"}]}` with string field values. FILE takes UTF-8 CSV. Assignment changes require a complete version; compensation history is separate. Each batch permits one operation per target. Successful changes and their item audit commit together; invalid items do not alter their target. Unknown fields reject the entire request before payload retention. Use synthetic data only.

Management uses normal HR/ADMIN JWTs. Partner calls use `POST /integrations/inbound/{code}`, `X-Integration-Key` and an `Idempotency-Key`; employee JWTs do not grant partner access. FILE partner calls use `Content-Type: text/csv`; REST uses JSON. Inbound definitions require BEARER_ENV metadata. Administrators supply only a credential **reference**, matching `INTEGRATION_TOKEN_[A-Z0-9_]{1,64}`, explicitly allowlisted in `INTEGRATION_CREDENTIAL_ENV_KEYS` (a JSON list). Set its value in the backend process environment, not in frontend variables or definition fields. Values are compared securely and never returned or retained with runs; missing values fail closed. Authentication headers and partner response bodies are not logged or stored.

HTTP destinations permit http/https without URL credentials, query strings or fragments. Private/loopback/link-local addresses are blocked, including DNS results; connections use the checked IP while HTTPS still verifies the original hostname. Redirects are not followed. `ALLOW_PRIVATE_INTEGRATION_TARGETS` defaults to False and should be enabled only in a local QA process for a local mock partner. Tests provide an isolated HTTP server fixture; there is no production mock route. Network operations use `INTEGRATION_HTTP_TIMEOUT_SECONDS` (default 5, maximum 15); DNS resolution follows the host OS resolver. A run stops starting new items after a 30-second delivery budget. Execution is synchronous under the shared simulator transaction lock, with at most `INTEGRATION_MAX_ITEMS` (default/maximum 100) and 1 MiB input. This is intended for small local demonstrations, not production throughput.

Every management run requires a client-generated `request_key`; reusing it for that definition returns 409. Partner Idempotency-Key supplies the same guard. History captures the definition snapshot, requester or API trigger, counts, safe metadata, timestamps and item outcomes. Manual retry creates a new run from **failed items only**, preserves each delivery Idempotency-Key and links its parent; only one direct retry and at most three retry levels are allowed. Business scope and transport must remain unchanged; the endpoint/credential reference can be repaired. Runs failing before item creation have no retryable items: inspect the cause and explicitly start a fresh run.

Delivery is **at least once**, not exactly once. HTTP delivery cannot be rolled back with PostgreSQL. A timeout or database/connection failure can leave delivery uncertain; inspect partner receipts before retrying or starting a new request. Partners must deduplicate delivery keys. Successful items are never copied into manual retries. No scheduler, infinite retry, payment instruction or automatic startup execution is included.

FILE output uses application-generated UUID filenames in `local-data/integrations/`, ignored by Git; `INTEGRATION_OUTPUT_DIR` can configure local storage. Authenticated downloads require HR/ADMIN. CSV formula prefixes are escaped. Audit rows have no hard-delete API. Local files require retention management; a failed database commit can leave an orphan file. Explicit commands from `backend/`:

```bash
python scripts/seed_integrations.py
python scripts/cleanup_integration_orphans.py --older-than-days 7
```

The rerunnable seed creates Worker Master Outbound, Payroll Results Outbound and Benefits Elections Outbound definitions only. It preserves existing definitions and creates no runs. Cleanup only removes old unreferenced UUID output, retaining referenced artifacts.

Management routes: `GET/POST /integrations`, `GET/PATCH /integrations/{id}`, `POST /integrations/{id}/run`, `GET /integrations/runs`, `GET /integrations/runs/{id}`, `/items`, `/download`, and `POST /integrations/runs/{id}/retry`. Definition/run lists use offset/limit pagination. The UI provides conditional configuration forms, explicit run confirmation, safe credential references, status/counts, item errors, downloads and confirmed retries. Management inbound runs accept `records` or `csv_content` together with `request_key`.

## AI assistant and policy library

The read-only assistant combines authorized HCM queries with retrieval over synthetic policies. HR/ADMIN can search active workers, look up a worker's employment/payroll/FBP records, explain import row errors and inspect report, extract or integration run status. Employees can query only their linked worker and shared policies. Tool authorization runs independently of both intent routing and the model. No SQL generation, record mutation or model-directed tool execution is available. This is not Oracle AI compatibility or production HR, legal, payroll or benefits advice.

The UI provides private conversation history, suggested questions, optional staff worker/job/run context, exact structured source values and expandable source excerpts. Policy Library is HR/ADMIN-only. Responses are non-streaming. Each turn resolves its own worker/job context and rechecks current permissions; previous answers are not passed back as authoritative context. Conversations are private even between administrators. Staff history is hidden after role downgrade, and self-service history is hidden after account/person relinking.

**Providers:** `AI_PROVIDER=mock` remains the default for deterministic tests and evaluations. It uses hashed term vectors and a small synonym map, not a learned semantic model. Set `AI_PROVIDER=gemini` in the backend process environment to enable Gemini without editing the local secret file. The only hosted adapter uses Google's official REST API through the existing HTTP client; no provider SDK is required. Defaults are `AI_MODEL=gemini-3.5-flash-lite`, `AI_EMBEDDING_MODEL=gemini-embedding-001` and `AI_EMBEDDING_DIMENSIONS=768`. Temperature, request timeout and maximum output tokens remain configurable. `GEMINI_API_KEY` is read from the backend process environment or ignored root `.env`, excluded from settings serialization and never sent to the frontend. Missing keys, quota limits and provider errors fail safely without falling back to mock.

The [stable Flash-Lite model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) supports structured output and a [free-tier development path](https://ai.google.dev/gemini-api/docs/pricing), subject to project access and changing quotas; free use is not unlimited. Free-tier inputs may be used to improve Google's products. Use synthetic data only. The adapter sends bounded authorized context to Gemini for evidence selection and policy text to the [embedding API](https://ai.google.dev/api/embeddings). It does not send chat history, credentials or arbitrary files as model input. Gemini may return only known evidence IDs; the application renders exact policy excerpts, Decimal strings and vetted explanations. This preserves the existing constrained answer composition instead of introducing unverified free-form financial statements. No model tools, search grounding, URL context or code execution are enabled.

Gemini retrieval uses query/document embedding task types, normalized 768-dimensional vectors, and a collection signature including model, dimensions and task version. Mock vectors remain in their own 256-dimensional collection. Reindexing preserves PostgreSQL document/chunk identities, checksums, content and ownership; only indexing timestamps/status, embedding references and audit records change. Chunk metadata tracks successfully indexed spaces so mock evaluations remain available independently of the hosted collection. Never copy vectors between model spaces. After switching a model or dimensionality, explicitly reindex retained documents through the staff policy library before use.

**Storage and retrieval:** PostgreSQL owns conversations, messages, query audits, document sources, documents and text chunks. A local [Qdrant](https://qdrant.tech/documentation/quickstart/) container stores cosine vectors and opaque chunk IDs only. It binds to loopback and uses a separate persistent volume, leaving the PostgreSQL image/volume unchanged. This unauthenticated loopback setup is for a trusted single-developer machine, not a public deployment. PostgreSQL authorizes the candidate chunk IDs before every Qdrant query: active/indexed documents, active source, ALL versus STAFF audience, optional source/document filters and matching embedding-provider signature. Results are rechecked against the authorized set. `AI_TOP_K` and `AI_MIN_SCORE` control retrieval; low-score or irrelevant results return a no-evidence fallback. Scores are similarity measures, not calibrated confidence.

Each provider/embedding model has a separate collection signature; changing providers/models requires explicit reindexing. Missing indexes return a safe error and can be rebuilt from retained text. PostgreSQL is authoritative across partial failures: vector points from a rolled-back upload are never eligible for retrieval. Reindexing upserts the same chunk IDs. No raw upload files are retained. The collection contains no policy text or employee records, and can be rebuilt by explicit reindexing; removing a collection does not remove source documents. At most 2,000 eligible chunks are searched per request; use a source/document filter for larger libraries.

**Ingestion:** Upload PDF, UTF-8 TXT or Markdown with an ALL or STAFF audience. Defaults are 2 MiB per file, 40,000 extracted characters and 30 PDF pages. PDF extraction runs in a time-limited child process; encrypted, scanned or unparseable PDFs are rejected with a safe message. There is no OCR, macro execution or user-supplied filesystem path. Normalized text is split into 900-character windows with 150-character overlap. Credential-shaped text and common instruction-injection patterns are rejected; retrieved text remains untrusted regardless of pattern matching. The model cannot request tools or influence scope, and excerpts render as plain text. HR must still review policies before publishing to the chosen audience.

Uploads are checksum-idempotent within a source. A failed index retains text with FAILED status for an explicit retry. Deactivation immediately removes a document from retrieval; activation requires reindexing. Historical messages retain the evidence snapshots shown at that time. No document/conversation hard-delete endpoint or automatic retention job is included. Do not upload real personal or proprietary documents.

API: `GET /ai/capabilities`, `POST /ai/chat`, `GET /ai/conversations`, `GET /ai/conversations/{id}`; HR/ADMIN use `GET/POST /ai/documents`, `GET/PATCH /ai/documents/{id}` and `POST /ai/documents/{id}/reindex`. Chat takes a UUID `request_key`, message and optional owned conversation, allowlisted tool, staff person number/job/run reference, row number, as-of date and document/source filters. Employee identifiers cannot broaden scope. Repeated request keys are rejected; after a network interruption, reload history before resending. Conversations are capped at 100 messages. Calls are bounded and synchronous under the existing simulator writer lock, suitable for local demonstrations rather than high-volume service.

AI tests use real local PostgreSQL and isolated Qdrant collections with deterministic providers, plus mocked Gemini HTTP contracts. Both containers must be running. They roll back database fixtures and remove test vector collections; no real API key is needed.

## Orchestration

A deterministic orchestrator selects up to four allowlisted sources across Core HR, Payroll, Benefits, Data Imports, Reporting, Integrations and Policies. Specialized agents use existing authorized read wrappers; the model cannot choose tools or perform writes. Cross-domain answers retain exact structured values, source sections and policy citations. The payroll/benefits comparison means people with any completed payroll result and an OPEN budget in the requested plan year, rather than an inferred eligibility decision. A failed source produces a partial answer when other verified evidence remains available.

Audit metadata records the route, selected agents, tool names, typed filters, outcomes, elapsed times and citation IDs. It contains no model reasoning or internal prompts. Prompt checks supplement independent tool authorization and constrained evidence selection; they are not a claim of universal injection detection. No autonomous HR decisions or startup evaluations are performed.

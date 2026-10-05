# Synthetic bulk import examples

These CSVs use the project's own format, not Oracle HDL. No real personal or employer data is included. Files are examples for explicit upload; nothing runs on startup.

First run the existing Core HR seed to provide `DEMO360_` reference codes. The examples create new `IMPORT_SAMPLE_` people/assignments; they do not modify seeded workers.

1. Upload `worker_hires.csv`, validate, inspect the preview, then process. It creates Robin Synthetic.
2. Optionally upload `worker_hires_mixed.csv`. Wren Synthetic is valid; the second row deliberately contains an invalid salary. Processing skips the invalid row.
3. After the first hire, `person_updates.csv`, `assignment_changes.csv` and `compensation_changes.csv` demonstrate independent changes to that sample worker. Assignment and compensation changes are effective 2026-02-01.

Do not reprocess these samples as new jobs once successful. Existing person/assignment numbers and duplicate history dates are intentionally rejected. Choose new synthetic numbers for another demonstration.

Templates are downloadable in Data Imports and through `/imports/templates/{object_type}`. Required fields are listed alongside the template. Optional hire fields include preferred name, birth date, personal email, phone, grade, manager and status (defaults to ACTIVE). PERSON_UPDATE requires person_number and at least one nonblank changed field; blank means unchanged, and `<CLEAR>` clears a nullable field. Assignment changes require the full organization/work-time snapshot, with optional grade/manager and default ACTIVE status.

Use UTF-8, exact headers, ISO dates and decimal salary text without commas or exponent notation. A manager must already exist and satisfy the normal dated reporting rules. Department codes belong to their business unit. Files cannot create reference data or authenticate users. Dry runs retain no worker changes; always inspect row outcomes before confirming processing.

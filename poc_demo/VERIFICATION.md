# Executed verification

Verified on 2026-10-23 against the existing development PostgreSQL 16 container and Demo Company `aef33b6b-773c-43cd-ab86-6f3882f2092a`.

## Environment and preservation

- Inspected the actual `data_source`, `ingestion_run`, `raw_artifact`, `company` and Alembic schemas before migration.
- The original database had four registered sources, 12 execution rows and eight artifact rows. All were retained.
- Saved a pre-migration database dump to `/tmp/invoice-finance-before-week1.sql` on the workstation.
- Applied `0002_acquisition_poc` after `0001_initial_schema` to the existing database; no database replacement or table reset.
- Preserved Demo Company. Final core counts are one company and zero rows in party, document, invoice, invoice_line, payment, payment_allocation and bank_transaction, matching the inspected development data.
- Existing invoice samples were mounted read-only into acquisition containers. Their originals were never changed.
- No development-company execution reset was run. Reset behavior was tested only with synthetic companies in an isolated test schema.
- No generated test schemas remained after the final test run.

## Build and automated tests

Built the shared Python 3.12 image:

```bash
docker build -t invoice-finance-week1 .
```

Executed the final suite using PostgreSQL in generated schemas within the existing development database:

```bash
docker run --rm --network invoice_finance_mvp_default --user 1000:1000 \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e TEST_DATABASE_URL=postgresql+psycopg://invoice_app:invoice_app@postgres:5432/invoice_finance \
  -v /home/elmehdi/Desktop/invoice_finance_mvp:/app -w /app \
  invoice-finance-week1 python -m pytest -q poc_demo/tests --tb=short
```

Actual result: **61 passed, 1 warning in 5.24 seconds**. The warning is Starlette's deprecated AnyIO BlockingPortal import; no tests were skipped in this run.

Coverage includes source registration/editing, upload names and company boundaries, all fixture formats, original byte integrity, duplicate prevention, external ID versions, ingestion history, failure/recovery, empty and duplicate collections, pagination and cycle detection, partial-page failure retention, HTTP destination restrictions, redirect rejection, response size limits, PostgreSQL source locking, reset scope, legacy/fresh migration paths, the original business read endpoints, and all five Streamlit pages. Streamlit AppTest creates a source through the UI and executes it through FastAPI with actual PostgreSQL results.

Also parsed 35 Python source files successfully and validated the Compose configuration with:

```bash
docker compose config --quiet
```

## Live end-to-end demonstration

Executed:

```bash
docker exec invoice-week1-backend python -m poc_demo.demo
```

Results are saved in [demo_results.json](demo_results.json), including actual run IDs and timestamps.

| Scenario | Executions | New artifacts | Duplicates | Result |
| --- | ---: | ---: | ---: | --- |
| All active sources | 22 | 37 | 17 | All SUCCEEDED |
| Immediate unchanged replay | 22 | 0 | 54 | All SUCCEEDED |
| Scenario source baseline | 1 | 4 | 0 | SUCCEEDED |
| New ERP record | 1 | 2 | 3 | New response + INV-1004 retained |
| Updated ERP record | 1 | 2 | 2 | New response + INV-1001 version retained |
| HTTP 500 | 1 | 0 | 0 | FAILED with recorded error |
| Recovery | 1 | 0 | 4 | SUCCEEDED |
| Pagination | 1 | 2 | 3 | Two response pages; records deduplicated |
| Duplicate records | 1 | 1 | 4 | New response only |
| Empty collection | 1 | 1 | 0 | Empty response envelope retained |
| HTTP 429 | 1 | 0 | 0 | FAILED with recorded error |
| Malformed JSON | 1 | 1 | 0 | Original response retained; parsing FAILED |
| Final recovery | 1 | 0 | 4 | SUCCEEDED |

Confirmed two distinct stored checksums for external ID INV-1001. Verified SHA-256 downloads for CSV, JSON, XML, PDF and PNG. Final overview: 23 active sources, 67 historical executions, 58 raw artifacts, 19 derived RECORD artifacts and 17 original RESPONSE artifacts. Four historical FAILED runs include one pre-existing failure and the three intentionally simulated failures. The scenario source was restored to normal success configuration.

The 37 new artifacts in the first run reflect existing deduplicated registry entries, repeated sample image bytes and the newly seeded sources. Acquired artifact counts include files, response envelopes and derived records; they are not invoice counts.

## Running services and limitations

HTTP health checks succeeded for FastAPI (`/health`), Streamlit (`/_stcore/health`) and the mock ERP endpoint. The services are available at ports 8000, 8501 and 9090 respectively, using the existing PostgreSQL container at 5432. See [README.md](README.md) for startup commands and the complete manual demonstration.

The legacy `docker-compose` command could not run because of the workstation's Python requests/Docker SDK conflict. Compose v2 configuration validated successfully; its full startup was not executed from this restricted session. The running demonstration used the documented direct Docker build/run commands instead.

There is no durable job queue, tenant authentication, OCR, normalization, reconciliation or external provider integration. Large-file and distributed operation are outside this POC. A backend interruption may leave RUNNING rows; no automatic reset is performed. The filesystem and PostgreSQL registry are separate transactions, so conservative orphan-file retention is possible.

This workspace does not contain usable Git metadata or a configured remote, so no pull request was created.

## Readable storage labels — 2026-10-24

Updated raw storage to group artifacts by company name, business entity (`invoices`, `payments`, `bank-transactions`), source name, format and artifact type (`original-files`, `api-responses`, `records`). Company/source labels retain UUID suffixes to prevent collisions. Legacy paths remain readable; duplicate replay retains registered locations even after a name changes.

Executed the expanded PostgreSQL-backed suite with the same Docker test command above: **71 passed, 1 warning in 5.52 seconds**. Added tests for safe labels, identical source names, renamed sources/companies, response/record grouping, legacy relocation, unchanged identities/bytes, corrupt-file handling and company/source path boundaries.

Saved a database backup at `/tmp/invoice-finance-before-storage-labels.sql`, then ran:

```bash
docker run --rm --network invoice_finance_mvp_default --user 1000:1000 \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e DATABASE_URL=postgresql+psycopg://invoice_app:invoice_app@postgres:5432/invoice_finance \
  -v /home/elmehdi/Desktop/invoice_finance_mvp:/app -w /app \
  invoice-finance-week1 python -m poc_demo.relabel_storage \
  --company-id aef33b6b-773c-43cd-ab86-6f3882f2092a
```

Actual outcome: **57 raw files moved**, no superseded copies retained. Verified all 57 files through the artifact service after relocation, including their registered SHA-256 hashes. All 58 artifact registry rows and the existing ingestion history were preserved. No schema change was needed; only `raw_artifact.storage_path` changed for relocated artifacts.

One artifact, `e3f42457-9675-49be-ad1f-f00ba420eee7`, already referenced an unavailable file before this change. Its original path and metadata were preserved, and the maintenance command reported it with a nonzero exit status rather than claiming it was moved. No replacement content was fabricated.

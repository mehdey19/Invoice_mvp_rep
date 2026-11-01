# Week 1 universal acquisition POC

This guide covers **Week 1 — Acquisition** in the existing Invoice Finance MVP. The same Acquisition Lab now exposes **Week 2 — Normalization**. See [the architecture guide](../docs/ARCHITECTURE.md) for the current module structure, database schemas and both stages.

The existing PostgreSQL database and Demo Company (`aef33b6b-773c-43cd-ab86-6f3882f2092a`) are reused. Acquisition writes process metadata in `integration_pipeline`, preserves raw files, and registers original content in `canonical.document`. Week 2 validates mapped records before writing canonical invoices, parties, lines, payments and bank transactions. Original public records are retained.

## Architecture and project structure

```mermaid
flowchart LR
    UI[Streamlit :8501] --> API[Existing FastAPI :8000 /poc]
    CLI[Seed and acquisition CLI] --> Services[Shared source and acquisition services]
    API --> Services
    DB[(Existing PostgreSQL)] --> Services
    Services --> Registry[Connector registry]
    Registry --> File[FILE]
    Registry --> Directory[DIRECTORY]
    Registry --> HTTP[HTTP_GET]
    HTTP --> Mock[Deterministic mock API :9090]
    File --> Store[Original bytes and SHA-256 storage]
    Directory --> Store
    HTTP --> Store
    Store --> Metadata[raw_artifact and ingestion_run]
    Metadata --> DB
    Store --> Interpret[Optional JSON record interpretation]
    Interpret --> Records[Derived record artifacts with external IDs]
    Records --> DB
    DB --> Future[Future normalization into existing business model]
```

```text
app/
  main.py                         existing API plus /poc router
  models/acquisition.py           DataSource, IngestionRun, RawArtifact
migrations/versions/
  0001_initial_schema.py          existing business schema
  0002_acquisition_poc.py         adopt and extend intermediary schema
poc_demo/
  main.py                         existing acquisition CLI
  universal_acquisition.py        compatibility entry point
  settings.py                     approved paths, origins and limits
  storage_layout.py               readable, company/source-scoped folder labels
  relabel_storage.py              verified relocation of existing raw artifacts
  interpretation.py               JSON validation and optional record splitting
  seed.py                         idempotent source and fixture initialization
  reset.py                        explicit seeded execution metadata reset
  demo.py                         repeatable HTTP demonstration
  demo_results.json               actual saved live demonstration results
  mock_api.py                     deterministic synthetic providers
  api.py                          source, execution, history and artifact endpoints
  dashboard.py                    five Streamlit pages
  connectors/                     shared interface and FILE/DIRECTORY/HTTP_GET registry
  services/                       source, acquisition, artifact and query services
  fixtures/
    generate.py                   deterministic synthetic fixture generation
    csv/                          French/English invoices, payments, bank transactions
    json/                         invoices and payments
    xml/invoice_sample.xml
    documents/invoice_sample.pdf
    images/synthetic.png          synthetic automated test image
    images/README.md
    uploads/                      generated names, scoped to company; ignored by git
    ...                           original POC fixtures retained
  sql/                            original POC SQL retained for legacy compatibility
  tests/                          connectors, acquisition, API, PostgreSQL, UI and E2E
requirements.txt
requirements-dev.txt
Dockerfile
docker-compose.yml
```

A **data source** is a PostgreSQL registration describing a company's source, transport, format, entity type, configuration and future field mappings. A **connector** implements transport only. A **raw artifact** is a stored original file/response or an explicitly marked derived API record. An **ingestion execution** records an attempt, its counts, timestamps and errors. A **normalized invoice** is a later business interpretation, not a response page. A **payment** is a business settlement event. A **bank transaction** is an account booking; it remains distinct from a payment until a later reconciliation stage.

## Database changes

`0002_acquisition_poc` follows the existing `0001_initial_schema` revision. It adopts the original three POC tables with `CREATE TABLE IF NOT EXISTS`, preserving existing rows, indexes and foreign keys. It creates them when absent. It expands the format constraint to CSV, JSON, XML, PDF, PNG, JPG/JPEG and the legacy IMAGE directory format.

| Table | Additions |
| --- | --- |
| `data_source` | `updated_at` |
| `ingestion_run` | `attempted_count`, `error_count`; backfill old execution counters |
| `raw_artifact` | `external_id`, `data_format`, `artifact_kind`, `acquisition_metadata`; index on source and external ID |

Historical `acquired_count` continues to mean **new artifacts**. `attempted_count` counts yielded original and derived artifacts, including duplicates. `duplicate_count` counts artifacts already registered for the same source and SHA-256. A run-level exception increments `error_count` and marks the run FAILED. Earlier artifacts in a failed run remain stored. Dates are timezone-aware; history date filters use UTC.

`artifact_kind` distinguishes FILE, RESPONSE and RECORD. HTTP JSON responses are stored byte-for-byte first. If `records_path` and `external_id_path` are configured, each record is also stored as canonical JSON with its external ID and parent response checksum. The record representation is explicitly identified in metadata; the original HTTP body remains available. Changing a record preserves another checksum/version under the same external ID. Response pages count as artifacts too, and are not presented as invoice counts.

The migration never resets core tables. Automatic downgrade is refused because these tables may predate Alembic and contain existing data. The old `sql/01_schema.sql` and `02_seed_sources.sql` are legacy definitions; use Alembic and `python -m poc_demo.seed` for this implementation.

## Startup with Docker Compose v2

From the project root:

```bash
docker compose up --build -d
```

This reuses the existing `postgres` service and `postgres_data` volume. Do not run `docker compose down -v`. The app applies additive migrations and idempotent seed registrations before starting. Images are mounted read-only. Set `POC_IMAGES_DIR` in the shell or a local `.env` if the existing sample directory is elsewhere; it must exist before Docker starts. Defaults point to `/home/elmehdi/Desktop/invoices/test_invoices`.

| Service | Address |
| --- | --- |
| Streamlit dashboard | http://localhost:8501 |
| Existing backend and API docs | http://localhost:8000/docs |
| Mock provider and docs | http://localhost:9090/docs |
| Existing PostgreSQL | localhost:5432 |

```bash
docker compose logs --tail=50 app mock-api dashboard
docker compose exec app python -m poc_demo.seed
docker compose exec app python -m poc_demo.main --company-id aef33b6b-773c-43cd-ab86-6f3882f2092a
```

The app uses `http://mock-api:9090` within Docker and Streamlit uses `http://app:8000`. Legacy source configurations for loopback port 9090 are resolved to the configured `POC_MOCK_BASE_URL` during execution, without changing their database registrations. Approved origins and paths are validated again before each acquisition. HTTP redirects, arbitrary headers, credentials and unsupported query parameters are rejected.

The older `docker-compose` binary on this workstation fails with `Not supported URL scheme http+docker` because of its installed Python dependencies. Use Compose v2 where available. Compose configuration was validated; the running demonstration described below was launched with direct Docker commands.

## Running demonstration on this workstation

The implementation session started the existing `invoice_finance_mvp-postgres-1` container, then launched:

- `invoice-week1-backend` on port 8000
- `invoice-week1-mock` on port 9090, with network alias `mock-api`
- `invoice-week1-dashboard` on port 8501

These services are already running. Open http://localhost:8501. If switching them to Compose, first stop these three demonstration containers to release their ports:

```bash
docker stop invoice-week1-dashboard invoice-week1-backend invoice-week1-mock
docker compose up --build -d
```

The tested direct Docker startup below is an alternative to Compose. It assumes the existing database container and network already exist. Do not run it while the above containers are already running with these names.

```bash
docker build -t invoice-finance-week1 .
docker start invoice_finance_mvp-postgres-1

docker run --rm --network invoice_finance_mvp_default --user 1000:1000 \
  -e DATABASE_URL=postgresql+psycopg://invoice_app:invoice_app@postgres:5432/invoice_finance \
  -e POC_IMAGES_DIR=/app/source_invoices -e POC_MOCK_BASE_URL=http://mock-api:9090 \
  -v "$PWD:/app" -v /home/elmehdi/Desktop/invoices/test_invoices:/app/source_invoices:ro \
  invoice-finance-week1 sh -c 'alembic upgrade head && python -m poc_demo.seed'

docker run -d --name invoice-week1-mock --network invoice_finance_mvp_default --network-alias mock-api \
  --user 1000:1000 -e POC_MOCK_HOST=0.0.0.0 -p 9090:9090 -v "$PWD:/app" \
  invoice-finance-week1 python -m poc_demo.mock_api

docker run -d --name invoice-week1-backend --network invoice_finance_mvp_default --user 1000:1000 \
  -e DATABASE_URL=postgresql+psycopg://invoice_app:invoice_app@postgres:5432/invoice_finance \
  -e POC_IMAGES_DIR=/app/source_invoices -e POC_RAW_DIR=/app/storage/raw/acquired \
  -e POC_MOCK_BASE_URL=http://mock-api:9090 -p 8000:8000 \
  -v "$PWD:/app" -v /home/elmehdi/Desktop/invoices/test_invoices:/app/source_invoices:ro \
  invoice-finance-week1 uvicorn app.main:app --host 0.0.0.0 --port 8000

docker run -d --name invoice-week1-dashboard --network invoice_finance_mvp_default --user 1000:1000 \
  -e POC_BACKEND_URL=http://invoice-week1-backend:8000 -p 8501:8501 -v "$PWD:/app" \
  invoice-finance-week1 python -m streamlit run poc_demo/dashboard.py \
  --server.address=0.0.0.0 --server.port=8501 --server.maxUploadSize=25 --browser.gatherUsageStats=false
```

## Host-based startup

Python 3.10+ is required. Keep the existing PostgreSQL service running; do not create another database.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
source poc_demo/env.sh
export POC_MOCK_BASE_URL=http://127.0.0.1:9090
export POC_BACKEND_URL=http://127.0.0.1:8000
alembic upgrade head
python -m poc_demo.seed
```

Use separate terminals with that environment to launch:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m poc_demo.mock_api
python -m streamlit run poc_demo/dashboard.py --server.port=8501 --server.maxUploadSize=25
```

`.env.example` contains development placeholders. `DATABASE_URL` must use `127.0.0.1` when Python runs on Ubuntu and `postgres` within Compose. `poc_demo/env.sh` contains the existing host database settings. The dashboard needs only `POC_BACKEND_URL`; its data and ingestion actions go through FastAPI.

## Supported sources and configuration

The registry contains FILE, DIRECTORY and HTTP_GET. Formats are CSV, JSON, XML, PDF, PNG, JPG/JPEG and legacy IMAGE for mixed image directories. File and HTTP responses preserve original bytes and MIME types. XML and document content remain opaque; no XML normalization or OCR runs.

Example configurable JSON source:

```json
{
  "source_code": "my_erp",
  "name": "Simulated ERP",
  "transport": "HTTP_GET",
  "data_format": "JSON",
  "entity_type": "INVOICE",
  "config": {
    "url": "http://mock-api:9090/mock/erp/invoices?scenario=paginated",
    "pagination": true,
    "records_path": "items",
    "external_id_path": "invoice_id",
    "page_size": 2,
    "max_pages": 100
  },
  "field_mapping": {},
  "is_active": true
}
```

On the host use `http://127.0.0.1:9090`. Nested paths such as `document.reference` support ERP B without another connector. `field_mapping` is stored for future normalization and has no effect on acquisition. File configs accept `path` (absolute within approved roots or relative to the project), the legacy `relative_path`, and an optional CSV `delimiter`. DIRECTORY can use `path` or `env_dir: POC_IMAGES_DIR`; scanning is nonrecursive and ignores symlinks. Uploaded files use a generated company/checksum path while their original filename is retained in source configuration and raw metadata.

Only `poc_demo/fixtures/` and the server-configured `POC_IMAGES_DIR` are readable as source roots. Uploaded fixtures are scoped to their company. HTTP destinations must match server-controlled `POC_ALLOWED_HTTP_ORIGINS` and `/mock/` or the legacy `/api/invoices` path. Do not place provider credentials in source configuration. The POC accepts no authentication headers.

Raw storage is `POC_RAW_DIR`, defaulting to `storage/raw/acquired/`. Folders now identify the company, business entity, source, format and artifact type:

```text
storage/raw/acquired/
  demo-company--<company-uuid>/
    invoices/
      week-1-invoices-en--<source-uuid>/csv/original-files/<sha256>.csv
      week-1-erp-a--<source-uuid>/json/api-responses/<sha256>.json
      week-1-erp-a--<source-uuid>/json/records/<sha256>.json
    payments/
      week-1-payments-csv--<source-uuid>/csv/original-files/<sha256>.csv
    bank-transactions/
      week-1-bank-api--<source-uuid>/json/records/<sha256>.json
```

Company and source names become sanitized lowercase labels. UUID suffixes keep identically named companies/sources distinct; filenames remain checksum-based. Formats are `csv`, `json`, `xml`, `pdf`, `png`, `jpeg`, or `images`. Artifact types are `original-files`, `api-responses`, and `records`. Original input filenames remain in metadata.

Writes are atomic. An unchanged source/checksum is deduplicated by a PostgreSQL unique constraint. A replay uses the artifact's registered location even after a company/source rename, restores a missing/corrupt content-addressed file, and does not insert another registry row. Downloads validate the registered checksum, company/source UUID boundaries and size. Legacy UUID-only paths remain readable.

To reorganize already acquired files using current company/source names, run this maintenance command while the backend is stopped:

```bash
python -m poc_demo.relabel_storage --company-id aef33b6b-773c-43cd-ab86-6f3882f2092a
```

The command verifies bytes, writes the new path atomically, commits the database path, then removes the superseded raw copy and empty directories. Artifact IDs, checksums, acquisition timestamps and ingestion history remain unchanged. Per-source locks prevent overlap with acquisition. It is safe to rerun; missing/corrupt files are reported and left untouched. No schema migration or reacquisition is needed. Original source documents are never moved.

No durable synchronization watermark is invented. The mock's temporary page numbers restart at one on every run. A failed pagination run retains stored pages, and a subsequent replay deduplicates them. Pagination has cycle detection, a 100-page limit, 10-second request timeouts and a 120-second acquisition limit.

## Mock endpoints and scenarios

| Endpoint | Response |
| --- | --- |
| `/mock/erp/invoices` | ERP A JSON envelope with `items`, `next_page` |
| `/mock/erp/invoices?variant=b` | ERP B nested document/partner/amount structures |
| `/mock/erp/invoices/{invoice_id}` | One synthetic invoice, e.g. INV-1001 |
| `/mock/erp/suppliers`, `/mock/erp/customers` | Synthetic partners |
| `/mock/payments/transactions` | successful, pending, failed and refunded payments |
| `/mock/payments/refunds` | Refund events |
| `/mock/bank/transactions` | Separate credit/debit bank bookings |
| `/mock/bank/accounts` | Synthetic account references |
| `/mock/erp/invoices.csv`, `/mock/erp/invoices.xml` | Original CSV/XML response bodies |
| `/mock/bank/transactions.csv` | Bank CSV response |
| `/mock/documents/invoice-sample.pdf` | Valid synthetic PDF |
| `/api/invoices` | Legacy POC compatibility |

JSON collection endpoints accept `scenario=success`, `empty`, `paginated`, `duplicates`, `http500`, `http429` or `malformed`. ERP invoices also implement `new` (INV-1004 added) and `updated` (INV-1001 amount changed). The same query always produces the same data. No failure is mixed into normal responses. There is no simulator state to reset: select `scenario=success` to return to baseline. CSV/XML/PDF endpoints are static deterministic fixtures.

## Streamlit pages and minimal demonstration

1. **Overview:** database source, active source, execution, success/failure, raw artifact and duplicate counts; last ingestion time; execution summary by transport.
2. **Data Sources:** inspect registered sources, create/edit configuration, choose transport/format/entity, select or upload a fixture, enable/disable a source, store future field mappings. Source details show the saved configuration.
3. **Run Ingestion:** select a source and click **Run ingestion**, or **Run all active sources**. Runs start through FastAPI, return IDs immediately and update every two seconds. The results include attempted/new/duplicate/error counts and duration.
4. **Ingestion History:** filter by source, status and UTC date; browse result pages; inspect execution errors.
5. **Raw Explorer:** filter by source and FILE/RESPONSE/RECORD; browse metadata and external identities; preview JSON, CSV, images and escaped XML. PDFs can be downloaded. Previews are capped at 2 MiB; full downloads at 25 MiB. All reads use registered artifact IDs.

For the minimal manual demo:

1. Open http://localhost:8501 and select Demo Company.
2. Visit Data Sources. The four original sources and 18 seeded Week 1 sources remain registered. The live demonstration also adds a separate scenario source.
3. Run all active sources. Inspect results and then repeat: unchanged content creates zero new registry rows and increments duplicate counts.
4. Register a FILE/CSV/PAYMENT source using `poc_demo/fixtures/csv/payments.csv`, then execute it without editing acquisition code.
5. Open Raw Explorer. Inspect CSV, JSON, XML, PNG and PDF artifacts; select RECORD to see stable external IDs separately from response envelopes.
6. Edit an ERP JSON source in Data Sources. Select `new`, save, and run. Select `updated`, save, and run again. Both INV-1001 versions remain traceable by external ID.
7. Select `http500`, save, and run. Inspect the FAILED execution and error in History. Select `success`, save, and run to verify recovery.
8. To demonstrate pagination choose `paginated`, enable **Follow mock page numbers**, save and execute. Return to `success` after the demonstration.

A scripted HTTP demonstration performs the same acquisition scenarios and checksum-verifies representative downloads:

```bash
# Current directly launched backend:
docker exec invoice-week1-backend python -m poc_demo.demo

# Compose backend:
docker compose exec app python -m poc_demo.demo

# Host:
python -m poc_demo.demo --backend-url http://127.0.0.1:8000
```

It writes actual results to `poc_demo/demo_results.json`. Repeating the command is safe; previously demonstrated versions may already exist. It restores the scenario source to success and never deletes execution data. It deliberately creates FAILED history entries for the three failure scenarios.

## Seed and explicit reset

```bash
python -m poc_demo.seed
python -m poc_demo.main --company-id aef33b6b-773c-43cd-ab86-6f3882f2092a
```

Seed generates deterministic synthetic fixtures, ensures the known Demo Company only if missing, and inserts missing `poc_w1_` source codes. It preserves existing sources, including edited source settings. Running ingestion alone does not seed or migrate automatically.

Only if you explicitly want to clear seeded POC execution metadata:

```bash
python -m poc_demo.reset \
  --company-id aef33b6b-773c-43cd-ab86-6f3882f2092a \
  --confirm RESET_POC_EXECUTIONS
```

Reset deletes `raw_artifact` and `ingestion_run` rows only for that company's `poc_w1_` sources. It refuses while a seeded run is RUNNING. It retains source registrations, other source histories, other companies, all core records, all raw files and all original images. Files retained after reset will be registered again on replay. This reset was tested only inside a generated test schema, and was not run against the development company's history.

## Automated verification

```bash
# Compose; uses an isolated generated schema in the existing development DB:
docker compose exec \
  -e TEST_DATABASE_URL=postgresql+psycopg://invoice_app:invoice_app@postgres:5432/invoice_finance \
  app python -m pytest -q poc_demo/tests

# Host:
TEST_DATABASE_URL="$DATABASE_URL" python -m pytest -q poc_demo/tests
```

If TEST_DATABASE_URL is unset, PostgreSQL-dependent tests are explicitly skipped. Tests never substitute SQLite. They create uniquely named schemas with no fallback to public, use synthetic companies/files, and drop those test schemas on teardown. The development company and its executions are not reset. HTTP unit tests use the real FastAPI mock application through an in-process transport; the live demonstration additionally verifies real HTTP traffic between running services. Streamlit AppTest registers a source, starts acquisition through FastAPI, reads its actual PostgreSQL execution and exercises all five pages.

See `VERIFICATION.md` for the executed commands, results and practical limitations.

## Known limitations and next integration

The following describes the Week 1 acquisition boundary. Week 2 normalization and optional LangChain image extraction are documented in the [current architecture guide](../docs/ARCHITECTURE.md); acquisition itself does not automatically apply business mappings.

- This is a local development UI/API without tenant authentication. Company-scoped queries prevent cross-company reads through resource IDs, but company IDs are not authorization credentials. Add authentication before exposing it beyond a trusted development environment.
- Two in-process workers and four admitted batches bound background work. PostgreSQL advisory locks prevent concurrent ingestion of the same source. The queue is not durable; stopping the backend during a job can leave RUNNING rows. Investigate those rows before an explicit metadata reset. There are no automatic destructive repairs.
- Source configuration is loaded when a worker starts. Avoid editing a queued source until its run finishes.
- Maximum artifact/upload size is 25 MiB; preview limit is 2 MiB. Directory limit is 1000 files; JSON response record limit is 10000. The execution artifact budget is 11000. This is not a large-file streaming platform.
- Filesystem and PostgreSQL are not one transaction. A failed registry insert may leave an unreferenced raw file. Raw files are retained conservatively; automatic orphan deletion is not implemented.
- Deduplication is per source and exact checksum. Semantically identical files with different bytes are separate artifacts. Original response changes can produce new RESPONSE artifacts even when every business record is unchanged.
- Field mappings are stored only. There is no XML normalization, PDF/image extraction, OCR/ML, reconciliation, forecasting, OAuth, external provider access, scheduled ingestion or durable incremental checkpoint.
- Future normalization should consume selected raw records with their `raw_artifact_id` provenance, then map into the existing invoice/party/payment/bank transaction model. Bank bookings must not become confirmed payments automatically.

The implementation uses the documented SQLAlchemy PostgreSQL conflict-handling API and Streamlit fragment polling: [SQLAlchemy PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert), [Streamlit fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment).

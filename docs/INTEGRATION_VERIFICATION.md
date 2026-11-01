# Week 1 and Week 2 integration verification

Executed on 2026-10-31 against the existing PostgreSQL 16 development database and Demo Company `aef33b6b-773c-43cd-ab86-6f3882f2092a`.

## Preserved original data and schema clone

A full backup was saved to `/tmp/invoice-finance-before-canonical.sql`. The backend was stopped briefly while applying migration `0003_canonical_pipeline`, then restarted. The migration cloned all 12 public tables and their existing rows into canonical, including independent copies of all 12 enums, indexes, checks and foreign keys. Operational acquisition data was copied with its existing IDs into integration_pipeline.

Before/after row counts and sorted content fingerprints match for all **11 public data tables**. The excluded table is alembic_version, whose revision advanced to 0003_canonical_pipeline. The recorded audit is [canonical_migration_verification.json](../poc_demo/canonical_migration_verification.json). No automatic reset or table replacement occurred.

The canonical clone's foreign keys reference canonical tables. Pipeline company/document/business references point to canonical and process references point to integration_pipeline. A direct catalog query confirmed **zero canonical columns using public enum types**.

## Automated tests

Executed the full original POC suite and new integration tests in generated PostgreSQL schemas:

```bash
docker run --rm --network invoice_finance_mvp_default --user 1000:1000 \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e TEST_DATABASE_URL=postgresql+psycopg://invoice_app:invoice_app@postgres:5432/invoice_finance \
  -v /home/elmehdi/Desktop/invoice_finance_mvp:/app -w /app \
  invoice-finance-week1 python -m pytest -q poc_demo/tests tests --tb=short
```

Final result: **91 passed, 1 warning in 9.88 seconds**, with no skips. The warning is Starlette's deprecated AnyIO BlockingPortal import.

Tests cover the existing POC, compatible imports, acquisition document registration, source/file boundaries, labeled storage, schema clone data/foreign keys/enums, mapping rules and immutable versions, dates/decimals/currencies/identifiers, invoice parties and lines, separate payment/bank loading, duplicate prevention, update approval, cross-source conflicts, transaction rollback, company isolation, reviewed image extraction, the LangChain message adapter, asynchronous Week 2 runs, API namespaces, explicit reset behavior and Streamlit controls.

All **11 live pages** rendered successfully through Streamlit AppTest against the running backend: five Week 1 pages and six Week 2 pages. A separate test registers/executes a source through Week 1 and previews/applies actual PostgreSQL records through Week 2.

## Live Week 1 regression demonstration

Executed:

```bash
docker exec invoice_finance_mvp-app-1 python -m poc_demo.demo \
  --report poc_demo/week1_regression_results.json
```

Actual results:

- All **26 active sources** succeeded: 61 attempted artifacts, 3 newly registered artifacts, 58 duplicates.
- Immediate unchanged replay: **0 new artifacts**, **61 duplicates**, all 26 runs successful.
- New/updated records, pagination, duplicate collections, empty collections, HTTP 500, HTTP 429 and malformed JSON scenarios behaved as expected.
- Successful runs after each failure recovered normally.
- Downloaded representative CSV, JSON, XML, PDF and PNG content and verified their SHA-256 checksums.

The three new source registrations cover detailed purchase JSON, French sales CSV and supplier XML, allowing real invoice lines to be demonstrated. Existing sources/configuration were retained. The simulator scenario source was restored to success. Actual run IDs and statistics are in [week1_regression_results.json](../poc_demo/week1_regression_results.json).

## Live Week 2 demonstration

Executed:

```bash
docker exec invoice_finance_mvp-app-1 python -m app.integration_pipeline.demo
```

| Source | Applied | Validation/review records | Immediate replay applied |
| --- | ---: | ---: | ---: |
| Detailed purchase JSON | 1 | 0 | 0 |
| French sales CSV | 2 | 0 | 0 |
| Foreign supplier XML | 1 | 0 | 0 |
| ERP A invoices | 3 | 0 | 0 |
| Payment JSON | 2 | 2 | 0 |
| Bank CSV | 3 | 0 | 0 |

The payment exceptions are actual FAILED and REFUNDED provider events. Their original data and normalization errors remain available. They were not silently converted into confirmed/cancelled payments. Default payment profiles created early during this implementation were superseded by immutable version 2 profiles with this conservative rule; prior versions remain available for audit.

Final canonical counts for Demo Company:

| Table | Rows |
| --- | ---: |
| document | 32 |
| invoice | 7 |
| invoice_line | 3 |
| party | 10 |
| payment | 2 |
| bank_transaction | 3 |
| payment_allocation | 0 |

No allocations or bank matches were fabricated. Of 61 pipeline raw artifacts, 60 have registered document links. One original legacy ERP response (`e3f42457-9675-49be-ad1f-f00ba420eee7`) still references an unavailable pre-existing file. Its metadata is preserved; no replacement was invented. Other missing demonstration files were restored by actual acquisition replay of their deterministic source scenarios.

Actual normalization run IDs, counters, exceptions and canonical counts are saved in [pipeline_demo_results.json](../poc_demo/pipeline_demo_results.json).

## AI and runtime limits

The LangChain/Ollama client packages are installed. Model configuration, structured image messaging and extraction audit were tested with a controlled model stub. No vision model was configured/downloaded, and no real inference was claimed. Real PNG/JPEG inference requires an installed vision-capable model configured through AI_VISION_MODEL and AI_VISION_BASE_URL. PDF rendering is not implemented; reviewed/existing OCR output can be submitted for PDF normalization.

Queues remain in-process, so a backend interruption can leave RUNNING rows. The local UI/API remains a development tool without tenant authentication. Unsupported refunds/credit notes, missing fields and ambiguous identity conflicts remain reviewable exceptions.

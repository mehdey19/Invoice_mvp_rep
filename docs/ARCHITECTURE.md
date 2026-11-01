# Acquisition and normalization architecture

The application exposes Week 1 (acquisition) and Week 2 (normalization) in the same Acquisition Lab at http://localhost:8501. Select the stage in the sidebar. Both stages have configuration, background execution, history and data exploration. The original POC commands, fixture files, mock API and `/poc` URLs remain supported.

## Code modules

```text
app/
  acquisition/              Week 1: transport registry, raw storage, source/run APIs
    connectors/
    services/               source, acquisition, artifact, document and query services
    main.py                 Week 1 CLI
    seed.py                 repeatable sample source registration
    settings.py             approved source paths, origins and limits
  normalization/            Week 2: versioned mappings and canonical loading
    schemas.py              typed invoice, party, line, payment and bank records
    mapper.py               approved transformations and field aliases
    readers.py              CSV, JSON, safe XML and extracted-image readers
    profiles.py             immutable mapping versions and sample profiles
    loaders.py              transactional business writes and identity bindings
    service.py              preview, apply, counters and provenance
    api.py                  Week 2 APIs and bounded background runs
    dashboard.py            Week 2 Streamlit pages
    main.py                 Week 2 CLI
  canonical/models/         existing business entities
  integration_pipeline/
    models.py               acquisition/extraction/normalization execution model
    schema_clone.py         schema/data cloning with independent foreign keys/enums
    bootstrap.py            source/profile initialization and document backfill
    demo.py                 repeatable Week 1 + Week 2 integration demonstration
  models/                   compatibility exports for previous model imports
ai_models/
  registry.py               explicit LangChain/Ollama model access
  extraction.py             image extraction and extraction-result audit
  prompts/                  versioned extraction instructions
  weights/                  reserved for local model files, ignored by git/build
poc_demo/                   existing demo UI, simulator, fixtures and tests
                            former implementation files delegate to app modules
```

## Database ownership

| Schema | Role |
| --- | --- |
| `public` | Original records retained. Application processing no longer writes here. Alembic records its migration revision here. |
| `canonical` | Full clone of the original public tables, records, enum types, indexes, checks and foreign keys. Business writes go to company, document, party, invoice, invoice_line, payment and bank_transaction here. |
| `integration_pipeline` | Operational data_source, ingestion_run and raw_artifact copied with their IDs/history, plus normalization_profile, normalization_run, normalization_item, source_entity_link and extraction_result. |

The copied acquisition tables in `canonical` are the requested snapshot of public; operational acquisition continues in `integration_pipeline`. They are not continuously synchronized. This avoids having two active registries.

The application connection uses `DATABASE_SEARCH_PATH=integration_pipeline,canonical`, with no fallback to public. The pipeline contains process tables only; business table names resolve to canonical. Foreign keys in the pipeline explicitly reference canonical companies/documents/business entities, and pipeline sources/runs/artifacts. Canonical enum types are independent of public enum types. The migration recreates foreign keys because PostgreSQL `LIKE INCLUDING ALL` does not clone them. See the [PostgreSQL documentation](https://www.postgresql.org/docs/16/sql-createtable.html).

`0003_canonical_pipeline` performs the clone once and refuses to overwrite existing destination schemas. It copies both structures and records. The inspected public schema had 12 ordinary tables, 12 enums, and no views, sequences, routines or triggers. The clone refuses to silently omit unsupported objects if this inventory changes. An automatic downgrade is refused because it would delete independent canonical/pipeline data.

## Week 1 — Acquisition

Pages: Overview, Data Sources, Run Ingestion, Ingestion History, Raw Explorer.

API namespace: `/api/week-1`, with the same routes also available under `/poc`:

```text
GET/POST  /api/week-1/companies/{company_id}/sources
PUT       /api/week-1/companies/{company_id}/sources/{source_id}
POST      /api/week-1/companies/{company_id}/runs
GET       /api/week-1/companies/{company_id}/runs
GET       /api/week-1/companies/{company_id}/artifacts
```

A run reads approved configured inputs, stores original bytes in the existing labeled raw directories, deduplicates by source/checksum and records actual counters. It also registers original files/HTTP responses in `canonical.document`. Structured batches use document_type OTHER; binary invoice documents use INVOICE. Derived API RECORD artifacts link to the original response's document. Documents are deduplicated by company/checksum. Existing artifacts gain document links on replay or explicit backfill without generating duplicate artifacts.

Original filenames, MIME types, size, hash, storage path, company, source and run provenance are retained. Raw content is never rewritten by normalization.

```bash
python -m app.acquisition.main --company-id aef33b6b-773c-43cd-ab86-6f3882f2092a
# Backward-compatible command:
python -m poc_demo.main --company-id aef33b6b-773c-43cd-ab86-6f3882f2092a
```

## Week 2 — Normalization

Pages: Overview, Mapping Profiles, Run Normalization, Normalization History, Canonical Explorer, Image Extraction.

API namespace: `/api/week-2`; legacy-compatible aliases remain under `/poc`:

```text
GET/POST  /api/week-2/companies/{company_id}/normalization/profiles/{source_id}
POST      /api/week-2/companies/{company_id}/normalization/runs
GET       /api/week-2/companies/{company_id}/normalization/runs/{run_id}
POST      /api/week-2/companies/{company_id}/normalization/runs/{run_id}/apply
GET       /api/week-2/companies/{company_id}/normalization/canonical/{entity}
GET       /api/week-2/companies/{company_id}/normalization/canonical-summary
```

`POST .../runs` accepts an optional source_id (omit for all active configured sources), optional version, apply_valid (default false), and allow_updates (default false). It returns run IDs immediately with HTTP 202. The UI polls recorded status and results. Each stage has two workers and four admitted batches; these queues are in-process rather than durable.

```bash
# Preview one source; omit source-id to preview all configured active sources:
python -m app.normalization.main --company-id COMPANY_UUID --source-id SOURCE_UUID
# Apply valid results; approve changes explicitly only when intended:
python -m app.normalization.main --company-id COMPANY_UUID --source-id SOURCE_UUID --apply
```

Mappings follow the agreed target/version/fields structure. `path` reads one field; `paths` is an ordered set of alternatives, with conflicting populated alternatives reported. `constant` supplies explicit source policy such as invoice direction. `transform` is restricted to trim, uppercase, date, decimal, number and enum. Required fields fail with field-level errors. Nested targets map party details, and line collections have their own field rules. No mapping executes Python code.

Amounts use Decimal with explicit separators and two-decimal rounding. Non-finite/out-of-range amounts are rejected. Dates use the configured format. Currency is trimmed/uppercased into a three-letter code, with explicit common aliases such as DH to MAD. Invoice numbers retain meaningful separators/leading zeros while whitespace/case is standardized. Party names preserve legal spelling; identifiers preserve leading zeros; emails are cleaned and validated.

## Loading and provenance

Preview stores NormalizedInvoice/NormalizedPayment/NormalizedBankTransaction payloads and validation errors in normalization_item. company_id and provenance come from the application, not raw document fields. Provenance includes source, record identity, raw artifact/checksum, row/object locator, mapping version/checksum and document link.

Apply writes one business record and its related party/line/binding updates in one transaction. A failed write rolls everything for that record back. An unchanged input/mapping is skipped. Changed records require explicit update approval. Newer raw versions block historical overwrites. Cross-source invoice-number conflicts require review. Tax identifiers or source-confined party identities are used; similar names are not automatically merged across sources. The company's own name is not inserted as an external party.

Invoices feed invoice, party and real supplied invoice_line rows; payments feed payment and party; bank entries feed bank_transaction and remain UNMATCHED. Documents become EXTRACTED/VALIDATED based on actual stage results. No invoice lines, missing dates, payment allocations, invoice payments or bank matches are invented. Failed/refunded provider events and credit notes stay visible with errors/review requirements when the canonical model has no explicit equivalent.

## Images and AI

See [ai_models/README.md](../ai_models/README.md). Images first enter acquisition as immutable raw documents. LangChain extraction writes an audited extraction_result, then the same mapping/validation/loading pipeline processes extracted fields. PDFs need an extraction result as well; PDF rendering into vision input is not part of this adapter. Existing OCR results or reviewed values can be submitted through the Image Extraction page.

## Startup and verification

```bash
docker compose up --build -d
```

Startup runs additive migrations and `python -m app.integration_pipeline.bootstrap`, which idempotently seeds sources/profiles and links readable existing artifacts to documents. Missing files are reported, not fabricated. Do not reset the database or delete the postgres_data volume.

```bash
docker compose exec app python -m app.integration_pipeline.demo
docker compose exec -e TEST_DATABASE_URL=postgresql+psycopg://invoice_app:invoice_app@postgres:5432/invoice_finance app python -m pytest -q poc_demo/tests tests
```

Tests use generated schemas in the existing PostgreSQL database. They never reset public/canonical production-like records. The original POC demonstration remains available through `python -m poc_demo.demo`.

An explicit POC execution reset also clears related normalization/extraction execution metadata for the selected seeded sources. It preserves canonical business/document rows, raw files, other sources/companies and external identity bindings, so replay remains idempotent. No reset runs automatically.

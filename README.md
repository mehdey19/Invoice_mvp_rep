# Invoice Finance MVP

Minimal backend foundation for an invoice/payment application.

Acquisition Lab exposes **Week 1 — Acquisition** and **Week 2 — Normalization** at
http://localhost:8501. Start both with `docker compose up --build -d`.
See [the architecture guide](docs/ARCHITECTURE.md) for the modules, `canonical` and
`integration_pipeline` schemas, versioned mappings, image models, APIs and commands.
The [original POC guide](poc_demo/README.md) remains available for its demonstration.

This project intentionally does not perform OCR or ML extraction. It preserves raw invoice files, records document metadata, and provides canonical relational tables that can later receive structured output from an existing extractor.

## Stack

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Docker Compose
- Filesystem raw invoice storage

## Start PostgreSQL and the API

```bash
docker compose up --build
```

If your Docker installation uses the legacy Compose binary:

```bash
docker-compose up --build
```

The API runs at:

```text
http://localhost:8000
```

Health check:

```bash
curl http://localhost:8000/health
```

## Run Migrations

With Docker Compose:

```bash
docker compose run --rm app alembic upgrade head
```

Legacy Compose:

```bash
docker-compose run --rm app alembic upgrade head
```

From a local Python environment:

```bash
pip install -r requirements.txt
alembic upgrade head
```

## Import Raw Invoices

The importer scans the configured source directory for:

- `.pdf`
- `.png`
- `.jpg`
- `.jpeg`

It calculates SHA-256, copies each source file into `storage/raw/invoices/`, and inserts one `document` row per unique `company_id + sha256_hash`.

With Docker Compose:

```bash
docker compose run --rm app python scripts/import_raw_invoices.py
```

Legacy Compose:

```bash
docker-compose run --rm app python scripts/import_raw_invoices.py
```

From a local Python environment:

```bash
python scripts/import_raw_invoices.py
```

Running the importer multiple times is safe. Duplicate files are skipped.

## Read Endpoints

```text
GET /health
GET /documents
GET /documents/{document_id}
GET /invoices
GET /invoices/{invoice_id}
GET /payments
GET /bank-transactions
```

## Inspect Imported Documents

Open psql:

```bash
docker compose exec postgres psql -U invoice_app -d invoice_finance
```

Legacy Compose:

```bash
docker-compose exec postgres psql -U invoice_app -d invoice_finance
```

Useful SQL:

```sql
select company_id, name, created_at
from company;

select document_id,
       original_filename,
       storage_path,
       mime_type,
       file_size,
       sha256_hash,
       processing_status,
       created_at
from document
order by created_at desc;

select sha256_hash, count(*)
from document
group by sha256_hash
having count(*) > 1;
```

## Inspect Business Tables

```sql
select * from invoice order by created_at desc;
select * from invoice_line order by created_at desc;
select * from payment order by created_at desc;
select * from payment_allocation order by created_at desc;
select * from bank_transaction order by created_at desc;
```

## ML Extractor Integration Point

The next integration should read from `document` rows with `processing_status = 'RAW'`, run your existing extractor against `storage_path`, then map the structured payload into:

```text
raw document
  -> extracted structured payload
  -> party
  -> invoice
  -> invoice_line
```

Keep extraction output separate from the canonical invoice tables until it has been normalized and validated.

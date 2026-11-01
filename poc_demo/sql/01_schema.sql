-- Experimental Week 1 POC additions; apply against an isolated development database.
-- Existing company/document/invoice/payment tables are not modified.
BEGIN;

CREATE TABLE IF NOT EXISTS data_source (
    data_source_id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES company(company_id),
    source_code VARCHAR(80) NOT NULL,
    name VARCHAR(160) NOT NULL,
    transport VARCHAR(20) NOT NULL CHECK (transport IN ('FILE','DIRECTORY','HTTP_GET')),
    data_format VARCHAR(20) NOT NULL CHECK (data_format IN ('CSV','JSON','IMAGE')),
    entity_type VARCHAR(30) NOT NULL CHECK (entity_type IN ('INVOICE','BANK_TRANSACTION','PAYMENT')),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    field_mapping JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_data_source_company_code UNIQUE (company_id, source_code)
);

CREATE TABLE IF NOT EXISTS ingestion_run (
    ingestion_run_id UUID PRIMARY KEY,
    data_source_id UUID NOT NULL REFERENCES data_source(data_source_id),
    company_id UUID NOT NULL REFERENCES company(company_id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','FAILED')),
    acquired_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_ingestion_run_source ON ingestion_run (data_source_id, started_at DESC);

CREATE TABLE IF NOT EXISTS raw_artifact (
    raw_artifact_id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES company(company_id),
    data_source_id UUID NOT NULL REFERENCES data_source(data_source_id),
    ingestion_run_id UUID NOT NULL REFERENCES ingestion_run(ingestion_run_id),
    original_filename VARCHAR(250) NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_size BIGINT NOT NULL CHECK (file_size >= 0),
    sha256_hash CHAR(64) NOT NULL,
    entity_type VARCHAR(30) NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_raw_artifact_source_checksum UNIQUE (data_source_id, sha256_hash)
);
CREATE INDEX IF NOT EXISTS idx_raw_artifact_company ON raw_artifact(company_id, acquired_at DESC);

COMMIT;

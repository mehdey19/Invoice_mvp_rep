-- Run with psql -v company_id='UUID_FROM_company' -f poc_demo/sql/02_seed_sources.sql
-- Source configs point to local demonstration fixtures and an HTTP mock.
\set ON_ERROR_STOP on
BEGIN;
WITH seed (source_code, name, transport, data_format, entity_type, config, field_mapping) AS (
 VALUES
 ('demo_bank_csv', 'Demo bank CSV export', 'FILE', 'CSV', 'BANK_TRANSACTION',
  '{"relative_path":"poc_demo/fixtures/bank_transactions.csv","delimiter":";"}'::jsonb,
  '{"transaction_date":"Date","reference":"Reference","amount":"Montant","currency":"Devise","description":"Libelle"}'::jsonb),
 ('demo_invoice_json', 'Demo invoice JSON file', 'FILE', 'JSON', 'INVOICE',
  '{"relative_path":"poc_demo/fixtures/invoices.json"}'::jsonb,
  '{"external_id":"id","invoice_number":"number","total_amount":"total"}'::jsonb),
 ('demo_invoice_api', 'Mock ERP invoice API', 'HTTP_GET', 'JSON', 'INVOICE',
  '{"url":"http://127.0.0.1:9090/api/invoices"}'::jsonb,
  '{"external_id":"id","invoice_number":"number","total_amount":"amount_total"}'::jsonb),
 ('demo_invoice_images', 'Existing sample invoice images', 'DIRECTORY', 'IMAGE', 'INVOICE',
  '{"env_dir":"POC_IMAGES_DIR","extensions":[".png",".jpg",".jpeg"]}'::jsonb,
  '{}'::jsonb)
)
INSERT INTO data_source(data_source_id, company_id, source_code, name, transport, data_format, entity_type, config, field_mapping)
SELECT md5(:'company_id' || ':' || source_code)::uuid, :'company_id'::uuid, source_code, name, transport, data_format, entity_type, config, field_mapping
FROM seed
ON CONFLICT (company_id, source_code) DO NOTHING;
COMMIT;

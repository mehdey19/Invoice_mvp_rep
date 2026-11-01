# Week 2 — Normalization

Versioned mappings convert acquired CSV/JSON/XML records, or extracted image/PDF fields, into typed invoice/payment/bank records. Preview stores results and errors in integration_pipeline; apply writes validated fields into canonical in a transaction per record.

The model uses explicit field paths/aliases, constants and approved transforms. It standardizes amounts, currency codes, dates, invoice numbers and party details while preserving raw content and provenance. Source updates require approval; replay does not duplicate records. Unsupported statuses or incomplete documents remain visible for review.

Select Week 2 — Normalization in Acquisition Lab. Pages mirror Week 1's overview/configuration/execution/history/explorer structure. Use the additional Image Extraction page for LangChain or reviewed extraction results.

See [the architecture guide](../../docs/ARCHITECTURE.md) for detailed rules, schema ownership, API endpoints and CLI commands.

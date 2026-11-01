# Week 1 — Acquisition

Implementation of the existing POC's FILE, DIRECTORY and HTTP_GET acquisition.

Connectors, validation, raw interpretation, labeled storage and services live here. Former imports under poc_demo delegate to these modules, including connector-module aliases so existing monkeypatches and tests still work. Demo fixtures, simulator and Streamlit entry point stay under poc_demo.

Operational tables are in integration_pipeline. Original files/responses also register in canonical.document; RECORD artifacts link back to the response document. The core acquisition counters, duplicate rules, source boundaries and original raw bytes are preserved.

See [the architecture guide](../../docs/ARCHITECTURE.md) for startup, schema ownership, APIs and both stages.

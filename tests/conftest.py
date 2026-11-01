# Reuse the existing POC's isolated PostgreSQL schema and synthetic fixtures.
from poc_demo.tests.conftest import db_engine,company,client,mock_http  # noqa: F401

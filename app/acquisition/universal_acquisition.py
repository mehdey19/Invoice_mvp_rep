"""Shared transport → raw storage → interpretation compatibility entry point.

Providers are registered in PostgreSQL; adding sources needs no changes here.
"""
from app.acquisition.connectors import CONNECTORS
from app.acquisition.connectors.base import RawItem
from app.acquisition.services.acquisition_service import acquire_all, execute_source
from app.acquisition.services.artifact_service import persist_raw
from app.acquisition.settings import PROJECT_ROOT, MAX_BYTES, allowed_path, raw_root

RAW_ROOT = raw_root()
relative_input_path = allowed_path


def raw_items(source):
    yield from CONNECTORS[source['transport']]().acquire(source)

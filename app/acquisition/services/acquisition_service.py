"""One ingestion workflow for all registered transport/format combinations."""
import hashlib
import time
from uuid import uuid4
from sqlalchemy import update, func, text
from app.models.acquisition import IngestionRun
from app.acquisition.connectors import CONNECTORS
from app.acquisition.interpretation import interpret
from app.acquisition.services.artifact_service import persist_raw
from app.acquisition.services.source_service import get_source, identifier, list_sources, validate_source

runs = IngestionRun.__table__


def create_run(engine, source):
    run_id = uuid4()
    with engine.begin() as conn:
        conn.execute(runs.insert().values(ingestion_run_id=run_id, data_source_id=identifier(source["data_source_id"]),
                                         company_id=identifier(source["company_id"]), status="RUNNING"))
    return run_id


def execute_source(engine, source, run_id=None):
    source = get_source(engine, source["company_id"], source["data_source_id"])
    run_id = identifier(run_id) if run_id else create_run(engine, source)
    new = duplicates = attempted = 0
    status, error = "SUCCEEDED", None
    start = time.monotonic()
    lock_key = int.from_bytes(hashlib.sha256(str(source["data_source_id"]).encode()).digest()[:8], "big", signed=True)
    with engine.connect() as lease:
        locked = False
        try:
            locked = lease.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}).scalar()
            lease.commit()
            if not locked:
                raise ValueError("This source already has an ingestion in progress")
            if not source["is_active"]:
                raise ValueError("Source is disabled")
            validate_source(source)
            for item in CONNECTORS[source["transport"]]().acquire(source):
                if time.monotonic() - start > 120:
                    raise ValueError("Acquisition exceeded the 120-second POC limit")
                for artifact in _original_and_records(source, item):
                    attempted += 1
                    if attempted > 11000:
                        raise ValueError("Run exceeds 11000 artifacts")
                    if persist_raw(engine, source, run_id, artifact):
                        new += 1
                    else:
                        duplicates += 1
                    with engine.begin() as conn:
                        conn.execute(update(runs).where(runs.c.ingestion_run_id == run_id).values(
                            acquired_count=new, duplicate_count=duplicates, attempted_count=attempted))
        except Exception as exc:
            status, error = "FAILED", f"{type(exc).__name__}: {exc}"[:2000]
        finally:
            if locked:
                lease.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
                lease.commit()
    with engine.begin() as conn:
        conn.execute(update(runs).where(runs.c.ingestion_run_id == run_id).values(
            finished_at=func.now(), status=status, acquired_count=new, duplicate_count=duplicates,
            attempted_count=attempted, error_count=int(error is not None), error_message=error))
    return {"source": source["source_code"], "run_id": str(run_id), "status": status,
            "acquired": new, "new_artifacts": new, "attempted": attempted,
            "duplicates": duplicates, "errors": int(error is not None), "error": error}


def _original_and_records(source, item):
    yield item
    yield from interpret(source, item)


def acquire_all(engine, company_id):
    return [execute_source(engine, source) for source in list_sources(engine, company_id) if source["is_active"]]

import hashlib
import os
from pathlib import Path
import tempfile
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.models.acquisition import RawArtifact
from app.models.company import Company
from app.acquisition.settings import MAX_BYTES, PREVIEW_BYTES
from app.acquisition.services.source_service import identifier
from app.acquisition.storage_layout import labeled_path, registered_path, storage_reference

artifacts = RawArtifact.__table__


def write_payload(dest, payload, digest):
    """Atomically store verified bytes; also repairs missing/corrupt files on replay."""
    if len(payload) > MAX_BYTES or hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("Artifact integrity verification failed")
    dest.parent.mkdir(parents=True, exist_ok=True)
    valid = False
    if dest.is_file() and dest.stat().st_size == len(payload):
        valid = hashlib.sha256(dest.read_bytes()).hexdigest() == digest
    if not valid:
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as out:
                temp = out.name
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, dest)
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)


def persist_raw(engine, source, run_id, item):
    if len(item.payload) > MAX_BYTES:
        raise ValueError("Artifact exceeds 25 MiB")
    digest = hashlib.sha256(item.payload).hexdigest()
    with engine.connect() as conn:
        existing = conn.execute(select(artifacts).where(
            artifacts.c.company_id == identifier(source["company_id"]),
            artifacts.c.data_source_id == identifier(source["data_source_id"]),
            artifacts.c.sha256_hash == digest)).mappings().first()
        company_name = conn.scalar(select(Company.name).where(Company.company_id == identifier(source["company_id"])))
    if existing:
        # Preserve the registered location when a company or source is renamed.
        write_payload(registered_path(existing), item.payload, digest)
        from app.acquisition.services.document_service import register_document
        with engine.begin() as conn:
            did = register_document(conn, source, item, existing["storage_path"], digest)
            conn.execute(artifacts.update().where(artifacts.c.raw_artifact_id == existing["raw_artifact_id"]).values(document_id=did))
        return False
    artifact = dict(company_id=source["company_id"], data_source_id=source["data_source_id"], sha256_hash=digest,
                    original_filename=item.filename, entity_type=source["entity_type"], data_format=source["data_format"],
                    artifact_kind=item.artifact_kind)
    dest = labeled_path(artifact, company_name, source.get("name") or source["source_code"])
    write_payload(dest, item.payload, digest)
    path = storage_reference(dest)
    with engine.begin() as conn:
        from app.acquisition.services.document_service import register_document
        did = register_document(conn, source, item, path, digest)
        result = conn.execute(insert(artifacts).values(
            raw_artifact_id=uuid4(), company_id=identifier(source["company_id"]),
            data_source_id=identifier(source["data_source_id"]), ingestion_run_id=identifier(run_id),
            original_filename=Path(item.filename.replace("\\", "/")).name[:250] or "artifact",
            storage_path=path, mime_type=item.mime_type[:100], file_size=len(item.payload), sha256_hash=digest,
            entity_type=source["entity_type"], data_format=source["data_format"], external_id=item.external_id,
            artifact_kind=item.artifact_kind, acquisition_metadata=item.metadata,
            document_id=did,
        ).on_conflict_do_nothing(index_elements=[artifacts.c.data_source_id, artifacts.c.sha256_hash]).returning(artifacts.c.raw_artifact_id)).scalar_one_or_none()
    return result is not None


def get_artifact(engine, company_id, artifact_id):
    with engine.connect() as conn:
        row = conn.execute(select(artifacts).where(artifacts.c.company_id == identifier(company_id), artifacts.c.raw_artifact_id == identifier(artifact_id))).mappings().first()
    if not row:
        raise LookupError("Artifact not found for this company")
    return dict(row)


def read_artifact(engine, company_id, artifact_id, preview=False):
    artifact = get_artifact(engine, company_id, artifact_id)
    path = registered_path(artifact)
    limit = PREVIEW_BYTES if preview else MAX_BYTES
    if artifact["file_size"] > limit:
        raise ValueError(f"Artifact exceeds the {'preview' if preview else 'download'} limit of {limit} bytes")
    try:
        with path.open("rb") as handle:
            payload = handle.read(limit + 1)
    except OSError as exc:
        raise LookupError("Registered artifact file is unavailable") from exc
    if len(payload) != artifact["file_size"] or hashlib.sha256(payload).hexdigest() != artifact["sha256_hash"]:
        raise ValueError("Artifact integrity verification failed")
    return artifact, payload

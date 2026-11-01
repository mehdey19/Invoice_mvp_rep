"""Register original acquired content in the canonical document catalogue."""
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from app.canonical.models.document import Document
from app.integration_pipeline.models import RawArtifact
from app.acquisition.services.source_service import identifier


def register_document(conn, source, item, path, digest):
    if item.artifact_kind == "RECORD":
        parent = item.metadata.get("response_sha256")
        if not parent:
            return None
        return conn.scalar(select(RawArtifact.document_id).where(
            RawArtifact.company_id == identifier(source["company_id"]),
            RawArtifact.data_source_id == identifier(source["data_source_id"]), RawArtifact.sha256_hash == parent))
    binary_invoice = source["entity_type"] == "INVOICE" and source["data_format"] in {"PDF", "IMAGE", "PNG", "JPG", "JPEG"}
    values = dict(document_id=uuid4(), company_id=identifier(source["company_id"]),
                  original_filename=item.filename.replace("\\", "/").rsplit("/", 1)[-1][:500], storage_path=path,
                  mime_type=item.mime_type[:255], file_size=len(item.payload), sha256_hash=digest,
                  document_type="INVOICE" if binary_invoice else "OTHER",
                  source_type="API" if source["transport"] == "HTTP_GET" else "MANUAL_UPLOAD", processing_status="RAW")
    created = conn.scalar(insert(Document.__table__).values(**values).on_conflict_do_nothing(
        index_elements=["company_id", "sha256_hash"]).returning(Document.document_id))
    return created or conn.scalar(select(Document.document_id).where(
        Document.company_id == identifier(source["company_id"]), Document.sha256_hash == digest))


def backfill_documents(engine, company_id):
    """Fill document links for previously acquired, readable artifacts only."""
    from app.acquisition.services.source_service import list_sources
    from app.acquisition.services.artifact_service import read_artifact
    from app.acquisition.connectors.base import RawItem
    report = {"linked": 0, "errors": []}
    for source in list_sources(engine, company_id):
        with engine.connect() as conn:
            rows = conn.execute(select(RawArtifact.__table__).where(
                RawArtifact.company_id == identifier(company_id), RawArtifact.data_source_id == source["data_source_id"])
                .order_by(RawArtifact.artifact_kind.desc())).mappings().all()  # RESPONSE precedes RECORD
        for row in rows:
            try:
                artifact, payload = read_artifact(engine, company_id, row["raw_artifact_id"])
                item = RawItem(artifact["original_filename"], artifact["mime_type"], payload,
                               artifact["external_id"], artifact["acquisition_metadata"], artifact["artifact_kind"])
                with engine.begin() as conn:
                    did = register_document(conn, source, item, artifact["storage_path"], artifact["sha256_hash"])
                    conn.execute(update(RawArtifact).where(RawArtifact.raw_artifact_id == row["raw_artifact_id"]).values(document_id=did))
                if did: report["linked"] += 1
            except Exception as exc:
                report["errors"].append({"artifact_id": str(row["raw_artifact_id"]), "error": str(exc)})
    return report

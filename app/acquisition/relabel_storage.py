"""Move registered raw artifacts into readable folders without re-ingesting data."""
import argparse
import hashlib
from uuid import UUID

from sqlalchemy import create_engine, select, text, update

from app.config import get_settings
from app.models.acquisition import DataSource, RawArtifact
from app.models.company import Company
from app.models.document import Document
from app.acquisition.services.artifact_service import read_artifact, write_payload
from app.acquisition.services.source_service import identifier
from app.acquisition.settings import raw_root
from app.acquisition.storage_layout import labeled_path, registered_path, storage_reference


def relabel_storage(engine, company_id):
    """Copy+verify, commit the registry path, then remove the superseded raw copy.

    Per-source acquisition locks prevent overlap with ingestion or another
    relabel operation. Run this maintenance command with API readers stopped.
    Every artifact commits independently, making an interrupted run resumable.
    """
    company_id = identifier(company_id)
    with engine.connect() as conn:
        sources = conn.execute(select(DataSource.__table__, Company.name.label("company_name"))
                               .join(Company, DataSource.company_id == Company.company_id)
                               .where(DataSource.company_id == company_id)).mappings().all()
    report = {"moved": 0, "unchanged": 0, "retained_old_files": [], "errors": []}
    for source in sources:
        sid = source["data_source_id"]
        key = int.from_bytes(hashlib.sha256(str(sid).encode()).digest()[:8], "big", signed=True)
        with engine.connect() as lease:
            locked = lease.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            lease.commit()
            if not locked:
                report["errors"].append({"source_id": str(sid), "error": "Source acquisition is in progress"})
                continue
            try:
                with engine.connect() as conn:
                    ids = list(conn.scalars(select(RawArtifact.raw_artifact_id).where(
                        RawArtifact.company_id == company_id, RawArtifact.data_source_id == sid)))
                for aid in ids:
                    try:
                        artifact, payload = read_artifact(engine, company_id, aid)
                        old = registered_path(artifact)
                        dest = labeled_path(artifact, source["company_name"], source["name"])
                        if dest == old:
                            report["unchanged"] += 1
                            continue
                        write_payload(dest, payload, artifact["sha256_hash"])
                        with engine.begin() as conn:
                            changed = conn.execute(update(RawArtifact).where(
                                RawArtifact.raw_artifact_id == aid, RawArtifact.company_id == company_id,
                                RawArtifact.storage_path == artifact["storage_path"])
                                .values(storage_path=storage_reference(dest))).rowcount
                            if changed != 1:
                                raise ValueError("Artifact path changed during relabeling; retry")
                            conn.execute(update(Document).where(Document.company_id == company_id,
                                Document.storage_path == artifact["storage_path"]).values(storage_path=storage_reference(dest)))
                        report["moved"] += 1
                        # The database now references verified destination bytes.
                        # Remove only this registered raw copy, never input files.
                        try:
                            old.unlink()
                            parent = old.parent
                            while parent != raw_root() and parent.is_relative_to(raw_root()):
                                try:
                                    parent.rmdir()
                                except OSError:
                                    break
                                parent = parent.parent
                        except OSError:
                            report["retained_old_files"].append(str(old))
                    except Exception as exc:
                        report["errors"].append({"artifact_id": str(aid), "error": str(exc)})
            finally:
                lease.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                lease.commit()
    return report


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company-id", type=UUID, required=True)
    args = parser.parse_args()
    from app.database import create_app_engine
    result = relabel_storage(create_app_engine(), args.company_id)
    print(json.dumps(result, indent=2))
    if result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

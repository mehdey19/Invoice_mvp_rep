import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.models.acquisition import RawArtifact
from app.models.company import Company
from poc_demo.relabel_storage import relabel_storage
from poc_demo.services.acquisition_service import execute_source
from poc_demo.services.artifact_service import read_artifact
from poc_demo.services.query_service import list_artifacts
from poc_demo.services.source_service import save_source
from poc_demo.settings import FIXTURES, raw_root
from poc_demo.storage_layout import label, registered_path


def file_source(engine, cid, name="French supplier invoices", **overrides):
    data = dict(source_code="test_"+uuid4().hex, name=name, transport="FILE", data_format="CSV", entity_type="INVOICE",
                config={"path": str(FIXTURES/"csv/invoices_english.csv")})
    data.update(overrides)
    return save_source(engine, cid, data)


def test_readable_folders_and_replay_after_rename(db_engine, company):
    with db_engine.begin() as conn:
        conn.execute(update(Company).where(Company.company_id == company).values(name="Société Démo / Casablanca"))
    source = file_source(db_engine, company)
    assert execute_source(db_engine, source)["acquired"] == 1
    artifact, = list_artifacts(db_engine, company)
    path = registered_path(artifact)
    assert path.relative_to(raw_root()).parts[:-1] == (
        f"societe-demo-casablanca--{company}", "invoices", f"french-supplier-invoices--{source['data_source_id']}",
        "csv", "original-files")
    original = path.read_bytes()
    source["name"] = "Renamed supplier export"
    save_source(db_engine, company, source, source["data_source_id"])
    with db_engine.begin() as conn:
        conn.execute(update(Company).where(Company.company_id == company).values(name="Renamed Company"))
    assert execute_source(db_engine, source)["duplicates"] == 1
    same, payload = read_artifact(db_engine, company, artifact["raw_artifact_id"])
    assert same["storage_path"] == artifact["storage_path"] and payload == original
    assert len(list(raw_root().rglob("*.csv"))) == 1


def test_same_names_do_not_collide(db_engine, company):
    for _ in range(2):
        source = file_source(db_engine, company, name="Same label")
        assert execute_source(db_engine, source)["acquired"] == 1
    rows = list_artifacts(db_engine, company)
    assert len({r["storage_path"] for r in rows}) == 2
    for row in rows:
        read_artifact(db_engine, company, row["raw_artifact_id"])


def test_api_response_and_record_labels(db_engine, company, mock_http):
    source = file_source(db_engine, company, name="Payment provider", transport="HTTP_GET", data_format="JSON", entity_type="PAYMENT",
        config={"url": "http://localhost:9090/mock/payments/transactions", "records_path": "items", "external_id_path": "payment_id"})
    assert execute_source(db_engine, source)["status"] == "SUCCEEDED"
    rows = list_artifacts(db_engine, company)
    assert {registered_path(row).parent.name for row in rows} == {"api-responses", "records"}
    assert all(registered_path(row).parts[-5] == "payments" for row in rows)


def test_legacy_relabel_preserves_ids_bytes_and_duplicates(db_engine, company):
    source = file_source(db_engine, company)
    execute_source(db_engine, source)
    artifact, = list_artifacts(db_engine, company)
    original = registered_path(artifact)
    payload = original.read_bytes()
    legacy = raw_root()/str(company)/str(source["data_source_id"])/artifact["sha256_hash"][:2]/original.name
    legacy.parent.mkdir(parents=True)
    original.rename(legacy)
    with db_engine.begin() as conn:
        conn.execute(update(RawArtifact).where(RawArtifact.raw_artifact_id == artifact["raw_artifact_id"]).values(storage_path=str(legacy)))
    assert read_artifact(db_engine, company, artifact["raw_artifact_id"])[1] == payload
    result = relabel_storage(db_engine, company)
    assert result == {"moved": 1, "unchanged": 0, "retained_old_files": [], "errors": []}
    migrated, actual = read_artifact(db_engine, company, artifact["raw_artifact_id"])
    assert actual == payload and migrated["raw_artifact_id"] == artifact["raw_artifact_id"]
    assert migrated["ingestion_run_id"] == artifact["ingestion_run_id"]
    assert not legacy.exists() and not (raw_root()/str(company)).exists()
    assert relabel_storage(db_engine, company)["unchanged"] == 1
    assert execute_source(db_engine, source)["acquired"] == 0


def test_relabel_refuses_corrupt_data(db_engine, company):
    source = file_source(db_engine, company)
    execute_source(db_engine, source)
    artifact, = list_artifacts(db_engine, company)
    path = registered_path(artifact)
    path.write_bytes(b"corrupt")
    result = relabel_storage(db_engine, company)
    assert result["moved"] == 0 and result["errors"]
    assert path.read_bytes() == b"corrupt"


def test_label_paths_cannot_cross_companies_or_sources(db_engine, company):
    source = file_source(db_engine, company)
    execute_source(db_engine, source)
    artifact, = list_artifacts(db_engine, company)
    for key in ("company_id", "data_source_id"):
        with pytest.raises(ValueError, match="outside"):
            registered_path(dict(artifact, **{key: uuid4()}))


@pytest.mark.parametrize("name", ["../../etc/passwd", "Société Démo", "你好", "x"*300])
def test_label_sanitization(name):
    clean = label(name, "source")
    assert clean and len(clean) <= 60 and "/" not in clean and ".." not in clean

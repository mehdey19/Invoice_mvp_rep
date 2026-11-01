"""Readable storage labels with immutable company/source identity boundaries."""
from pathlib import Path
import re
import unicodedata

from app.acquisition.settings import PROJECT_ROOT, raw_root
from app.acquisition.services.source_service import identifier

ENTITY_LABELS = {"INVOICE": "invoices", "PAYMENT": "payments", "BANK_TRANSACTION": "bank-transactions"}
KIND_LABELS = {"FILE": "original-files", "RESPONSE": "api-responses", "RECORD": "records"}
FORMAT_LABELS = {"CSV": "csv", "JSON": "json", "XML": "xml", "PDF": "pdf",
                 "PNG": "png", "JPG": "jpeg", "JPEG": "jpeg", "IMAGE": "images", None: "unknown"}
SUFFIXES = {".csv", ".json", ".xml", ".png", ".jpg", ".jpeg", ".pdf", ".bin"}


def label(value, fallback):
    ascii_text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:60].rstrip("-") or fallback


def _categories(artifact):
    return (ENTITY_LABELS[artifact["entity_type"]], FORMAT_LABELS[artifact.get("data_format")],
            KIND_LABELS[artifact.get("artifact_kind", "FILE")])


def labeled_path(artifact, company_name, source_name):
    company_id = str(identifier(artifact["company_id"]))
    source_id = str(identifier(artifact["data_source_id"]))
    digest = artifact["sha256_hash"]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid artifact checksum")
    ext = Path(artifact["original_filename"]).suffix.lower()
    if ext not in SUFFIXES:
        ext = ".bin"
    entity, fmt, kind = _categories(artifact)
    path = (raw_root() / f"{label(company_name, 'company')}--{company_id}" / entity
            / f"{label(source_name, 'source')}--{source_id}" / fmt / kind / (digest + ext))
    # Validate the resolved path too: labels must not follow a symlink outside
    # the expected company/source boundaries.
    return registered_path(dict(artifact, storage_path=str(path)))


def storage_reference(path):
    return str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else str(path)


def registered_path(artifact):
    path = Path(artifact["storage_path"])
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    try:
        parts = path.relative_to(raw_root()).parts
    except ValueError as exc:
        raise ValueError("Artifact path is outside its registered source storage") from exc
    cid, sid = str(identifier(artifact["company_id"])), str(identifier(artifact["data_source_id"]))
    digest = artifact["sha256_hash"]
    filename_ok = path.stem == digest and path.suffix in SUFFIXES
    legacy = (len(parts) == 4 and parts[:2] == (cid, sid) and parts[2] == digest[:2])
    readable = False
    if len(parts) == 6:
        entity, fmt, kind = _categories(artifact)
        def matches(component, identity):
            suffix = "--" + identity
            return component.endswith(suffix) and bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", component[:-len(suffix)]))
        readable = (matches(parts[0], cid) and matches(parts[2], sid)
                    and (parts[1], parts[3], parts[4]) == (entity, fmt, kind))
    if not filename_ok or not (legacy or readable):
        raise ValueError("Artifact path is outside its registered source storage")
    return path

#!/usr/bin/env python3
import hashlib
import mimetypes
import shutil
import sys
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.document import Document, DocumentType, ProcessingStatus, SourceType  # noqa: E402

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_or_create_demo_company(db: Session) -> Company:
    settings = get_settings()
    company = db.scalar(select(Company).where(Company.name == settings.default_company_name))
    if company is not None:
        return company

    company = Company(name=settings.default_company_name, default_currency=None, country_code=None)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def supported_source_files(source_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def import_file(db: Session, company: Company, source_path: Path, storage_dir: Path) -> str:
    file_hash = sha256_file(source_path)
    existing = db.scalar(
        select(Document).where(
            Document.company_id == company.company_id,
            Document.sha256_hash == file_hash,
        )
    )
    if existing is not None:
        return f"SKIP duplicate {source_path.name} -> {existing.document_id}"

    document_id = uuid.uuid4()
    destination_name = f"{document_id}{source_path.suffix.lower()}"
    destination_path = storage_dir / destination_name
    storage_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)

    relative_path = destination_path.relative_to(PROJECT_ROOT).as_posix()
    mime_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
    document = Document(
        document_id=document_id,
        company_id=company.company_id,
        original_filename=source_path.name,
        storage_path=relative_path,
        mime_type=mime_type,
        file_size=source_path.stat().st_size,
        sha256_hash=file_hash,
        document_type=DocumentType.INVOICE,
        source_type=SourceType.MANUAL_UPLOAD,
        processing_status=ProcessingStatus.RAW,
    )
    db.add(document)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if destination_path.exists():
            destination_path.unlink()
        duplicate = db.scalar(
            select(Document).where(
                Document.company_id == company.company_id,
                Document.sha256_hash == file_hash,
            )
        )
        return f"SKIP duplicate {source_path.name} -> {duplicate.document_id if duplicate else 'existing hash'}"

    return f"IMPORTED {source_path.name} -> {document_id}"


def main() -> int:
    settings = get_settings()
    source_dir = settings.raw_invoice_source_dir
    storage_dir = settings.raw_invoice_storage_dir
    if not source_dir.is_absolute():
        source_dir = PROJECT_ROOT / source_dir
    if not storage_dir.is_absolute():
        storage_dir = PROJECT_ROOT / storage_dir

    if not source_dir.exists():
        print(f"Source directory does not exist: {source_dir}", file=sys.stderr)
        return 1

    files = supported_source_files(source_dir)
    if not files:
        print(f"No supported invoice files found in {source_dir}")
        return 0

    with SessionLocal() as db:
        company = get_or_create_demo_company(db)
        print(f"Company: {company.name} ({company.company_id})")
        for source_path in files:
            print(import_file(db, company, source_path, storage_dir))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

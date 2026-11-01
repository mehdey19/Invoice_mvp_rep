"""Intermediary acquisition metadata; no normalization into business tables."""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

json_type = JSON().with_variant(JSONB, "postgresql")


class DataSource(Base):
    __tablename__ = "data_source"
    __table_args__ = (UniqueConstraint("company_id", "source_code", name="uq_data_source_company_code"),)

    data_source_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.company_id"), nullable=False)
    source_code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    transport: Mapped[str] = mapped_column(String(20))
    data_format: Mapped[str] = mapped_column(String(20))
    entity_type: Mapped[str] = mapped_column(String(30))
    config: Mapped[dict] = mapped_column(json_type, default=dict, server_default="{}")
    field_mapping: Mapped[dict] = mapped_column(json_type, default=dict, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionRun(Base):
    __tablename__ = "ingestion_run"
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_source.data_source_id"))
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.company_id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    # Historical acquired_count already means NEW artifacts. Keep that meaning.
    acquired_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    attempted_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)


class RawArtifact(Base):
    __tablename__ = "raw_artifact"
    __table_args__ = (UniqueConstraint("data_source_id", "sha256_hash", name="uq_raw_artifact_source_checksum"),)
    raw_artifact_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.company_id"))
    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_source.data_source_id"))
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_run.ingestion_run_id"))
    original_filename: Mapped[str] = mapped_column(String(250))
    storage_path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(BigInteger)
    sha256_hash: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(30))
    data_format: Mapped[str | None] = mapped_column(String(20))
    external_id: Mapped[str | None] = mapped_column(Text)
    artifact_kind: Mapped[str] = mapped_column(String(20), default="FILE", server_default="FILE")
    acquisition_metadata: Mapped[dict] = mapped_column(json_type, default=dict, server_default="{}")
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document.document_id"))


class NormalizationProfile(Base):
    __tablename__ = "normalization_profile"
    __table_args__ = (UniqueConstraint("data_source_id", "version", name="uq_profile_source_version"),)
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.company_id"))
    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_source.data_source_id"))
    version: Mapped[int] = mapped_column(Integer)
    target: Mapped[str] = mapped_column(String(30))
    mapping: Mapped[dict] = mapped_column(json_type)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NormalizationRun(Base):
    __tablename__ = "normalization_run"
    normalization_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.company_id"))
    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_source.data_source_id"))
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("normalization_profile.profile_id"))
    status: Mapped[str] = mapped_column(String(30), default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    valid_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    applied_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)


class NormalizationItem(Base):
    __tablename__ = "normalization_item"
    normalization_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    normalization_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("normalization_run.normalization_run_id"))
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.company_id"))
    raw_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_artifact.raw_artifact_id"))
    record_locator: Mapped[str] = mapped_column(Text)
    source_record_id: Mapped[str | None] = mapped_column(Text)
    input_checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30))
    normalized_payload: Mapped[dict] = mapped_column(json_type, default=dict)
    errors: Mapped[list] = mapped_column(json_type, default=list)
    target_ids: Mapped[dict] = mapped_column(json_type, default=dict)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceEntityLink(Base):
    __tablename__ = "source_entity_link"
    __table_args__ = (UniqueConstraint("company_id", "data_source_id", "target", "source_record_id", name="uq_source_entity_identity"),)
    source_entity_link_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.company_id"))
    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_source.data_source_id"))
    target: Mapped[str] = mapped_column(String(30))
    source_record_id: Mapped[str] = mapped_column(Text)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoice.invoice_id"))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payment.payment_id"))
    bank_transaction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bank_transaction.bank_transaction_id"))
    input_checksum: Mapped[str] = mapped_column(String(64))
    mapping_version: Mapped[int] = mapped_column(Integer)
    normalization_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("normalization_item.normalization_item_id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExtractionResult(Base):
    __tablename__ = "extraction_result"
    extraction_result_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.company_id"))
    raw_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_artifact.raw_artifact_id"))
    provider: Mapped[str] = mapped_column(String(40))
    model_name: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(json_type, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

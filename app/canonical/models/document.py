import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentType(str, enum.Enum):
    INVOICE = "INVOICE"
    CREDIT_NOTE = "CREDIT_NOTE"
    RECEIPT = "RECEIPT"
    OTHER = "OTHER"


class SourceType(str, enum.Enum):
    MANUAL_UPLOAD = "MANUAL_UPLOAD"
    EMAIL = "EMAIL"
    API = "API"
    ERP = "ERP"
    E_INVOICE = "E_INVOICE"


class ProcessingStatus(str, enum.Enum):
    RAW = "RAW"
    EXTRACTED = "EXTRACTED"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (
        UniqueConstraint("company_id", "sha256_hash", name="uq_document_company_sha256_hash"),
        Index("ix_document_company_sha256_hash", "company_id", "sha256_hash"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.company_id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, name="document_type"), nullable=False, default=DocumentType.INVOICE)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, name="source_type"), nullable=False, default=SourceType.MANUAL_UPLOAD)
    processing_status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus, name="processing_status"), nullable=False, default=ProcessingStatus.RAW)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    company = relationship("Company", back_populates="documents")
    invoices = relationship("Invoice", back_populates="document")

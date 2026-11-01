import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InvoiceType(str, enum.Enum):
    PAYABLE = "PAYABLE"
    RECEIVABLE = "RECEIVABLE"


class PaymentStatus(str, enum.Enum):
    UNPAID = "UNPAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERPAID = "OVERPAID"
    UNKNOWN = "UNKNOWN"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class Invoice(Base):
    __tablename__ = "invoice"
    __table_args__ = (
        Index("ix_invoice_company_invoice_number", "company_id", "invoice_number"),
        Index("ix_invoice_company_invoice_date", "company_id", "invoice_date"),
        Index("ix_invoice_company_due_date", "company_id", "due_date"),
        Index("ix_invoice_company_payment_status", "company_id", "payment_status"),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.company_id"), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document.document_id"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("party.party_id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("party.party_id"), index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100))
    customer_reference: Mapped[str | None] = mapped_column(String(100))
    invoice_type: Mapped[InvoiceType] = mapped_column(Enum(InvoiceType, name="invoice_type"), nullable=False)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    delivery_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    shipping_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    balance_due: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    payment_status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, name="payment_status"), nullable=False, default=PaymentStatus.UNKNOWN)
    invoice_status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus, name="invoice_status"), nullable=False, default=InvoiceStatus.UNKNOWN)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company", back_populates="invoices")
    document = relationship("Document", back_populates="invoices")
    supplier = relationship("Party", foreign_keys=[supplier_id], back_populates="supplied_invoices")
    customer = relationship("Party", foreign_keys=[customer_id], back_populates="customer_invoices")
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    payment_allocations = relationship("PaymentAllocation", back_populates="invoice")

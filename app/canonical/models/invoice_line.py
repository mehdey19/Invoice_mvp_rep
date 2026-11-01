import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InvoiceLine(Base):
    __tablename__ = "invoice_line"
    __table_args__ = (Index("ix_invoice_line_invoice_id", "invoice_id"),)

    invoice_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoice.invoice_id"), nullable=False)
    line_number: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    line_subtotal: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    line_tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    invoice = relationship("Invoice", back_populates="lines")

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PartyType(str, enum.Enum):
    SUPPLIER = "SUPPLIER"
    CUSTOMER = "CUSTOMER"
    BOTH = "BOTH"


class Party(Base):
    __tablename__ = "party"

    party_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.company_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    party_type: Mapped[PartyType] = mapped_column(Enum(PartyType, name="party_type"), nullable=False)
    tax_identifier: Mapped[str | None] = mapped_column(String(100))
    registration_identifier: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    billing_address: Mapped[str | None] = mapped_column(Text)
    shipping_address: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    company = relationship("Company", back_populates="parties")
    supplied_invoices = relationship("Invoice", foreign_keys="Invoice.supplier_id", back_populates="supplier")
    customer_invoices = relationship("Invoice", foreign_keys="Invoice.customer_id", back_populates="customer")
    payments = relationship("Payment", back_populates="party")

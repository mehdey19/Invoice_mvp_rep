import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PaymentDirection(str, enum.Enum):
    INCOMING = "INCOMING"
    OUTGOING = "OUTGOING"


class PaymentMethod(str, enum.Enum):
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD = "CARD"
    CASH = "CASH"
    CHECK = "CHECK"
    DIRECT_DEBIT = "DIRECT_DEBIT"
    OTHER = "OTHER"


class PaymentState(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class Payment(Base):
    __tablename__ = "payment"
    __table_args__ = (
        Index("ix_payment_company_payment_date", "company_id", "payment_date"),
        Index("ix_payment_company_party_id", "company_id", "party_id"),
        Index("ix_payment_company_status", "company_id", "status"),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.company_id"), nullable=False)
    party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("party.party_id"))
    payment_direction: Mapped[PaymentDirection] = mapped_column(Enum(PaymentDirection, name="payment_direction"), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(Enum(PaymentMethod, name="payment_method"))
    reference: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[PaymentState] = mapped_column(Enum(PaymentState, name="payment_state"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    company = relationship("Company", back_populates="payments")
    party = relationship("Party", back_populates="payments")
    allocations = relationship("PaymentAllocation", back_populates="payment", cascade="all, delete-orphan")
    bank_transactions = relationship("BankTransaction", back_populates="matched_payment")

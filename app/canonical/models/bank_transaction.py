import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BankTransactionDirection(str, enum.Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class ReconciliationStatus(str, enum.Enum):
    UNMATCHED = "UNMATCHED"
    MATCHED = "MATCHED"
    PARTIALLY_MATCHED = "PARTIALLY_MATCHED"
    IGNORED = "IGNORED"


class BankTransaction(Base):
    __tablename__ = "bank_transaction"
    __table_args__ = (
        Index("ix_bank_transaction_company_transaction_date", "company_id", "transaction_date"),
        Index("ix_bank_transaction_company_reconciliation_status", "company_id", "reconciliation_status"),
        Index("ix_bank_transaction_company_reference", "company_id", "reference"),
    )

    bank_transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.company_id"), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    direction: Mapped[BankTransactionDirection] = mapped_column(Enum(BankTransactionDirection, name="bank_transaction_direction"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(255))
    counterparty_name: Mapped[str | None] = mapped_column(String(255))
    bank_account_reference: Mapped[str | None] = mapped_column(String(255))
    matched_payment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("payment.payment_id"))
    reconciliation_status: Mapped[ReconciliationStatus] = mapped_column(Enum(ReconciliationStatus, name="reconciliation_status"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    company = relationship("Company", back_populates="bank_transactions")
    matched_payment = relationship("Payment", back_populates="bank_transactions")

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Company(Base):
    __tablename__ = "company"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_currency: Mapped[str | None] = mapped_column(String(3))
    country_code: Mapped[str | None] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    parties = relationship("Party", back_populates="company")
    documents = relationship("Document", back_populates="company")
    invoices = relationship("Invoice", back_populates="company")
    payments = relationship("Payment", back_populates="company")
    bank_transactions = relationship("BankTransaction", back_populates="company")

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CompanyRead(ApiModel):
    company_id: UUID
    name: str
    default_currency: str | None
    country_code: str | None
    created_at: datetime


class DocumentRead(ApiModel):
    document_id: UUID
    company_id: UUID
    original_filename: str
    storage_path: str
    mime_type: str
    file_size: int
    sha256_hash: str
    document_type: str
    source_type: str
    processing_status: str
    created_at: datetime


class InvoiceRead(ApiModel):
    invoice_id: UUID
    company_id: UUID
    document_id: UUID | None
    supplier_id: UUID | None
    customer_id: UUID | None
    invoice_number: str | None
    customer_reference: str | None
    invoice_type: str
    invoice_date: date | None
    delivery_date: date | None
    due_date: date | None
    currency: str
    subtotal_amount: Decimal | None
    discount_amount: Decimal | None
    tax_amount: Decimal | None
    shipping_amount: Decimal | None
    total_amount: Decimal | None
    balance_due: Decimal | None
    payment_status: str
    invoice_status: str
    created_at: datetime
    updated_at: datetime


class PaymentRead(ApiModel):
    payment_id: UUID
    company_id: UUID
    party_id: UUID | None
    payment_direction: str
    payment_date: date
    amount: Decimal
    currency: str
    payment_method: str | None
    reference: str | None
    status: str
    created_at: datetime


class BankTransactionRead(ApiModel):
    bank_transaction_id: UUID
    company_id: UUID
    transaction_date: date
    value_date: date | None
    amount: Decimal
    currency: str
    direction: str
    description: str | None
    reference: str | None
    counterparty_name: str | None
    bank_account_reference: str | None
    matched_payment_id: UUID | None
    reconciliation_status: str
    created_at: datetime

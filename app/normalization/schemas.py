from datetime import date
from decimal import Decimal
import re
import unicodedata
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def clean_text(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).split())


class CommonModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PartyData(CommonModel):
    name: str = Field(min_length=1,max_length=255)
    external_id: str | None = None
    tax_identifier: str | None = None
    registration_identifier: str | None = None
    email: str | None = None
    phone: str | None = None
    billing_address: str | None = None
    @field_validator('name','billing_address','phone',mode='before')
    @classmethod
    def clean(cls,v): return clean_text(v) if v is not None else v
    @field_validator('tax_identifier','registration_identifier',mode='before')
    @classmethod
    def identifier(cls,v): return re.sub(r'\s+','',clean_text(v)).upper() if v is not None else None
    @field_validator('email',mode='before')
    @classmethod
    def email_clean(cls,v):
        if v is None: return None
        v=clean_text(v).lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v): raise ValueError('Invalid email address')
        return v


class InvoiceLineData(CommonModel):
    description: str = Field(min_length=1)
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    tax_rate: Decimal | None = None
    line_subtotal: Decimal | None = None
    line_tax_amount: Decimal | None = None
    line_total: Decimal | None = None


class EntityData(CommonModel):
    company_id: UUID
    currency: str
    provenance: dict
    @field_validator('currency',mode='before')
    @classmethod
    def currency_clean(cls,v):
        v=clean_text(v).upper()
        v={'DH':'MAD','DHS':'MAD','DIRHAM':'MAD','EURO':'EUR','EUROS':'EUR'}.get(v,v)
        if not re.fullmatch('[A-Z]{3}',v): raise ValueError('Currency must be a three-letter code')
        return v


class NormalizedInvoice(EntityData):
    invoice_number: str = Field(min_length=1,max_length=100)
    invoice_type: Literal['PAYABLE','RECEIVABLE']
    invoice_date: date
    due_date: date | None = None
    delivery_date: date | None = None
    customer_reference: str | None = None
    subtotal_amount: Decimal | None = None
    discount_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    shipping_amount: Decimal | None = None
    total_amount: Decimal = Field(ge=0)
    balance_due: Decimal | None = None
    payment_status: Literal['UNPAID','PARTIALLY_PAID','PAID','OVERPAID','UNKNOWN']='UNKNOWN'
    invoice_status: Literal['DRAFT','VALIDATED','CANCELLED','UNKNOWN']='UNKNOWN'
    supplier: PartyData | None = None
    customer: PartyData | None = None
    lines: list[InvoiceLineData] = Field(default_factory=list)
    @field_validator('invoice_number',mode='before')
    @classmethod
    def invoice_number_clean(cls,v): return clean_text(v).upper()
    @model_validator(mode='after')
    def totals(self):
        if self.subtotal_amount is not None and self.tax_amount is not None:
            expected=self.subtotal_amount+self.tax_amount-(self.discount_amount or 0)+(self.shipping_amount or 0)
            if abs(expected-self.total_amount)>Decimal('.01'): raise ValueError('Invoice amounts do not balance')
        if self.due_date and self.due_date<self.invoice_date: raise ValueError('Due date precedes invoice date')
        return self


class NormalizedPayment(EntityData):
    payment_date: date
    payment_direction: Literal['INCOMING','OUTGOING']
    amount: Decimal = Field(ge=0)
    payment_method: Literal['BANK_TRANSFER','CARD','CASH','CHECK','DIRECT_DEBIT','OTHER'] | None = None
    status: Literal['PENDING','CONFIRMED','CANCELLED']
    reference: str | None = None
    party: PartyData | None = None


class NormalizedBankTransaction(EntityData):
    transaction_date: date
    value_date: date | None = None
    amount: Decimal = Field(ge=0)
    direction: Literal['CREDIT','DEBIT']
    description: str | None = None
    reference: str | None = None
    counterparty_name: str | None = None
    bank_account_reference: str | None = None

MODELS={'INVOICE':NormalizedInvoice,'PAYMENT':NormalizedPayment,'BANK_TRANSACTION':NormalizedBankTransaction}

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.bank_transaction import BankTransaction
from app.models.document import Document
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.schemas.common import BankTransactionRead, DocumentRead, InvoiceRead, PaymentRead

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    return list(db.scalars(select(Document).order_by(Document.created_at.desc(), Document.original_filename)))


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: UUID, db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/invoices", response_model=list[InvoiceRead])
def list_invoices(db: Session = Depends(get_db)) -> list[Invoice]:
    return list(db.scalars(select(Invoice).order_by(Invoice.created_at.desc())))


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead)
def get_invoice(invoice_id: UUID, db: Session = Depends(get_db)) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.get("/payments", response_model=list[PaymentRead])
def list_payments(db: Session = Depends(get_db)) -> list[Payment]:
    return list(db.scalars(select(Payment).order_by(Payment.payment_date.desc(), Payment.created_at.desc())))


@router.get("/bank-transactions", response_model=list[BankTransactionRead])
def list_bank_transactions(db: Session = Depends(get_db)) -> list[BankTransaction]:
    return list(db.scalars(select(BankTransaction).order_by(BankTransaction.transaction_date.desc(), BankTransaction.created_at.desc())))

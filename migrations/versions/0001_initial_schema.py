"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-04 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    party_type = postgresql.ENUM("SUPPLIER", "CUSTOMER", "BOTH", name="party_type")
    document_type = postgresql.ENUM("INVOICE", "CREDIT_NOTE", "RECEIPT", "OTHER", name="document_type")
    source_type = postgresql.ENUM("MANUAL_UPLOAD", "EMAIL", "API", "ERP", "E_INVOICE", name="source_type")
    processing_status = postgresql.ENUM("RAW", "EXTRACTED", "VALIDATED", "FAILED", name="processing_status")
    invoice_type = postgresql.ENUM("PAYABLE", "RECEIVABLE", name="invoice_type")
    payment_status = postgresql.ENUM("UNPAID", "PARTIALLY_PAID", "PAID", "OVERPAID", "UNKNOWN", name="payment_status")
    invoice_status = postgresql.ENUM("DRAFT", "VALIDATED", "CANCELLED", "UNKNOWN", name="invoice_status")
    payment_direction = postgresql.ENUM("INCOMING", "OUTGOING", name="payment_direction")
    payment_method = postgresql.ENUM("BANK_TRANSFER", "CARD", "CASH", "CHECK", "DIRECT_DEBIT", "OTHER", name="payment_method")
    payment_state = postgresql.ENUM("PENDING", "CONFIRMED", "CANCELLED", name="payment_state")
    bank_transaction_direction = postgresql.ENUM("CREDIT", "DEBIT", name="bank_transaction_direction")
    reconciliation_status = postgresql.ENUM("UNMATCHED", "MATCHED", "PARTIALLY_MATCHED", "IGNORED", name="reconciliation_status")

    op.create_table(
        "company",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("company_id", name=op.f("pk_company")),
    )
    op.create_table(
        "party",
        sa.Column("party_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("party_type", party_type, nullable=False),
        sa.Column("tax_identifier", sa.String(length=100), nullable=True),
        sa.Column("registration_identifier", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("billing_address", sa.Text(), nullable=True),
        sa.Column("shipping_address", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.company_id"], name=op.f("fk_party_company_id_company")),
        sa.PrimaryKeyConstraint("party_id", name=op.f("pk_party")),
    )
    op.create_index(op.f("ix_party_company_id"), "party", ["company_id"], unique=False)
    op.create_table(
        "document",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("storage_path", sa.String(length=1000), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("document_type", document_type, nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("processing_status", processing_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.company_id"], name=op.f("fk_document_company_id_company")),
        sa.PrimaryKeyConstraint("document_id", name=op.f("pk_document")),
        sa.UniqueConstraint("company_id", "sha256_hash", name="uq_document_company_sha256_hash"),
    )
    op.create_index("ix_document_company_sha256_hash", "document", ["company_id", "sha256_hash"], unique=False)
    op.create_table(
        "invoice",
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invoice_number", sa.String(length=100), nullable=True),
        sa.Column("customer_reference", sa.String(length=100), nullable=True),
        sa.Column("invoice_type", invoice_type, nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("discount_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("tax_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("shipping_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("balance_due", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("payment_status", payment_status, nullable=False),
        sa.Column("invoice_status", invoice_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.company_id"], name=op.f("fk_invoice_company_id_company")),
        sa.ForeignKeyConstraint(["customer_id"], ["party.party_id"], name=op.f("fk_invoice_customer_id_party")),
        sa.ForeignKeyConstraint(["document_id"], ["document.document_id"], name=op.f("fk_invoice_document_id_document")),
        sa.ForeignKeyConstraint(["supplier_id"], ["party.party_id"], name=op.f("fk_invoice_supplier_id_party")),
        sa.PrimaryKeyConstraint("invoice_id", name=op.f("pk_invoice")),
    )
    op.create_index("ix_invoice_company_due_date", "invoice", ["company_id", "due_date"], unique=False)
    op.create_index("ix_invoice_company_invoice_date", "invoice", ["company_id", "invoice_date"], unique=False)
    op.create_index("ix_invoice_company_invoice_number", "invoice", ["company_id", "invoice_number"], unique=False)
    op.create_index("ix_invoice_company_payment_status", "invoice", ["company_id", "payment_status"], unique=False)
    op.create_index(op.f("ix_invoice_customer_id"), "invoice", ["customer_id"], unique=False)
    op.create_index(op.f("ix_invoice_supplier_id"), "invoice", ["supplier_id"], unique=False)
    op.create_table(
        "payment",
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("party_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payment_direction", payment_direction, nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payment_method", payment_method, nullable=True),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("status", payment_state, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.company_id"], name=op.f("fk_payment_company_id_company")),
        sa.ForeignKeyConstraint(["party_id"], ["party.party_id"], name=op.f("fk_payment_party_id_party")),
        sa.PrimaryKeyConstraint("payment_id", name=op.f("pk_payment")),
    )
    op.create_index("ix_payment_company_party_id", "payment", ["company_id", "party_id"], unique=False)
    op.create_index("ix_payment_company_payment_date", "payment", ["company_id", "payment_date"], unique=False)
    op.create_index("ix_payment_company_status", "payment", ["company_id", "status"], unique=False)
    op.create_table(
        "invoice_line",
        sa.Column("invoice_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("tax_rate", sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column("line_subtotal", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("line_tax_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("line_total", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoice.invoice_id"], name=op.f("fk_invoice_line_invoice_id_invoice")),
        sa.PrimaryKeyConstraint("invoice_line_id", name=op.f("pk_invoice_line")),
    )
    op.create_index("ix_invoice_line_invoice_id", "invoice_line", ["invoice_id"], unique=False)
    op.create_table(
        "payment_allocation",
        sa.Column("payment_allocation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoice.invoice_id"], name=op.f("fk_payment_allocation_invoice_id_invoice")),
        sa.ForeignKeyConstraint(["payment_id"], ["payment.payment_id"], name=op.f("fk_payment_allocation_payment_id_payment")),
        sa.PrimaryKeyConstraint("payment_allocation_id", name=op.f("pk_payment_allocation")),
        sa.UniqueConstraint("payment_id", "invoice_id", name="uq_payment_allocation_payment_invoice"),
    )
    op.create_index("ix_payment_allocation_invoice_id", "payment_allocation", ["invoice_id"], unique=False)
    op.create_index("ix_payment_allocation_payment_id", "payment_allocation", ["payment_id"], unique=False)
    op.create_table(
        "bank_transaction",
        sa.Column("bank_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("direction", bank_transaction_direction, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("counterparty_name", sa.String(length=255), nullable=True),
        sa.Column("bank_account_reference", sa.String(length=255), nullable=True),
        sa.Column("matched_payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reconciliation_status", reconciliation_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.company_id"], name=op.f("fk_bank_transaction_company_id_company")),
        sa.ForeignKeyConstraint(["matched_payment_id"], ["payment.payment_id"], name=op.f("fk_bank_transaction_matched_payment_id_payment")),
        sa.PrimaryKeyConstraint("bank_transaction_id", name=op.f("pk_bank_transaction")),
    )
    op.create_index("ix_bank_transaction_company_reconciliation_status", "bank_transaction", ["company_id", "reconciliation_status"], unique=False)
    op.create_index("ix_bank_transaction_company_reference", "bank_transaction", ["company_id", "reference"], unique=False)
    op.create_index("ix_bank_transaction_company_transaction_date", "bank_transaction", ["company_id", "transaction_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bank_transaction_company_transaction_date", table_name="bank_transaction")
    op.drop_index("ix_bank_transaction_company_reference", table_name="bank_transaction")
    op.drop_index("ix_bank_transaction_company_reconciliation_status", table_name="bank_transaction")
    op.drop_table("bank_transaction")
    op.drop_index("ix_payment_allocation_payment_id", table_name="payment_allocation")
    op.drop_index("ix_payment_allocation_invoice_id", table_name="payment_allocation")
    op.drop_table("payment_allocation")
    op.drop_index("ix_invoice_line_invoice_id", table_name="invoice_line")
    op.drop_table("invoice_line")
    op.drop_index("ix_payment_company_status", table_name="payment")
    op.drop_index("ix_payment_company_payment_date", table_name="payment")
    op.drop_index("ix_payment_company_party_id", table_name="payment")
    op.drop_table("payment")
    op.drop_index(op.f("ix_invoice_supplier_id"), table_name="invoice")
    op.drop_index(op.f("ix_invoice_customer_id"), table_name="invoice")
    op.drop_index("ix_invoice_company_payment_status", table_name="invoice")
    op.drop_index("ix_invoice_company_invoice_number", table_name="invoice")
    op.drop_index("ix_invoice_company_invoice_date", table_name="invoice")
    op.drop_index("ix_invoice_company_due_date", table_name="invoice")
    op.drop_table("invoice")
    op.drop_index("ix_document_company_sha256_hash", table_name="document")
    op.drop_table("document")
    op.drop_index(op.f("ix_party_company_id"), table_name="party")
    op.drop_table("party")
    op.drop_table("company")

    bind = op.get_bind()
    for enum_name in (
        "reconciliation_status",
        "bank_transaction_direction",
        "payment_state",
        "payment_method",
        "payment_direction",
        "invoice_status",
        "payment_status",
        "invoice_type",
        "processing_status",
        "source_type",
        "document_type",
        "party_type",
    ):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)

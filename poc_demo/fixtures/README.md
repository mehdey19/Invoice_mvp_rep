# Invoice normalization — synthetic inputs (not production invoices)

Each file intentionally represents a *different source schema*. Values, organizations, identifiers, and VAT rates are **fictitious**, not tax or regulatory guidance.

| File | Meaning | Raw format | Target after normalization |
|---|---|---|---|
| 01_sales_invoice_csv.csv | Two issued customer invoices (RECEIVABLE) | French semicolon CSV, comma decimals | invoice / party |
| 02_purchase_goods_invoice_json.json | Supplier goods invoice (PAYABLE) | nested JSON with multiple lines | party / invoice / invoice_line |
| 03_service_invoice_api.json | Service invoice from hypothetical REST API | nested JSON response | party / invoice / invoice_line |
| 04_foreign_supplier_invoice_xml.xml | EUR supplier invoice (PAYABLE) | illustrative proprietary XML (not UBL) | party / invoice / invoice_line, EUR maintained |
| 05_credit_note_avoir.json | Supplier credit note with original invoice link | JSON, negative amount | credit note concept needs modeling before posting; don't blindly treat as ordinary invoice |
| 06_scanned_invoice_ml_extraction.json | Illustrative output of an *existing* ML extractor | JSON containing confidence scores | review then party / invoice / invoice_line |
| 07_bank_transactions_csv.csv | Two statement transactions | CSV | bank_transaction (not payment automatically) |

## Recommended intermediate candidate format

```json
{
  "source_artifact_id": "<raw_artifact UUID>",
  "document_kind": "INVOICE",
  "flow": "PAYABLE",
  "invoice_number": "FA-678",
  "dates": {"issued": "2026-10-05", "due": "2026-11-04"},
  "seller": {"name": "Fournitures Casablanca SARL", "tax_identifier": "001111222000033"},
  "buyer": {"name": "Demo Company"},
  "currency": "MAD",
  "lines": [
    {"description": "Cartons d'emballage", "quantity": "10", "unit_price": "100.00", "tax_rate_percent": "20", "net_amount": "1000.00"},
    {"description": "Etiquettes", "quantity": "5", "unit_price": "40.00", "tax_rate_percent": "20", "net_amount": "200.00"}
  ],
  "totals": {"subtotal": "1200.00", "tax": "240.00", "total": "1440.00"},
  "original_invoice_number": null,
  "review_required": false
}
```

This is an illustration, not a final DB migration. Existing `invoice.invoice_type` holds PAYABLE/RECEIVABLE, *not* INVOICE/CREDIT_NOTE, so keep `document_kind` separate; use existing `document.document_type` for document classification where appropriate.

## Rules to decide before coding

- Merchant/customer identity: use IDs (ICE/IF, provider party ID) where available; names alone can collide.
- Dates: known dates normalize to YYYY-MM-DD; preserve original value when uncertain.
- Money: decimal strings; never binary floating-point for amounts.
- Currency: preserve invoice currency (EUR stays EUR); exchange rates must not be invented.
- Totals: verify subtotal + tax + shipping - discount against total within a defined rounding tolerance, but do not reject legitimate invoices solely because breakdown details are absent.
- Credit notes: reference original invoice, preserve sign convention with unambiguous `document_kind`, decide ledger treatment separately.
- Scanned documents: extraction confidence and missing information require review; no invented fields.
- Bank transactions: map to bank_transaction first; do not create a payment merely from a transfer line.

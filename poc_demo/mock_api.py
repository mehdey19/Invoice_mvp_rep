"""Deterministic provider simulator. Run: python -m poc_demo.mock_api."""
import json
import os
from typing import Literal
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from poc_demo.fixtures.generate import ROOT, invoices, payments, bank_transactions, csv_bytes, pdf_bytes

app = FastAPI(title='Synthetic invoice, payment and bank systems')
Scenario = Literal['success', 'empty', 'paginated', 'duplicates', 'new', 'updated', 'http500', 'http429', 'malformed']


def respond(rows, scenario, page, page_size):
    if scenario == 'http500':
        return Response('Synthetic provider failure', status_code=500)
    if scenario == 'http429':
        return Response('Synthetic rate limit', status_code=429, headers={'Retry-After': '1'})
    if scenario == 'malformed':
        return Response(b'{"items": [broken', media_type='application/json')
    if scenario == 'empty':
        rows = []
    if scenario == 'duplicates' and rows:
        rows = rows + [rows[0]]
    next_page = None
    if scenario == 'paginated':
        start = (page-1)*page_size
        next_page = page+1 if start+page_size < len(rows) else None
        rows = rows[start:start+page_size]
    return {'items': rows, 'next_page': next_page}


@app.get('/mock/erp/invoices.csv')
def invoice_csv():
    return Response(csv_bytes(invoices()), media_type='text/csv')


@app.get('/mock/erp/invoices.xml')
def invoice_xml():
    return Response((ROOT/'xml/invoice_sample.xml').read_bytes(), media_type='application/xml')


@app.get('/mock/erp/invoices')
def invoice_list(scenario: Scenario = 'success', variant: Literal['a', 'b'] = 'a',
                 page: int = Query(1, ge=1), page_size: int = Query(2, ge=1, le=100)):
    return respond(invoices(variant, scenario), scenario, page, page_size)


@app.get('/mock/erp/invoices/{invoice_id}')
def invoice_detail(invoice_id: str):
    for row in invoices():
        if row['invoice_id'] == invoice_id:
            return row
    raise HTTPException(404, 'Synthetic invoice not found')


@app.get('/mock/erp/suppliers')
def suppliers():
    return {'items': [{'id': 'SUP-1', 'name': 'Synthetic ERP Supplier', 'country': 'MA'}]}


@app.get('/mock/erp/customers')
def customers():
    return {'items': [{'id': f'CUS-{i}', 'name': f'Synthetic Atlas {i} SARL'} for i in range(1, 4)]}


@app.get('/mock/payments/transactions')
def payment_list(scenario: Scenario = 'success', page: int = Query(1, ge=1), page_size: int = Query(2, ge=1, le=100)):
    return respond(payments(), scenario, page, page_size)


@app.get('/mock/payments/refunds')
def refund_list(scenario: Scenario = 'success', page: int = Query(1, ge=1), page_size: int = Query(2, ge=1, le=100)):
    return respond([{'refund_id': 'REF-1', 'payment_id': 'PAY-4', 'date': '2026-10-15', 'amount': 2400,
                     'currency': 'MAD', 'status': 'refunded'}], scenario, page, page_size)


@app.get('/mock/bank/transactions.csv')
def bank_csv():
    return Response(csv_bytes(bank_transactions()), media_type='text/csv')


@app.get('/mock/bank/transactions')
def bank_list(scenario: Scenario = 'success', page: int = Query(1, ge=1), page_size: int = Query(2, ge=1, le=100)):
    return respond(bank_transactions(), scenario, page, page_size)


@app.get('/mock/bank/accounts')
def accounts():
    return {'items': [{'account_id': 'DEMO-MA-ACCOUNT-001', 'currency': 'MAD', 'name': 'Synthetic operating account'}]}


@app.get('/mock/documents/invoice-sample.pdf')
def invoice_pdf():
    return Response(pdf_bytes(), media_type='application/pdf')


@app.get('/api/invoices')
def legacy_invoices():
    return {'invoices': [dict(id=f'api-{i:03}', number=f'ERP-2026-{i}', amount_total=str(i*1200), currency='MAD') for i in (1, 2)]}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=os.environ.get('POC_MOCK_HOST', '127.0.0.1'), port=9090)

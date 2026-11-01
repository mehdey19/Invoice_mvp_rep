"""Generate harmless deterministic fixtures; existing customer images are read-only."""
import base64
import csv
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def invoices(variant='a', scenario='success'):
    rows = []
    for i in range(1, 5 if scenario == 'new' else 4):
        subtotal = 1000 * i
        total = subtotal * 1.2 + (100 if scenario == 'updated' and i == 1 else 0)
        if variant == 'b':
            rows.append({'document': {'reference': f'F-2026-{100+i}', 'issued_at': '2026-10-10', 'due_at': '2026-11-10'},
                         'partner': {'name': f'Synthetic Atlas {i} SARL'}, 'supplier': {'name': 'Synthetic ERP Supplier'},
                         'amounts': {'subtotal': subtotal, 'tax': total-subtotal, 'total_including_tax': total},
                         'currency_code': 'MAD', 'payment_status': 'PAID' if i == 2 else 'UNPAID'})
        else:
            rows.append({'invoice_id': f'INV-{1000+i}', 'invoice_number': f'INV-{1000+i}', 'date': '2026-10-10',
                         'due_date': '2026-11-10', 'customer': f'Synthetic Atlas {i} SARL', 'supplier': 'Synthetic ERP Supplier',
                         'subtotal': subtotal, 'taxes': total-subtotal, 'total': total, 'currency': 'MAD',
                         'payment_status': 'PAID' if i == 2 else 'UNPAID'})
    return rows


def payments():
    return [{'payment_id': f'PAY-{i}', 'transaction_date': f'2026-10-{10+i}', 'amount': i*600,
             'currency': 'MAD', 'method': ['card', 'bank_transfer'][i % 2], 'status': status,
             'counterparty': f'Synthetic Customer {i}', 'reference': f'INV-{1000+i}'}
            for i, status in enumerate(['successful', 'pending', 'failed', 'refunded'], 1)]


def bank_transactions():
    return [{'transaction_id': f'BANK-{i}', 'booking_date': '2026-10-12', 'value_date': '2026-10-13',
             'amount': i*500, 'currency': 'MAD', 'direction': 'CREDIT' if i % 2 else 'DEBIT',
             'description': f'Synthetic bank transfer {i}', 'counterparty': f'Synthetic Partner {i}',
             'account_reference': 'DEMO-MA-ACCOUNT-001'} for i in range(1, 4)]


def csv_bytes(rows, delimiter=','):
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), delimiter=delimiter)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode('utf-8')


def pdf_bytes():
    content = b'BT /F1 18 Tf 50 750 Td (SYNTHETIC INVOICE INV-1001 - MAD 1200.00) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream']
    out = b'%PDF-1.4\n'
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    start = len(out)
    out += b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{n:010} 00000 n \n'.encode() for n in offsets[1:])
    return out+f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()


def generate():
    fixtures = {
        'csv/invoices_english.csv': csv_bytes(invoices()),
        'csv/invoices_french.csv': csv_bytes([{'Numero': r['invoice_id'], 'Date': r['date'], 'Client': r['customer'],
                                             'Montant_TTC': r['total'], 'Devise': r['currency']} for r in invoices()], ';'),
        'csv/payments.csv': csv_bytes(payments()), 'csv/bank_transactions.csv': csv_bytes(bank_transactions()),
        'json/invoices.json': json.dumps(invoices(), indent=2).encode(),
        'json/payments.json': json.dumps(payments(), indent=2).encode(),
        'xml/invoice_sample.xml': b'<?xml version="1.0" encoding="UTF-8"?>\n<invoice><reference>INV-1001</reference><customer>Synthetic Atlas SARL</customer><currency>MAD</currency><total>1200.00</total></invoice>\n',
        'documents/invoice_sample.pdf': pdf_bytes(),
        'images/synthetic.png': base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='),
    }
    for name, payload in fixtures.items():
        path = ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != payload:
            path.write_bytes(payload)


if __name__ == '__main__':
    generate()

"""Idempotent source registration. No existing sources or core records are overwritten."""
import argparse
import os
from uuid import UUID, uuid5, NAMESPACE_URL
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert
from app.config import get_settings
from app.models.company import Company
from app.models.acquisition import DataSource
from poc_demo.fixtures.generate import generate
from app.acquisition.settings import mock_base, images_dir
from app.acquisition.services.source_service import validate_source

DEMO_COMPANY = UUID('aef33b6b-773c-43cd-ab86-6f3882f2092a')
PREFIX = 'poc_w1_'


def examples():
    rows = []
    for code, path, fmt, entity in [
        ('invoices_fr', 'csv/invoices_french.csv', 'CSV', 'INVOICE'),
        ('invoices_en', 'csv/invoices_english.csv', 'CSV', 'INVOICE'),
        ('bank_csv', 'csv/bank_transactions.csv', 'CSV', 'BANK_TRANSACTION'),
        ('payments_csv', 'csv/payments.csv', 'CSV', 'PAYMENT'),
        ('invoices_json', 'json/invoices.json', 'JSON', 'INVOICE'),
        ('payments_json', 'json/payments.json', 'JSON', 'PAYMENT'),
        ('xml', 'xml/invoice_sample.xml', 'XML', 'INVOICE'),
        ('pdf', 'documents/invoice_sample.pdf', 'PDF', 'INVOICE'),
        ('png', 'images/synthetic.png', 'PNG', 'INVOICE'),
        ('purchase_detailed_json', '../02_purchase_goods_invoice_json.json', 'JSON', 'INVOICE'),
        ('sales_detailed_csv', '../01_sales_invoice_csv.csv', 'CSV', 'INVOICE'),
        ('foreign_supplier_xml', '../04_foreign_supplier_invoice_xml.xml', 'XML', 'INVOICE'),
    ]:
        rows.append(dict(source_code=PREFIX+code, name='Week 1 '+code.replace('_',' '), transport='FILE', data_format=fmt,
                         entity_type=entity, config={'path': 'poc_demo/fixtures/'+path.replace('../',''), **({'delimiter': ';'} if code in {'invoices_fr','sales_detailed_csv'} else {})}))
    for code, endpoint, fmt, entity, identity in [
        ('erp_a', '/mock/erp/invoices', 'JSON', 'INVOICE', 'invoice_id'),
        ('erp_b', '/mock/erp/invoices?variant=b', 'JSON', 'INVOICE', 'document.reference'),
        ('payments_api', '/mock/payments/transactions', 'JSON', 'PAYMENT', 'payment_id'),
        ('refunds_api', '/mock/payments/refunds', 'JSON', 'PAYMENT', 'refund_id'),
        ('bank_api', '/mock/bank/transactions', 'JSON', 'BANK_TRANSACTION', 'transaction_id'),
        ('http_csv', '/mock/erp/invoices.csv', 'CSV', 'INVOICE', None),
        ('http_xml', '/mock/erp/invoices.xml', 'XML', 'INVOICE', None),
        ('http_pdf', '/mock/documents/invoice-sample.pdf', 'PDF', 'INVOICE', None),
    ]:
        config = {'url': mock_base()+endpoint}
        if identity:
            config.update(records_path='items', external_id_path=identity)
        rows.append(dict(source_code=PREFIX+code, name='Week 1 '+code.replace('_',' '), transport='HTTP_GET',
                         data_format=fmt, entity_type=entity, config=config))
    if images_dir().is_dir():
        rows.append(dict(source_code=PREFIX+'invoice_images', name='Week 1 existing invoice images', transport='DIRECTORY',
                         data_format='IMAGE', entity_type='INVOICE', config={'env_dir':'POC_IMAGES_DIR'}))
    return rows


def seed(engine, company_id=DEMO_COMPANY):
    generate()
    company_id = UUID(str(company_id))
    with engine.begin() as conn:
        exists = conn.execute(select(Company.company_id).where(Company.company_id == company_id)).first()
        if not exists:
            if company_id != DEMO_COMPANY:
                raise ValueError('Only the known Demo Company may be created by seed; other companies must already exist')
            conn.execute(Company.__table__.insert().values(company_id=company_id, name='Demo Company', default_currency='MAD', country_code='MA'))
        for example in examples():
            values = validate_source(example)
            conn.execute(insert(DataSource.__table__).values(**values, company_id=company_id,
                data_source_id=uuid5(NAMESPACE_URL, str(company_id)+':'+values['source_code']))
                .on_conflict_do_nothing(index_elements=['company_id','source_code']))
    return len(examples())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--company-id', type=UUID, default=DEMO_COMPANY)
    args = parser.parse_args()
    from app.database import create_app_engine
    engine = create_app_engine()
    count = seed(engine, args.company_id)
    print(f'Ensured {count} Week 1 source registrations for {args.company_id}; existing sources preserved.')


if __name__ == '__main__':
    main()

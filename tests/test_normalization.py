from copy import deepcopy
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select,func,update
from app.canonical.models import Invoice,InvoiceLine,Party,Document,Payment,BankTransaction
from app.integration_pipeline.models import RawArtifact,NormalizationItem,SourceEntityLink
from app.acquisition.services.source_service import save_source
from app.acquisition.services.acquisition_service import execute_source
from app.acquisition.settings import FIXTURES
from app.normalization.profiles import example_profile,save_profile,get_profile
from app.normalization.mapper import normalize,validate_profile
from app.normalization.service import preview_source,apply_run


def source(engine,cid,**overrides):
    data=dict(source_code='poc_w1_test_'+uuid4().hex,name='Synthetic normalization source',transport='FILE',data_format='JSON',
              entity_type='INVOICE',config={'path':str(FIXTURES/'json/invoices.json')})
    data.update(overrides)
    s=save_source(engine,cid,data);profile=example_profile(s);save_profile(engine,cid,s['data_source_id'],profile)
    return s


def preview_apply(engine,cid,s):
    preview=preview_source(engine,cid,s['data_source_id'])
    return apply_run(engine,cid,preview['normalization_run_id'])


def test_invoice_documents_parties_and_replay(db_engine,company):
    s=source(db_engine,company)
    assert execute_source(db_engine,s)['status']=='SUCCEEDED'
    with db_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Document).where(Document.company_id==company))==1
    first=preview_source(db_engine,company,s['data_source_id'])
    assert first['valid_count']==3
    with db_engine.connect() as conn: assert conn.scalar(select(func.count()).select_from(Invoice).where(Invoice.company_id==company))==0
    applied=apply_run(db_engine,company,first['normalization_run_id'])
    assert applied['applied_count']==3 and applied['error_count']==0,applied
    replay=preview_apply(db_engine,company,s)
    assert replay['skipped_count']==3 and replay['applied_count']==0
    with db_engine.connect() as conn:
        rows=conn.execute(select(Invoice.__table__).where(Invoice.company_id==company)).mappings().all()
        assert len(rows)==3 and all(r['document_id'] for r in rows)
        assert rows[0]['total_amount'] in (Decimal('1200'),Decimal('2400'),Decimal('3600'))
        assert conn.scalar(select(func.count()).select_from(Party).where(Party.company_id==company))==4
    assert all(i['normalized_payload']['provenance']['mapping_version']==1 for i in applied['items'])


def test_purchase_lines_and_french_amounts(db_engine,company):
    s=source(db_engine,company,source_code='poc_w1_purchase_test',config={'path':str(FIXTURES/'02_purchase_goods_invoice_json.json')})
    execute_source(db_engine,s);result=preview_apply(db_engine,company,s)
    assert result['applied_count']==1,result
    with db_engine.connect() as conn:
        invoice=conn.execute(select(Invoice.__table__).where(Invoice.company_id==company)).mappings().one()
        assert invoice['invoice_type'].value=='PAYABLE' and invoice['total_amount']==Decimal('1440')
        assert conn.scalar(select(func.count()).select_from(InvoiceLine).where(InvoiceLine.invoice_id==invoice['invoice_id']))==2
        assert conn.scalar(select(Party.tax_identifier).where(Party.party_id==invoice['supplier_id']))=='001111222000033'


def test_payments_and_bank_keep_distinct_models(db_engine,company):
    p=source(db_engine,company,entity_type='PAYMENT',config={'path':str(FIXTURES/'json/payments.json')})
    execute_source(db_engine,p);payments=preview_apply(db_engine,company,p)
    assert payments['applied_count']==2 and payments['error_count']==2,payments
    b=source(db_engine,company,entity_type='BANK_TRANSACTION',data_format='CSV',config={'path':str(FIXTURES/'csv/bank_transactions.csv')})
    execute_source(db_engine,b);bank=preview_apply(db_engine,company,b)
    assert bank['applied_count']==3,bank
    with db_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Payment).where(Payment.company_id==company))==2
        assert conn.scalar(select(func.count()).select_from(BankTransaction).where(BankTransaction.company_id==company))==3
        assert all(x is None for x in conn.scalars(select(BankTransaction.matched_payment_id).where(BankTransaction.company_id==company)))


def test_updates_require_approval_and_keep_raw_history(db_engine,company,mock_http):
    s=source(db_engine,company,transport='HTTP_GET',config={'url':'http://localhost:9090/mock/erp/invoices','records_path':'items','external_id_path':'invoice_id'})
    execute_source(db_engine,s);assert preview_apply(db_engine,company,s)['applied_count']==3
    s['config']['url']+='?scenario=updated';save_source(db_engine,company,s,s['data_source_id'])
    execute_source(db_engine,s)
    blocked=preview_apply(db_engine,company,s)
    assert blocked['error_count']==1 and blocked['skipped_count']==2
    preview=preview_source(db_engine,company,s['data_source_id'])
    applied=apply_run(db_engine,company,preview['normalization_run_id'],allow_updates=True)
    assert applied['applied_count']==1,applied
    with db_engine.connect() as conn:
        assert conn.scalar(select(Invoice.total_amount).where(Invoice.company_id==company,Invoice.invoice_number=='INV-1001'))==Decimal('1300')
        assert conn.scalar(select(func.count()).select_from(RawArtifact).where(RawArtifact.company_id==company))==6


def test_cross_source_duplicate_is_reviewed(db_engine,company):
    a=source(db_engine,company);b=source(db_engine,company)
    execute_source(db_engine,a);execute_source(db_engine,b)
    assert preview_apply(db_engine,company,a)['applied_count']==3
    second=preview_apply(db_engine,company,b)
    assert second['applied_count']==0 and second['error_count']==3
    with db_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Invoice).where(Invoice.company_id==company))==3


def test_profile_versions_are_immutable(db_engine,company):
    s=source(db_engine,company);profile=get_profile(db_engine,company,s['data_source_id'])['mapping']
    profile['fields']['invoice_type']['constant']='PAYABLE'
    with pytest.raises(ValueError,match='immutable'): save_profile(db_engine,company,s['data_source_id'],profile)
    profile['version']=2
    assert save_profile(db_engine,company,s['data_source_id'],profile)['version']==2


@pytest.mark.parametrize('field,value',[('invoice_number','  inv-001  '),('currency',' dh '),('total_amount','1 234,50')])
def test_common_normalization_rules(field,value):
    from app.normalization.profiles import rule
    mapping={'target':'INVOICE','version':1,'fields':{'invoice_number':{'constant':'INV-001'},'invoice_date':{'constant':'2026-10-10'},
        'currency':{'constant':'MAD'},'invoice_type':{'constant':'RECEIVABLE'},'total_amount':{'constant':'1234.50'}}}
    mapping['fields'][field]=rule(['input'],'decimal' if field=='total_amount' else 'trim',decimal_separator=',',thousands_separator=' ')
    record,errors=normalize({'input':value},mapping,uuid4(),{})
    assert not errors,errors
    assert record[field]=={'invoice_number':'INV-001','currency':'MAD','total_amount':'1234.50'}[field]


def test_conflicting_aliases_and_reserved_fields():
    mapping={'target':'INVOICE','version':1,'fields':{'invoice_number':{'paths':['Numero','number']}}}
    _,errors=normalize({'Numero':'A','number':'B'},mapping,uuid4(),{})
    assert errors and 'conflicting' in errors[0]['message']
    mapping['fields']['company_id']={'constant':str(uuid4())}
    with pytest.raises(ValueError,match='reserved'): validate_profile(mapping)


def test_xml_foreign_invoice(db_engine,company):
    s=source(db_engine,company,source_code='poc_w1_foreign_test',data_format='XML',config={'path':str(FIXTURES/'04_foreign_supplier_invoice_xml.xml')})
    execute_source(db_engine,s);run=preview_apply(db_engine,company,s)
    assert run['applied_count']==1,run
    assert run['items'][0]['normalized_payload']['currency']=='EUR'


def test_xml_external_entities_are_rejected(db_engine,company,tmp_path,monkeypatch):
    monkeypatch.setenv('POC_IMAGES_DIR',str(tmp_path))
    path=tmp_path/'bad.xml';path.write_text('<!DOCTYPE x [<!ENTITY steal SYSTEM "file:///etc/passwd">]><x>&steal;</x>')
    s=source(db_engine,company,data_format='XML',config={'path':str(path)})
    execute_source(db_engine,s)
    run=preview_source(db_engine,company,s['data_source_id'])
    assert run['error_count']==1 and 'EntitiesForbidden' in run['items'][0]['errors'][0]['message']


def test_image_requires_extraction_then_loads_reviewed_fields(db_engine,company):
    from ai_models.extraction import save_extraction
    s=source(db_engine,company,data_format='PNG',config={'path':str(FIXTURES/'images/synthetic.png')})
    execute_source(db_engine,s)
    first=preview_source(db_engine,company,s['data_source_id'])
    assert first['items'][0]['status']=='EXTRACTION_REQUIRED'
    with db_engine.connect() as conn:
        aid=conn.scalar(select(RawArtifact.raw_artifact_id).where(RawArtifact.company_id==company))
    save_extraction(db_engine,company,aid,{'invoice_number':'IMG-001','invoice_date':'2026-10-10','total_amount':'42.00','currency':'MAD'})
    loaded=preview_apply(db_engine,company,s)
    assert loaded['applied_count']==1,loaded


def test_explicit_poc_reset_preserves_canonical_records_and_replay_bindings(db_engine,company):
    from app.acquisition.reset import reset_executions
    from app.integration_pipeline.models import NormalizationRun
    s=source(db_engine,company)
    execute_source(db_engine,s)
    assert preview_apply(db_engine,company,s)['applied_count']==3
    reset_executions(db_engine,company)
    with db_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Invoice).where(Invoice.company_id==company))==3
        assert conn.scalar(select(func.count()).select_from(NormalizationRun).where(NormalizationRun.company_id==company))==0
    execute_source(db_engine,s)
    assert preview_apply(db_engine,company,s)['skipped_count']==3

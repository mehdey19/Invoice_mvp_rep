import hashlib
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from poc_demo.mock_api import app
from poc_demo.settings import FIXTURES, allowed_url
from poc_demo.services.source_service import validate_source
from poc_demo.universal_acquisition import raw_items
from poc_demo.fixtures.generate import pdf_bytes


@pytest.mark.parametrize('path,fmt,mime',[
 ('csv/invoices_english.csv','CSV','text/csv'),('json/invoices.json','JSON','application/json'),
 ('xml/invoice_sample.xml','XML','application/xml'),('documents/invoice_sample.pdf','PDF','application/pdf'),
 ('images/synthetic.png','PNG','image/png')])
def test_file_formats_preserve_bytes(path,fmt,mime):
    src = {'transport':'FILE','data_format':fmt,'config':{'path':str(FIXTURES/path)}}
    item, = raw_items(src)
    assert item.payload == (FIXTURES/path).read_bytes()
    assert item.mime_type == mime


@pytest.mark.parametrize('url', ['https://example.org/mock/a','http://127.0.0.1:22/mock/a','http://user:secret@localhost:9090/mock/a',
                                'http://localhost:9090/admin','http://localhost.evil.test:9090/mock/a','http://169.254.169.254/mock/a'])
def test_http_boundaries(url):
    with pytest.raises(ValueError):
        allowed_url(url)


def test_symlink_escape(monkeypatch,tmp_path):
    link = tmp_path/'escape.csv'
    link.symlink_to('/etc/passwd')
    monkeypatch.setenv('POC_IMAGES_DIR',str(tmp_path))
    with pytest.raises(ValueError):
        list(raw_items({'transport':'FILE','data_format':'CSV','config':{'path':str(link)}}))


@pytest.mark.parametrize('endpoint', ['/mock/erp/invoices','/mock/erp/invoices/INV-1001','/mock/erp/suppliers','/mock/erp/customers',
 '/mock/payments/transactions','/mock/payments/refunds','/mock/bank/transactions','/mock/bank/accounts',
 '/mock/erp/invoices.csv','/mock/erp/invoices.xml','/mock/bank/transactions.csv','/mock/documents/invoice-sample.pdf'])
def test_mock_endpoints(endpoint):
    with TestClient(app) as client:
        first, second = client.get(endpoint),client.get(endpoint)
    assert first.status_code == 200
    assert first.content == second.content


def test_pdf_is_valid():
    from io import BytesIO
    # Structural PDF check without optional parsing dependencies.
    data=pdf_bytes()
    offset=int(data.split(b'startxref\n')[1].splitlines()[0])
    assert data[offset:].startswith(b'xref') and data.endswith(b'%%EOF\n')


def test_mock_pagination_and_variants(mock_http):
    a=mock_http.get('/mock/erp/invoices').json()['items'][0]
    b=mock_http.get('/mock/erp/invoices?variant=b').json()['items'][0]
    assert 'invoice_id' in a and 'document' in b
    source={'transport':'HTTP_GET','data_format':'JSON','config':{'url':'http://localhost:9090/mock/erp/invoices?scenario=paginated','pagination':True}}
    items=list(raw_items(source))
    assert [json.loads(x.payload)['next_page'] for x in items] == [2,None]
    assert sum(len(json.loads(x.payload)['items']) for x in items)==3


def test_configuration_rejects_credentials_and_bad_types():
    src=dict(source_code='test',name='Test',transport='HTTP_GET',data_format='JSON',entity_type='INVOICE',
             config={'url':'http://localhost:9090/mock/erp/invoices','token':'secret'})
    with pytest.raises(ValueError,match='credentials'):
        validate_source(src)
    src['config'].pop('token')
    src['config']['page_size']='two'
    with pytest.raises(ValueError,match='page_size'):
        validate_source(src)

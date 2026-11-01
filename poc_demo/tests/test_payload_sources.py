"""Compatibility checks for the original POC's raw_items entry point."""
import json
import pytest
from poc_demo.universal_acquisition import raw_items, relative_input_path, PROJECT_ROOT


def test_bank_csv_is_original_bytes():
    fixture = PROJECT_ROOT/'poc_demo/fixtures/bank_transactions.csv'
    source = {'transport':'FILE','data_format':'CSV','config':{'relative_path':'poc_demo/fixtures/bank_transactions.csv'}}
    obj, = list(raw_items(source))
    assert obj.payload == fixture.read_bytes()
    assert obj.payload.count(b'\n') == 3


def test_invoice_json_keeps_original_bytes():
    source = {'transport':'FILE','data_format':'JSON','config':{'relative_path':'poc_demo/fixtures/invoices.json'}}
    obj, = list(raw_items(source))
    assert len(json.loads(obj.payload)) == 2


def test_reject_relative_path_escape():
    with pytest.raises(ValueError):
        relative_input_path('../../../../etc/passwd')


def test_images_read_without_modification(monkeypatch,tmp_path):
    f = tmp_path/'one.png'
    f.write_bytes(b'PNG demo bytes')
    monkeypatch.setenv('POC_IMAGES_DIR',str(tmp_path))
    source = {'transport':'DIRECTORY','data_format':'IMAGE','config':{'env_dir':'POC_IMAGES_DIR'}}
    obj, = list(raw_items(source))
    assert obj.filename == 'one.png' and obj.payload == f.read_bytes()


def test_legacy_mock_contract(mock_http):
    source = {'transport':'HTTP_GET','data_format':'JSON','config':{'url':'http://127.0.0.1:9090/api/invoices'}}
    obj, = list(raw_items(source))
    assert len(json.loads(obj.payload)['invoices']) == 2

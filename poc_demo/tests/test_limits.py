"""Failure cases that must retain stored pages and reject unsafe reads."""
from types import SimpleNamespace
import hashlib
import json
import pytest
import httpx
from sqlalchemy import text,select
from poc_demo.connectors import http_connector
from poc_demo.tests.test_acquisition import source
from poc_demo.services.acquisition_service import execute_source
from poc_demo.services.query_service import list_artifacts
from poc_demo.services.artifact_service import read_artifact
from poc_demo.settings import allowed_url


def fake_responses(monkeypatch,callback):
    original=httpx.Client
    monkeypatch.setattr(http_connector,'httpx',SimpleNamespace(Client=lambda **kwargs:original(transport=httpx.MockTransport(callback),**kwargs)))


def test_partial_pagination_failure_retains_first_page(db_engine,company,monkeypatch):
    def respond(request):
        if request.url.params['page']=='2':
            return httpx.Response(500,request=request)
        return httpx.Response(200,json={'items':[{'invoice_id':'INV-FIRST'}],'next_page':2},request=request)
    fake_responses(monkeypatch,respond)
    s=source(db_engine,company,'paginated')
    result=execute_source(db_engine,s)
    assert result['status']=='FAILED' and result['acquired']==2
    assert len(list_artifacts(db_engine,company))==2


def test_pagination_cycle_is_bounded(db_engine,company,monkeypatch):
    fake_responses(monkeypatch,lambda request:httpx.Response(200,json={'items':[],'next_page':1},request=request))
    s=source(db_engine,company,'paginated')
    result=execute_source(db_engine,s)
    assert result['status']=='FAILED' and 'Pagination cycle' in result['error']
    assert result['acquired']==1


def test_redirects_are_rejected(db_engine,company,monkeypatch):
    fake_responses(monkeypatch,lambda request:httpx.Response(302,headers={'location':'http://example.org/'},request=request))
    s=source(db_engine,company)
    result=execute_source(db_engine,s)
    assert result['status']=='FAILED' and result['acquired']==0


def test_http_size_limit(db_engine,company,monkeypatch):
    monkeypatch.setattr(http_connector,'MAX_BYTES',5)
    fake_responses(monkeypatch,lambda request:httpx.Response(200,content=b'123456',request=request))
    s=source(db_engine,company)
    result=execute_source(db_engine,s)
    assert result['status']=='FAILED' and 'exceeds' in result['error']


def test_postgresql_source_lock_prevents_overlapping_runs(db_engine,company,mock_http):
    s=source(db_engine,company)
    key=int.from_bytes(hashlib.sha256(str(s['data_source_id']).encode()).digest()[:8],'big',signed=True)
    with db_engine.connect() as conn:
        conn.execute(text('select pg_advisory_lock(:key)'),{'key':key})
        conn.commit()
        try:
            result=execute_source(db_engine,s)
            assert result['status']=='FAILED' and 'already has an ingestion' in result['error']
        finally:
            conn.execute(text('select pg_advisory_unlock(:key)'),{'key':key})
            conn.commit()
    assert execute_source(db_engine,s)['status']=='SUCCEEDED'


def test_query_credentials_rejected():
    with pytest.raises(ValueError):
        allowed_url('http://localhost:9090/mock/erp/invoices?api_key=secret')

import httpx
from uuid import uuid4
from sqlalchemy import select,func,event
from streamlit.testing.v1 import AppTest
from app.canonical.models import Invoice,Party
from app.integration_pipeline.models import RawArtifact,ExtractionResult
from app.acquisition.services.acquisition_service import execute_source
from app.normalization.service import preview_source,apply_run
from tests.test_normalization import source


def test_normalization_api_and_company_isolation(client,db_engine,company):
    s=source(db_engine,company)
    execute_source(db_engine,s)
    base=f'/poc/companies/{company}/normalization'
    profiles=client.get(base+'/profiles',params={'source_id':str(s['data_source_id'])})
    assert profiles.status_code==200 and len(profiles.json())==1
    response=client.post(base+'/preview',json={'source_id':str(s['data_source_id'])})
    assert response.status_code==200,response.text
    run=response.json();assert run['valid_count']==3
    applied=client.post(base+'/runs/'+run['normalization_run_id']+'/apply',json={})
    assert applied.status_code==200 and applied.json()['applied_count']==3
    assert len(client.get(base+'/runs').json())==1
    other=uuid4()
    assert client.get(f'/poc/companies/{other}/normalization/runs/'+run['normalization_run_id']).status_code==404
    assert client.post(f'/poc/companies/{other}/normalization/preview',json={'source_id':str(s['data_source_id'])}).status_code==404


def test_loader_rolls_back_all_related_writes(db_engine,company):
    from app.acquisition.settings import FIXTURES
    s=source(db_engine,company,source_code='poc_w1_purchase_rollback',config={'path':str(FIXTURES/'02_purchase_goods_invoice_json.json')})
    execute_source(db_engine,s);preview=preview_source(db_engine,company,s['data_source_id'])
    def reject_line(conn,cursor,statement,parameters,context,executemany):
        if statement.startswith('INSERT INTO invoice_line'): raise ValueError('Synthetic line write failure')
    event.listen(db_engine,'before_cursor_execute',reject_line)
    try: result=apply_run(db_engine,company,preview['normalization_run_id'])
    finally: event.remove(db_engine,'before_cursor_execute',reject_line)
    assert result['applied_count']==0 and result['error_count']==1
    with db_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Invoice).where(Invoice.company_id==company))==0
        assert conn.scalar(select(func.count()).select_from(Party).where(Party.company_id==company))==0


def test_langchain_vision_adapter_and_audit(db_engine,company,monkeypatch):
    from app.acquisition.settings import FIXTURES
    from ai_models import extraction
    from ai_models.registry import configuration,get_vision_model
    s=source(db_engine,company,data_format='PNG',config={'path':str(FIXTURES/'images/synthetic.png')})
    execute_source(db_engine,s)
    with db_engine.connect() as conn: aid=conn.scalar(select(RawArtifact.raw_artifact_id).where(RawArtifact.company_id==company))
    monkeypatch.delenv('AI_VISION_MODEL',raising=False)
    assert not configuration()['enabled']
    import pytest
    with pytest.raises(ValueError,match='AI_VISION_MODEL'): get_vision_model()
    monkeypatch.setenv('AI_VISION_MODEL','synthetic-test-model')
    class Model:
        def with_structured_output(self,schema): self.schema=schema;return self
        def invoke(self,messages):
            assert messages[0].content[1]['image_url']['url'].startswith('data:image/png;base64,')
            return self.schema(invoice_number='VISION-001',invoice_date='2026-10-10',currency='MAD',total_amount='12.00')
    monkeypatch.setattr(extraction,'get_vision_model',lambda:Model())
    result=extraction.extract_image(db_engine,company,aid)
    assert result['status']=='SUCCEEDED' and result['payload']['invoice_number']=='VISION-001'
    with db_engine.connect() as conn:
        audit=conn.execute(select(ExtractionResult.__table__).where(ExtractionResult.company_id==company)).mappings().one()
        assert audit['model_name']=='synthetic-test-model' and audit['prompt_version']=='invoice-v1'


def test_normalization_streamlit_page(client,db_engine,company,monkeypatch):
    s=source(db_engine,company);execute_source(db_engine,s)
    def backend(method,url,**kwargs):
        kwargs.pop('timeout',None);kwargs.pop('follow_redirects',None)
        return client.request(method,url,**kwargs)
    monkeypatch.setattr(httpx,'request',backend)
    at=AppTest.from_file('poc_demo/dashboard.py',default_timeout=20).run()
    at.sidebar.selectbox[0].select({'company_id':str(company),'name':'Synthetic integration test company'}).run()
    at.sidebar.selectbox[1].set_value('Week 2 — Normalization').run()
    for page in ('Overview','Mapping Profiles','Normalization History','Canonical Explorer','Image Extraction','Run Normalization'):
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception
    next(b for b in at.button if b.label=='Run normalization').click().run()
    import time
    deadline=time.monotonic()+10
    base=f'/poc/companies/{company}/normalization'
    while time.monotonic()<deadline:
        runs=client.get(base+'/runs').json()
        if runs and runs[0]['status']!='RUNNING': break
        time.sleep(.02)
    at.run()
    assert not at.exception
    next(b for b in at.button if b.label=='Apply valid records').click().run()
    assert not at.exception
    with db_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Invoice).where(Invoice.company_id==company))==3


def test_week_namespaces_and_background_runs(client,db_engine,company):
    import time
    s=source(db_engine,company);execute_source(db_engine,s)
    assert client.get(f'/api/week-1/companies/{company}/sources').status_code==200
    base=f'/api/week-2/companies/{company}/normalization'
    queued=client.post(base+'/runs',json={'source_id':str(s['data_source_id']),'apply_valid':True})
    assert queued.status_code==202,queued.text
    rid=queued.json()['run_ids'][0];deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        result=client.get(base+'/runs/'+rid).json()
        if result['status']!='RUNNING': break
        time.sleep(.02)
    assert result['applied_count']==3,result
    assert len(client.get(base+'/canonical/invoice').json())==3
    summary=client.get(base+'/canonical-summary').json()
    assert summary['counts']['invoice']==3 and summary['counts']['document']==1
    other=uuid4()
    assert client.get(f'/api/week-2/companies/{other}/normalization/canonical/invoice').json()==[]

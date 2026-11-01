"""Exercise Streamlit against the actual service/API and PostgreSQL test schema."""
import httpx
from streamlit.testing.v1 import AppTest
from poc_demo.tests.test_api import register,wait_run


def test_dashboard_pages_registration_and_ingestion(client,company,monkeypatch):
    original_request=httpx.request
    def backend(method,url,**kwargs):
        kwargs.pop('timeout',None)
        kwargs.pop('follow_redirects',None)
        return client.request(method,url,**kwargs)
    monkeypatch.setattr(httpx,'request',backend)
    at=AppTest.from_file('poc_demo/dashboard.py',default_timeout=20).run()
    assert not at.exception
    company_options=at.sidebar.selectbox[0].options
    # The current fixture company has a unique ID even when previous test rows remain.
    at.sidebar.selectbox[0].select({'company_id':str(company),'name':'Synthetic integration test company'}).run()
    at.sidebar.radio[0].set_value('Data Sources').run()
    assert not at.exception
    def label(elements,name):
        return next(e for e in elements if e.label==name)
    label(at.text_input,'Source code').set_value('streamlit_created')
    label(at.text_input,'Source name').set_value('Streamlit synthetic source')
    label(at.button,'Save source').click().run()
    assert not at.exception
    sources=client.get(f'/poc/companies/{company}/sources').json()
    created=next(s for s in sources if s['source_code']=='streamlit_created')
    at.sidebar.radio[0].set_value('Run Ingestion').run()
    label(at.button,'Run ingestion').click().run()
    assert not at.exception
    runs=client.get(f'/poc/companies/{company}/runs').json()
    assert runs
    result=wait_run(client,company,runs[0]['ingestion_run_id'])
    assert result['status']=='SUCCEEDED'
    for page in ('Overview','Ingestion History','Raw Explorer'):
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception
    label(at.button,'Load preview (maximum 2 MiB)').click().run()
    assert not at.exception

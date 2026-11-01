import time
from uuid import uuid4
from sqlalchemy import select
from app.models.company import Company
from poc_demo.settings import FIXTURES


def register(client,cid,code='ui_source'):
    response=client.post(f'/poc/companies/{cid}/sources',json=dict(source_code=code,name='UI synthetic CSV',transport='FILE',data_format='CSV',entity_type='PAYMENT',config={'path':str(FIXTURES/'csv/payments.csv')}))
    assert response.status_code==201,response.text
    return response.json()


def wait_run(client,cid,run_id):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        row=client.get(f'/poc/companies/{cid}/runs/{run_id}').json()
        if row['status']!='RUNNING':
            return row
        time.sleep(.02)
    raise AssertionError('Run did not finish')


def test_register_edit_execute_explore_and_isolate(client,db_engine,company):
    base=f'/poc/companies/{company}'
    source=register(client,company)
    payload={k:source[k] for k in ('source_code','name','transport','data_format','entity_type','config','field_mapping','is_active')}
    payload['name']='Updated source'
    assert client.put(base+'/sources/'+source['data_source_id'],json=payload).status_code==200
    response=client.post(base+'/runs',json={'source_id':source['data_source_id']})
    assert response.status_code==202
    run=wait_run(client,company,response.json()['run_ids'][0])
    assert run['status']=='SUCCEEDED' and run['acquired_count']==1
    rows=client.get(base+'/artifacts').json()
    artifact,=rows
    content=client.get(base+'/artifacts/'+artifact['raw_artifact_id']+'/content')
    assert content.status_code==200 and content.content==(FIXTURES/'csv/payments.csv').read_bytes()
    assert content.headers['content-disposition'].startswith('attachment;')
    second=client.post(base+'/runs',json={})
    replay=wait_run(client,company,second.json()['run_ids'][0])
    assert replay['acquired_count']==0 and replay['duplicate_count']==1
    assert client.get(base+'/overview').json()['duplicates']==1
    assert len(client.get(base+'/runs',params={'status':'SUCCEEDED'}).json())==2
    other=uuid4()
    with db_engine.begin() as conn:
        conn.execute(Company.__table__.insert().values(company_id=other,name='Other synthetic company'))
    for path in ('sources/'+source['data_source_id'],'runs/'+run['ingestion_run_id'],
                 'artifacts/'+artifact['raw_artifact_id'],'artifacts/'+artifact['raw_artifact_id']+'/content'):
        assert client.get(f'/poc/companies/{other}/'+path).status_code==404
    assert client.get(f'/poc/companies/{other}/artifacts').json()==[]
    assert client.post(f'/poc/companies/{other}/runs',json={'source_id':source['data_source_id']}).status_code==404
    payload['is_active']=False
    assert client.put(base+'/sources/'+source['data_source_id'],json=payload).status_code==200
    assert client.post(base+'/runs',json={'source_id':source['data_source_id']}).status_code==422


def test_validation_and_upload(client,company):
    base=f'/poc/companies/{company}'
    source=register(client,company)
    assert client.post(base+'/sources',json={k:source[k] for k in ('source_code','name','transport','data_format','entity_type','config')}).status_code==422
    payload={k:source[k] for k in ('source_code','name','transport','data_format','entity_type','config')}
    payload.update(source_code='escape',config={'path':'/etc/passwd'})
    assert client.post(base+'/sources',json=payload).status_code==422
    uploaded=client.post(base+'/uploads',files={'file':('../../escape.csv',b'id,amount\n1,100\n','text/csv')})
    assert uploaded.status_code==201
    path=uploaded.json()['path']
    assert '..' not in path and str(company) in path
    assert uploaded.json()['original_filename']=='escape.csv'
    payload.update(source_code='uploaded',config={'path':path,'original_filename':uploaded.json()['original_filename']})
    stored=client.post(base+'/sources',json=payload)
    assert stored.status_code==201
    queued=client.post(base+'/runs',json={'source_id':stored.json()['data_source_id']})
    assert wait_run(client,company,queued.json()['run_ids'][0])['status']=='SUCCEEDED'
    rows=client.get(base+'/artifacts',params={'source_id':stored.json()['data_source_id']}).json()
    assert rows[0]['original_filename']=='escape.csv'
    other=uuid4()
    payload['source_code']='wrong_company_upload'
    assert client.post(f'/poc/companies/{other}/sources',json=payload).status_code==422
    from pathlib import Path
    root=FIXTURES.parents[1]
    (root/path).unlink()
    (root/path).parent.rmdir()


def test_core_routes_remain_available(client):
    assert client.get('/health').json()=={'status':'ok'}
    for path in ('/documents','/invoices','/payments','/bank-transactions'):
        assert client.get(path).status_code==200

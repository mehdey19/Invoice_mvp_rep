from uuid import uuid4
import pytest
from sqlalchemy import select, func
from app.models.acquisition import RawArtifact, IngestionRun
from poc_demo.services.source_service import save_source
from poc_demo.services.acquisition_service import execute_source
from poc_demo.services.artifact_service import read_artifact
from poc_demo.services.query_service import history, list_artifacts, overview
from poc_demo.settings import FIXTURES


def source(engine,cid,scenario='success',**kwargs):
    data=dict(source_code='test_'+uuid4().hex,name='Synthetic test ERP',transport='HTTP_GET',data_format='JSON',entity_type='INVOICE',
              config={'url':'http://localhost:9090/mock/erp/invoices?scenario='+scenario,'records_path':'items','external_id_path':'invoice_id',
                      'pagination': scenario == 'paginated'})
    data.update(kwargs)
    return save_source(engine,cid,data)


def test_replay_new_updated_and_original_integrity(db_engine,company,mock_http):
    s=source(db_engine,company)
    first=execute_source(db_engine,s)
    assert first['status']=='SUCCEEDED' and first['acquired']==4
    again=execute_source(db_engine,s)
    assert again['acquired']==0 and again['duplicates']==4
    s['config']['url']='http://localhost:9090/mock/erp/invoices?scenario=new'
    save_source(db_engine,company,s,s['data_source_id'])
    added=execute_source(db_engine,s)
    assert added['acquired']==2 and added['duplicates']==3
    s['config']['url']='http://localhost:9090/mock/erp/invoices?scenario=updated'
    save_source(db_engine,company,s,s['data_source_id'])
    updated=execute_source(db_engine,s)
    assert updated['acquired']==2 and updated['duplicates']==2
    rows=list_artifacts(db_engine,company)
    versions=[a for a in rows if a['external_id']=='INV-1001']
    assert len(versions)==2 and len({v['sha256_hash'] for v in versions})==2
    for row in rows:
        artifact,payload=read_artifact(db_engine,company,row['raw_artifact_id'])
        import hashlib
        assert hashlib.sha256(payload).hexdigest()==artifact['sha256_hash']
    assert len(history(db_engine,company))==4
    assert overview(db_engine,company)['artifacts']==8


@pytest.mark.parametrize('scenario,expected_new,expected_duplicates', [('paginated',5,0),('duplicates',4,1),('empty',1,0)])
def test_pagination_duplicates_empty(db_engine,company,mock_http,scenario,expected_new,expected_duplicates):
    s=source(db_engine,company,scenario)
    r=execute_source(db_engine,s)
    assert r['status']=='SUCCEEDED'
    assert (r['acquired'],r['duplicates'])==(expected_new,expected_duplicates)
    replay=execute_source(db_engine,s)
    assert replay['acquired']==0 and replay['duplicates']==expected_new+expected_duplicates


@pytest.mark.parametrize('scenario', ['http500','http429','malformed'])
def test_failure_retains_data_and_recovers(db_engine,company,mock_http,scenario):
    s=source(db_engine,company)
    assert execute_source(db_engine,s)['status']=='SUCCEEDED'
    s['config']['url']='http://localhost:9090/mock/erp/invoices?scenario='+scenario
    save_source(db_engine,company,s,s['data_source_id'])
    result=execute_source(db_engine,s)
    assert result['status']=='FAILED' and result['errors']==1 and result['error']
    rows=list_artifacts(db_engine,company)
    assert len(rows)==(5 if scenario=='malformed' else 4)
    s['config']['url']='http://localhost:9090/mock/erp/invoices'
    save_source(db_engine,company,s,s['data_source_id'])
    assert execute_source(db_engine,s)['status']=='SUCCEEDED'
    assert len(history(db_engine,company,status='FAILED'))==1


@pytest.mark.parametrize('path,fmt', [('csv/payments.csv','CSV'),('json/payments.json','JSON'),('xml/invoice_sample.xml','XML'),
                                     ('documents/invoice_sample.pdf','PDF'),('images/synthetic.png','PNG')])
def test_local_acquisition_postgresql_and_raw_bytes(db_engine,company,path,fmt):
    s=source(db_engine,company,transport='FILE',data_format=fmt,config={'path':str(FIXTURES/path)})
    result=execute_source(db_engine,s)
    assert result['status']=='SUCCEEDED' and result['acquired']==1
    row,=list_artifacts(db_engine,company)
    _,payload=read_artifact(db_engine,company,row['raw_artifact_id'])
    assert payload==(FIXTURES/path).read_bytes()
    assert execute_source(db_engine,s)['duplicates']==1


def test_disabled_source(db_engine,company):
    s=source(db_engine,company,is_active=False)
    assert execute_source(db_engine,s)['status']=='FAILED'


def test_storage_integrity_and_bounds(db_engine,company):
    s=source(db_engine,company,transport='FILE',data_format='JSON',config={'path':str(FIXTURES/'json/invoices.json')})
    execute_source(db_engine,s)
    row,=list_artifacts(db_engine,company)
    from pathlib import Path
    path=Path(row['storage_path'])
    if not path.is_absolute():
        from poc_demo.settings import PROJECT_ROOT
        path=PROJECT_ROOT/path
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='integrity'):
        read_artifact(db_engine,company,row['raw_artifact_id'])
    execute_source(db_engine,s)  # replay repairs content-addressed file
    read_artifact(db_engine,company,row['raw_artifact_id'])
    with db_engine.begin() as conn:
        conn.execute(RawArtifact.__table__.update().where(RawArtifact.raw_artifact_id==row['raw_artifact_id']).values(storage_path='/etc/passwd'))
    with pytest.raises(ValueError,match='outside'):
        read_artifact(db_engine,company,row['raw_artifact_id'])

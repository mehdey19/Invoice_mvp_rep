from uuid import uuid4
import pytest
from sqlalchemy import select,func,text,create_engine,inspect
from alembic import command
from alembic.config import Config
from app.models.company import Company
from app.models.acquisition import DataSource,IngestionRun,RawArtifact
from poc_demo.seed import seed,DEMO_COMPANY
from poc_demo.reset import reset_executions
from poc_demo.services.source_service import save_source,list_sources
from poc_demo.services.acquisition_service import execute_source
from poc_demo.settings import FIXTURES


def test_seed_is_repeatable_and_preserves_sources(db_engine,company):
    custom=save_source(db_engine,company,dict(source_code='custom',name='Preserved custom source',transport='FILE',data_format='CSV',entity_type='INVOICE',config={'path':str(FIXTURES/'csv/invoices_english.csv')}))
    seed(db_engine,company)
    before=list_sources(db_engine,company)
    seed(db_engine,company)
    after=list_sources(db_engine,company)
    assert len(before)==len(after)
    assert any(s['data_source_id']==custom['data_source_id'] and s['name']==custom['name'] for s in after)


def test_reset_is_scoped_to_seeded_execution_metadata(db_engine,company):
    seed(db_engine,company)
    s=next(s for s in list_sources(db_engine,company) if s['source_code']=='poc_w1_invoices_json')
    execute_source(db_engine,s)
    custom=save_source(db_engine,company,dict(source_code='unrelated',name='Unrelated',transport='FILE',data_format='CSV',entity_type='INVOICE',config={'path':str(FIXTURES/'csv/invoices_english.csv')}))
    execute_source(db_engine,custom)
    counts=reset_executions(db_engine,company)
    assert counts=={'artifacts':1,'runs':1}
    with db_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(RawArtifact).where(RawArtifact.company_id==company))==1
        assert conn.scalar(select(Company.company_id).where(Company.company_id==company))==company
        assert conn.scalar(select(DataSource.data_source_id).where(DataSource.data_source_id==s['data_source_id']))


@pytest.mark.parametrize('legacy',[False,True])
def test_migration_fresh_and_existing_tables(db_engine,legacy):
    from pathlib import Path
    schema='poc_migration_test_'+uuid4().hex
    with db_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    connection=db_engine.connect()
    original_schema=connection.scalar(text('select current_schema()'))
    connection.commit()
    try:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()
        config=Config('alembic.ini')
        config.attributes['connection']=connection
        command.upgrade(config,'0001_initial_schema')
        cid=uuid4()
        connection.execute(text('insert into company(company_id,name) values (:cid,:name)'),{'cid':cid,'name':'Synthetic migration sentinel'})
        connection.commit()
        if legacy:
            sql=Path('poc_demo/sql/01_schema.sql').read_text()
            sql='\n'.join(line for line in sql.splitlines() if not line.lstrip().startswith('--'))
            for statement in sql.split(';'):
                statement='\n'.join(line for line in statement.splitlines() if not line.startswith('--')).strip()
                if statement and statement not in {'BEGIN','COMMIT'}:
                    connection.execute(text(statement))
            connection.execute(text("insert into data_source(data_source_id,company_id,source_code,name,transport,data_format,entity_type) values (:sid,:cid,'legacy','Legacy sentinel','FILE','JSON','INVOICE')"),{'sid':uuid4(),'cid':cid})
            connection.commit()
        command.upgrade(config,'head')
        assert connection.scalar(text('select name from company where company_id=:cid'),{'cid':cid})=='Synthetic migration sentinel'
        assert 'external_id' in {x['name'] for x in inspect(connection).get_columns('raw_artifact')}
        if legacy:
            assert connection.scalar(text("select count(*) from data_source where source_code='legacy'"))==1
        assert connection.scalar(text('select version_num from alembic_version'))=='0003_canonical_pipeline'
        connection.rollback()
    finally:
        connection.rollback()
        connection.execute(text(f'SET search_path TO "{original_schema}"'))
        connection.commit()
        connection.close()
        with db_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))

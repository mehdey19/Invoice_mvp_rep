from uuid import uuid4
from alembic import command
from alembic.config import Config
from sqlalchemy import text,inspect
import pytest


def test_full_schema_clone_and_pipeline_foreign_keys(db_engine):
    token=uuid4().hex
    origin='clone_source_'+token;canonical='clone_canonical_'+token;pipeline='clone_pipeline_'+token
    with db_engine.begin() as conn: conn.execute(text(f'CREATE SCHEMA "{origin}"'))
    with db_engine.connect() as conn:
        original=conn.scalar(text('select current_schema()'));conn.commit()
        try:
            conn.execute(text(f'SET search_path TO "{origin}"'));conn.commit()
            config=Config('alembic.ini');config.attributes['connection']=conn
            command.upgrade(config,'0002_acquisition_poc')
            cid=uuid4();iid=uuid4();sid=uuid4()
            conn.execute(text("insert into company(company_id,name) values (:cid,'Synthetic clone sentinel')"),{'cid':cid})
            conn.execute(text("insert into invoice(invoice_id,company_id,invoice_type,currency,payment_status,invoice_status) values (:iid,:cid,'RECEIVABLE','MAD','UNKNOWN','UNKNOWN')"),{'iid':iid,'cid':cid})
            conn.execute(text("insert into data_source(data_source_id,company_id,source_code,name,transport,data_format,entity_type) values (:sid,:cid,'sentinel','Sentinel','FILE','CSV','INVOICE')"),{'sid':sid,'cid':cid});conn.commit()
            config.attributes['integration_schemas']={'canonical':canonical,'pipeline':pipeline}
            command.upgrade(config,'head')
            insp=inspect(conn)
            assert set(insp.get_table_names(schema=origin))==set(insp.get_table_names(schema=canonical))
            assert conn.scalar(text(f'select name from "{canonical}".company where company_id=:cid'),{'cid':cid})=='Synthetic clone sentinel'
            assert conn.scalar(text(f'select invoice_id from "{canonical}".invoice'))==iid
            assert conn.scalar(text(f'select data_source_id from "{pipeline}".data_source'))==sid
            assert all(fk['referred_schema']==canonical for fk in insp.get_foreign_keys('invoice',schema=canonical))
            raw_fks=insp.get_foreign_keys('raw_artifact',schema=pipeline)
            assert {fk['referred_schema'] for fk in raw_fks}=={canonical,pipeline}
            assert insp.get_columns('invoice',schema=canonical)[8]['type'] is not None
            enum_schema=conn.scalar(text("""select n.nspname from pg_attribute a join pg_class c on c.oid=a.attrelid
                join pg_namespace tn on tn.oid=c.relnamespace join pg_type t on t.oid=a.atttypid
                join pg_namespace n on n.oid=t.typnamespace where tn.nspname=:s and c.relname='invoice' and a.attname='invoice_type'"""),{'s':canonical})
            assert enum_schema==canonical
            conn.execute(text(f'update "{canonical}".company set name=\'Changed canonical only\' where company_id=:cid'),{'cid':cid});conn.commit()
            assert conn.scalar(text(f'select name from "{origin}".company where company_id=:cid'),{'cid':cid})=='Synthetic clone sentinel'
        finally:
            conn.rollback();conn.execute(text(f'SET search_path TO "{original}"'));conn.commit()
            for schema in (pipeline,canonical,origin):
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            conn.commit()

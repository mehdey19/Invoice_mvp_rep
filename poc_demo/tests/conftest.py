import os
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from app.database import Base
from app import models
from app.models.company import Company
from app.main import app
from poc_demo.api import get_engine
from poc_demo.mock_api import app as mock_app


@pytest.fixture
def mock_http(monkeypatch):
    import httpx
    from poc_demo.connectors import http_connector
    provider = TestClient(mock_app)
    original_client = httpx.Client
    def transport(request):
        response = provider.get(str(request.url))
        return httpx.Response(response.status_code, headers=response.headers, content=response.content, request=request)
    def factory(*args, **kwargs):
        return original_client(*args, transport=httpx.MockTransport(transport), **kwargs)
    monkeypatch.setattr(http_connector, 'httpx', SimpleNamespace(Client=factory))
    yield provider
    provider.close()


@pytest.fixture(scope='session')
def db_engine():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set TEST_DATABASE_URL to the existing PostgreSQL development database; tests create an isolated schema')
    admin = create_engine(url)
    schema = 'poc_test_'+uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'}, pool_size=5, max_overflow=10)
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def company(db_engine, tmp_path, monkeypatch):
    monkeypatch.setenv('POC_RAW_DIR',str(tmp_path/'raw'))
    cid = uuid4()
    with db_engine.begin() as conn:
        conn.execute(Company.__table__.insert().values(company_id=cid,name='Synthetic integration test company',default_currency='MAD',country_code='MA'))
    return cid


@pytest.fixture
def client(db_engine, company):
    from app.database import get_db
    from sqlalchemy.orm import Session
    def scoped_session():
        with Session(db_engine) as session:
            yield session
    app.dependency_overrides[get_engine] = lambda: db_engine
    app.dependency_overrides[get_db] = scoped_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

from poc_demo.seed import seed
from poc_demo.services.source_service import list_sources
from poc_demo.services.acquisition_service import acquire_all
from poc_demo.services.query_service import list_artifacts


def test_all_seeded_formats_and_safe_replay(db_engine,company,mock_http,monkeypatch):
    # Synthetic image directory keeps automated tests independent of real samples.
    from poc_demo.settings import FIXTURES
    monkeypatch.setenv('POC_IMAGES_DIR',str(FIXTURES/'images'))
    seed(db_engine,company)
    first=acquire_all(db_engine,company)
    assert first and all(r['status']=='SUCCEEDED' for r in first)
    artifacts=list_artifacts(db_engine,company)
    assert {'CSV','JSON','XML','PDF','PNG','IMAGE'} <= {a['data_format'] for a in artifacts}
    replay=acquire_all(db_engine,company)
    assert all(r['status']=='SUCCEEDED' and r['acquired']==0 and r['duplicates']>0 for r in replay)
    assert len(list_artifacts(db_engine,company))==len(artifacts)

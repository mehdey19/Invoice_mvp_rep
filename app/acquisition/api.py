"""Development-only acquisition endpoints used by Streamlit and integration tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import hashlib
from pathlib import Path
from threading import BoundedSemaphore
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update, func
from app.database import engine
from app.models.company import Company
from app.models.acquisition import IngestionRun
from app.acquisition.services.source_service import get_source, list_sources, save_source
from app.acquisition.services.acquisition_service import create_run, execute_source
from app.acquisition.services.artifact_service import get_artifact, read_artifact
from app.acquisition.services.query_service import history, list_artifacts, overview
from app.acquisition.settings import FIXTURES, MAX_BYTES, EXTENSIONS, mock_base

router = APIRouter(tags=['Week 1 — Acquisition'])
workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix='poc-acquisition')
capacity = BoundedSemaphore(4)


def get_engine():
    return engine


class SourceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    transport: Literal['FILE','DIRECTORY','HTTP_GET']
    data_format: Literal['CSV','JSON','XML','PNG','JPG','JPEG','PDF','IMAGE']
    entity_type: Literal['INVOICE','PAYMENT','BANK_TRANSACTION']
    config: dict = Field(default_factory=dict)
    field_mapping: dict[str,str] = Field(default_factory=dict)
    is_active: bool = True


class RunInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: UUID | None = None


def service_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/companies')
def companies(db=Depends(get_engine)):
    with db.connect() as conn:
        return [dict(x) for x in conn.execute(select(Company.company_id, Company.name).order_by(Company.name)).mappings()]


@router.get('/companies/{company_id}/overview')
def get_overview(company_id: UUID, db=Depends(get_engine)):
    return overview(db, company_id)


@router.get('/companies/{company_id}/sources')
def get_sources(company_id: UUID, db=Depends(get_engine)):
    return list_sources(db, company_id)


@router.post('/companies/{company_id}/sources', status_code=201)
def add_source(company_id: UUID, source: SourceInput, db=Depends(get_engine)):
    return service_call(save_source, db, company_id, source.model_dump())


@router.get('/companies/{company_id}/sources/{source_id}')
def source_detail(company_id: UUID, source_id: UUID, db=Depends(get_engine)):
    return service_call(get_source, db, company_id, source_id)


@router.put('/companies/{company_id}/sources/{source_id}')
def edit_source(company_id: UUID, source_id: UUID, source: SourceInput, db=Depends(get_engine)):
    return service_call(save_source, db, company_id, source.model_dump(), source_id)


@router.get('/companies/{company_id}/fixtures')
def fixtures(company_id: UUID):
    root = FIXTURES.resolve()
    paths = []
    for f in sorted(root.rglob('*')):
        if f.is_symlink() or not f.is_file() or f.suffix.lower() not in set.union(*EXTENSIONS.values()):
            continue
        rel = f.relative_to(root)
        if rel.parts[0] == 'uploads' and (len(rel.parts) < 3 or rel.parts[1] != str(company_id)):
            continue
        paths.append(str(f.relative_to(FIXTURES.parents[1])))
    return {'paths': paths, 'mock_base_url': mock_base()}


@router.post('/companies/{company_id}/uploads', status_code=201)
async def upload(company_id: UUID, file: UploadFile = File(...), db=Depends(get_engine)):
    with db.connect() as conn:
        if not conn.scalar(select(Company.company_id).where(Company.company_id == company_id)):
            raise HTTPException(404, 'Company not found')
    ext = Path(file.filename or '').suffix.lower()
    if ext not in set.union(*EXTENSIONS.values()):
        raise HTTPException(422, 'Unsupported fixture format')
    payload = await file.read(MAX_BYTES+1)
    await file.close()
    if len(payload) > MAX_BYTES:
        raise HTTPException(413, 'Upload exceeds 25 MiB')
    folder = (FIXTURES/'uploads'/str(company_id)).resolve()
    if not folder.is_relative_to(FIXTURES.resolve()):
        raise HTTPException(422, 'Invalid upload directory')
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/(hashlib.sha256(payload).hexdigest()+ext)
    # Generated content-addressed name; original upload names never form paths.
    import tempfile, os
    with tempfile.NamedTemporaryFile(dir=folder, delete=False) as out:
        out.write(payload)
        temporary = out.name
    os.replace(temporary, path)
    filename = Path((file.filename or 'fixture'+ext).replace('\\','/')).name[:250]
    return {'path': str(path.relative_to(FIXTURES.parents[1])), 'size':len(payload), 'original_filename':filename}


def run_batch(db, sources, ids):
    try:
        for source, run_id in zip(sources, ids):
            try:
                execute_source(db, source, run_id)
            except Exception as exc:
                # Includes a source deleted/changed between scheduling and work.
                with db.begin() as conn:
                    conn.execute(update(IngestionRun).where(IngestionRun.ingestion_run_id == run_id).values(
                        status='FAILED', finished_at=func.now(), error_count=1, error_message=f'{type(exc).__name__}: {exc}'[:2000]))
    finally:
        capacity.release()


@router.post('/companies/{company_id}/runs', status_code=202)
def start_ingestion(company_id: UUID, request: RunInput, db=Depends(get_engine)):
    if request.source_id:
        sources = [service_call(get_source, db, company_id, request.source_id)]
        if not sources[0]['is_active']:
            raise HTTPException(422, 'Enable this source before running it')
    else:
        sources = [s for s in list_sources(db, company_id) if s['is_active']]
    if not sources:
        raise HTTPException(422, 'No active sources')
    if not capacity.acquire(blocking=False):
        raise HTTPException(429, 'Acquisition queue is full; retry after current runs finish')
    ids = []
    try:
        for source in sources:
            ids.append(create_run(db, source))
        workers.submit(run_batch, db, sources, ids)
    except Exception:
        capacity.release()
        with db.begin() as conn:
            conn.execute(update(IngestionRun).where(IngestionRun.ingestion_run_id.in_(ids)).values(
                status='FAILED', finished_at=func.now(), error_count=1, error_message='Unable to schedule acquisition'))
        raise
    return {'run_ids': [str(i) for i in ids]}


@router.get('/companies/{company_id}/runs')
def get_history(company_id: UUID, source_id: UUID | None = None,
                status: Literal['RUNNING','SUCCEEDED','FAILED'] | None = None,
                date_from: date | None = None, date_to: date | None = None,
                limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0), db=Depends(get_engine)):
    return history(db, company_id, source_id, status, date_from, date_to, limit, offset)


@router.get('/companies/{company_id}/runs/{run_id}')
def run_detail(company_id: UUID, run_id: UUID, db=Depends(get_engine)):
    with db.connect() as conn:
        row = conn.execute(select(IngestionRun.__table__).where(IngestionRun.company_id == company_id, IngestionRun.ingestion_run_id == run_id)).mappings().first()
    if not row:
        raise HTTPException(404, 'Run not found for this company')
    result = dict(row)
    result['duration_seconds'] = (row['finished_at']-row['started_at']).total_seconds() if row['finished_at'] else None
    return result


@router.get('/companies/{company_id}/artifacts')
def artifact_list(company_id: UUID, source_id: UUID | None = None, kind: Literal['FILE','RESPONSE','RECORD'] | None = None,
                  limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0), db=Depends(get_engine)):
    return list_artifacts(db, company_id, source_id, kind, limit, offset)


@router.get('/companies/{company_id}/artifacts/{artifact_id}')
def artifact_detail(company_id: UUID, artifact_id: UUID, db=Depends(get_engine)):
    return service_call(get_artifact, db, company_id, artifact_id)


@router.get('/companies/{company_id}/artifacts/{artifact_id}/content')
def artifact_content(company_id: UUID, artifact_id: UUID, preview: bool = True, db=Depends(get_engine)):
    artifact, payload = service_call(read_artifact, db, company_id, artifact_id, preview)
    from urllib.parse import quote
    return Response(payload, media_type=artifact['mime_type'], headers={
        'Content-Disposition': "attachment; filename*=UTF-8''"+quote(artifact['original_filename'], safe=''),
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})

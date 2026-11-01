from uuid import UUID
from fastapi import APIRouter,Depends,Query
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from app.acquisition.api import get_engine,service_call
from app.acquisition.services.source_service import get_source,identifier
from app.integration_pipeline.models import NormalizationRun,ExtractionResult,NormalizationProfile
from app.normalization.profiles import get_profile,save_profile,example_profile,seed_profiles
from app.normalization.service import preview_source,apply_run,run_detail
from ai_models.registry import configuration
from ai_models.extraction import extract_image,save_extraction

router=APIRouter(prefix='/companies/{company_id}/normalization',tags=['Week 2 — Normalization'])


class PreviewInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_id:UUID
    version:int | None=Field(default=None,ge=1)
    artifact_ids:list[UUID] | None=Field(default=None,min_length=1,max_length=500)


class ApplyInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    allow_updates:bool=False


@router.get('/profiles')
def profiles(company_id:UUID,source_id:UUID,db=Depends(get_engine)):
    service_call(get_source,db,company_id,source_id)
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(select(NormalizationProfile.__table__).where(
            NormalizationProfile.company_id==company_id,NormalizationProfile.data_source_id==source_id)
            .order_by(NormalizationProfile.version.desc())).mappings()]


@router.get('/profiles/{source_id}')
def read_profile(company_id:UUID,source_id:UUID,version:int | None=None,db=Depends(get_engine)):
    return service_call(get_profile,db,company_id,source_id,version)


@router.get('/profiles/{source_id}/example')
def profile_example(company_id:UUID,source_id:UUID,db=Depends(get_engine)):
    return example_profile(service_call(get_source,db,company_id,source_id))


@router.post('/profiles/{source_id}',status_code=201)
def create_profile(company_id:UUID,source_id:UUID,mapping:dict,db=Depends(get_engine)):
    return service_call(save_profile,db,company_id,source_id,mapping)


@router.post('/preview')
def preview(company_id:UUID,request:PreviewInput,db=Depends(get_engine)):
    return service_call(preview_source,db,company_id,request.source_id,request.version,request.artifact_ids)


@router.post('/runs/{run_id}/apply')
def apply(company_id:UUID,run_id:UUID,request:ApplyInput,db=Depends(get_engine)):
    return service_call(apply_run,db,company_id,run_id,request.allow_updates)


@router.get('/runs')
def runs(company_id:UUID,limit:int=Query(100,ge=1,le=500),db=Depends(get_engine)):
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(select(NormalizationRun.__table__).where(NormalizationRun.company_id==company_id)
            .order_by(NormalizationRun.started_at.desc()).limit(limit)).mappings()]


@router.get('/runs/{run_id}')
def detail(company_id:UUID,run_id:UUID,db=Depends(get_engine)):
    return service_call(run_detail,db,company_id,run_id)


@router.get('/ai-model')
def model_config(company_id:UUID): return configuration()


@router.get('/canonical-summary')
def canonical_summary(company_id:UUID,db=Depends(get_engine)):
    from sqlalchemy import func
    from app.canonical.models import Document,Invoice,Party,Payment,BankTransaction,InvoiceLine,PaymentAllocation
    with db.connect() as conn:
        counts={cls.__tablename__:conn.scalar(select(func.count()).select_from(cls).where(cls.company_id==company_id))
                for cls in (Document,Invoice,Party,Payment,BankTransaction)}
        counts['invoice_line']=conn.scalar(select(func.count()).select_from(InvoiceLine).join(Invoice,InvoiceLine.invoice_id==Invoice.invoice_id).where(Invoice.company_id==company_id))
        counts['payment_allocation']=conn.scalar(select(func.count()).select_from(PaymentAllocation).join(Payment,PaymentAllocation.payment_id==Payment.payment_id).where(Payment.company_id==company_id))
    return {'business_schema':'canonical','process_schema':'integration_pipeline','counts':counts}


@router.get('/extractions')
def extractions(company_id:UUID,db=Depends(get_engine)):
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(select(ExtractionResult.__table__).where(ExtractionResult.company_id==company_id)
            .order_by(ExtractionResult.created_at.desc()).limit(100)).mappings()]


@router.post('/extractions/{artifact_id}')
def extract(company_id:UUID,artifact_id:UUID,db=Depends(get_engine)):
    return service_call(extract_image,db,company_id,artifact_id)


@router.post('/extractions/{artifact_id}/reviewed')
def reviewed_extraction(company_id:UUID,artifact_id:UUID,payload:dict,db=Depends(get_engine)):
    return service_call(save_extraction,db,company_id,artifact_id,payload)


# Week 2 uses the same bounded background-run pattern as Week 1.
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from uuid import uuid4
from sqlalchemy import update,func
from fastapi import HTTPException
from app.acquisition.services.source_service import list_sources
norm_workers=ThreadPoolExecutor(max_workers=2,thread_name_prefix='normalization')
norm_capacity=BoundedSemaphore(4)


class RunInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_id:UUID | None=None
    version:int | None=Field(default=None,ge=1)
    apply_valid:bool=False
    allow_updates:bool=False


def normalization_batch(db,company_id,jobs,apply_valid,allow_updates):
    try:
        for sid,version,rid in jobs:
            try:
                result=preview_source(db,company_id,sid,version,run_id=rid,pending_apply=apply_valid)
                if apply_valid: apply_run(db,company_id,rid,allow_updates)
            except Exception as exc:
                with db.begin() as conn:
                    conn.execute(update(NormalizationRun).where(NormalizationRun.normalization_run_id==rid).values(
                        status='FAILED',error_count=1,error_message=str(exc)[:2000],finished_at=func.now()))
    finally: norm_capacity.release()


@router.post('/runs',status_code=202)
def start_normalization(company_id:UUID,request:RunInput,db=Depends(get_engine)):
    sources=[service_call(get_source,db,company_id,request.source_id)] if request.source_id else [s for s in list_sources(db,company_id) if s['is_active']]
    profiles=[]
    for source in sources:
        if not source['is_active']: raise HTTPException(422,'Enable this source before running it')
        try: profile=get_profile(db,company_id,source['data_source_id'],request.version)
        except LookupError:
            if request.source_id: raise HTTPException(422,'Save a normalization profile for this source first')
            continue
        profiles.append(profile)
    if not profiles: raise HTTPException(422,'No active sources with normalization profiles')
    if not norm_capacity.acquire(blocking=False): raise HTTPException(429,'Normalization queue is full; retry later')
    jobs=[]
    try:
        with db.begin() as conn:
            for profile in profiles:
                rid=uuid4()
                conn.execute(NormalizationRun.__table__.insert().values(normalization_run_id=rid,company_id=company_id,
                    data_source_id=profile['data_source_id'],profile_id=profile['profile_id'],status='RUNNING'))
                jobs.append((profile['data_source_id'],profile['version'],rid))
        norm_workers.submit(normalization_batch,db,company_id,jobs,request.apply_valid,request.allow_updates)
    except Exception:
        norm_capacity.release()
        with db.begin() as conn:
            conn.execute(update(NormalizationRun).where(NormalizationRun.normalization_run_id.in_([job[2] for job in jobs])).values(
                status='FAILED',error_count=1,error_message='Unable to schedule normalization',finished_at=func.now()))
        raise
    return {'run_ids':[str(job[2]) for job in jobs]}


@router.get('/canonical/{entity}')
def canonical_records(company_id:UUID,entity:str,limit:int=Query(200,ge=1,le=500),db=Depends(get_engine)):
    from app.canonical.models import Document,Invoice,InvoiceLine,Party,Payment,PaymentAllocation,BankTransaction
    models={c.__tablename__:c for c in (Document,Invoice,InvoiceLine,Party,Payment,PaymentAllocation,BankTransaction)}
    if entity not in models: raise HTTPException(422,'Unknown canonical entity')
    model=models[entity];query=select(model.__table__)
    if entity=='invoice_line': query=query.join(Invoice,InvoiceLine.invoice_id==Invoice.invoice_id).where(Invoice.company_id==company_id)
    elif entity=='payment_allocation': query=query.join(Payment,PaymentAllocation.payment_id==Payment.payment_id).where(Payment.company_id==company_id)
    else: query=query.where(model.company_id==company_id)
    with db.connect() as conn: return [dict(r) for r in conn.execute(query.limit(limit)).mappings()]

from collections import Counter
import hashlib
import json
from uuid import uuid4
from sqlalchemy import select,update,func,text
from app.integration_pipeline.models import NormalizationRun,NormalizationItem,RawArtifact
from app.acquisition.services.source_service import get_source,identifier
from app.acquisition.services.artifact_service import read_artifact
from app.normalization.profiles import get_profile
from app.normalization.mapper import normalize,get_path
from app.normalization.readers import records,ExtractionRequired
from app.normalization.loaders import apply_item,NeedsReview


def checksum(value): return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()


def run_detail(engine,company_id,run_id):
    with engine.connect() as conn:
        run=conn.execute(select(NormalizationRun.__table__).where(NormalizationRun.company_id==identifier(company_id),
            NormalizationRun.normalization_run_id==identifier(run_id))).mappings().first()
        if not run: raise LookupError('Normalization run not found for this company')
        items=conn.execute(select(NormalizationItem.__table__).where(NormalizationItem.normalization_run_id==identifier(run_id),
            NormalizationItem.company_id==identifier(company_id))).mappings().all()
    duration=(run['finished_at']-run['started_at']).total_seconds() if run['finished_at'] else None
    return dict(run,items=[dict(i) for i in items],duration_seconds=duration)


def finalize(engine,run_id,keep_running=False):
    with engine.begin() as conn:
        detail=conn.execute(select(NormalizationItem.status,RawArtifact.document_id).join(RawArtifact,
            NormalizationItem.raw_artifact_id==RawArtifact.raw_artifact_id).where(NormalizationItem.normalization_run_id==run_id)).all()
        rows=[r.status for r in detail]
        counts=Counter(rows)
        errors=sum(counts[s] for s in ('INVALID','FAILED','NEEDS_REVIEW','EXTRACTION_REQUIRED'))
        applied=counts['APPLIED'];skipped=counts['SKIPPED'];ready=counts['READY']
        status='PREVIEWED' if ready or not rows else 'APPLIED' if not errors else 'PARTIAL' if applied or skipped else 'NEEDS_REVIEW'
        if keep_running: status='RUNNING'
        conn.execute(update(NormalizationRun).where(NormalizationRun.normalization_run_id==run_id).values(
            status=status,finished_at=None if keep_running else func.now(),record_count=len(rows),valid_count=ready+applied+skipped,
            applied_count=applied,skipped_count=skipped,error_count=errors))
        from app.canonical.models.document import Document
        grouped={}
        for row in detail:
            if row.document_id: grouped.setdefault(row.document_id,[]).append(row.status)
        for document_id,statuses in grouped.items():
            if all(s in ('APPLIED','SKIPPED') for s in statuses): state='VALIDATED'
            elif any(s in ('READY','APPLIED','SKIPPED') for s in statuses): state='EXTRACTED'
            else: continue
            conn.execute(update(Document).where(Document.document_id==document_id).values(processing_status=state))


def preview_source(engine,company_id,source_id,version=None,artifact_ids=None,run_id=None,pending_apply=False):
    source=get_source(engine,company_id,source_id);profile=get_profile(engine,company_id,source_id,version);mapping=profile['mapping']
    if artifact_ids is not None and not artifact_ids: raise ValueError('artifact_ids must not be empty')
    query=select(RawArtifact.__table__).where(RawArtifact.company_id==identifier(company_id),RawArtifact.data_source_id==identifier(source_id))
    if artifact_ids is not None: query=query.where(RawArtifact.raw_artifact_id.in_([identifier(x) for x in artifact_ids]))
    with engine.connect() as conn:
        artifacts=[dict(r) for r in conn.execute(query.order_by(RawArtifact.acquired_at.desc())).mappings()]
    if artifact_ids is not None and len(artifacts)!=len(set(map(str,artifact_ids))): raise LookupError('Artifact not found for this company/source')
    has_records=any(a['artifact_kind']=='RECORD' for a in artifacts)
    latest=[];seen=set()
    for artifact in artifacts:
        if has_records and source['config'].get('records_path') and artifact['artifact_kind']=='RESPONSE': continue
        key=(artifact['artifact_kind'],artifact['external_id'])
        if artifact['external_id'] and key in seen: continue
        seen.add(key);latest.append(artifact)
    rid=identifier(run_id) if run_id else uuid4()
    if not run_id:
        with engine.begin() as conn:
            conn.execute(NormalizationRun.__table__.insert().values(normalization_run_id=rid,company_id=identifier(company_id),
                data_source_id=identifier(source_id),profile_id=profile['profile_id'],status='RUNNING'))
    for artifact in latest:
        try:
            _,payload=read_artifact(engine,company_id,artifact['raw_artifact_id'])
            for locator,record in records(engine,artifact,payload,source,mapping):
                provenance=dict(data_source_id=str(source_id),raw_artifact_id=str(artifact['raw_artifact_id']),
                    external_id=artifact['external_id'],record_locator=locator,raw_checksum=artifact['sha256_hash'],
                    mapping_version=profile['version'],mapping_checksum=checksum(mapping),document_id=str(artifact['document_id']) if artifact['document_id'] else None)
                identity=next((str(v) for path in mapping.get('identity',{}).get('paths',[]) if (v:=get_path(record,path)) is not None and str(v).strip()),None)
                identity=identity or (artifact['external_id'] if artifact['artifact_kind']=='RECORD' else None)
                normalized,errors=normalize(record,mapping,company_id,provenance)
                status='INVALID' if errors else 'READY'
                if not identity: errors.append({'field':'identity','message':'A stable external record identity is required'});status='INVALID'
                if mapping.get('review_reason'):
                    errors.append({'field':'record','message':mapping['review_reason']});status='NEEDS_REVIEW'
                if record.get('type') in ('AVOIR','CREDIT_NOTE'):
                    errors.append({'field':'record','message':'Credit notes require an explicit business representation'});status='NEEDS_REVIEW'
                if normalized: normalized['provenance']['external_id']=identity
                with engine.begin() as conn:
                    conn.execute(NormalizationItem.__table__.insert().values(normalization_item_id=uuid4(),normalization_run_id=rid,
                        company_id=identifier(company_id),raw_artifact_id=artifact['raw_artifact_id'],record_locator=locator,
                        source_record_id=identity,input_checksum=checksum(record),status=status,normalized_payload=normalized,errors=errors,target_ids={}))
        except Exception as exc:
            status='EXTRACTION_REQUIRED' if isinstance(exc,ExtractionRequired) else 'INVALID'
            with engine.begin() as conn:
                conn.execute(NormalizationItem.__table__.insert().values(normalization_item_id=uuid4(),normalization_run_id=rid,
                    company_id=identifier(company_id),raw_artifact_id=artifact['raw_artifact_id'],record_locator='artifact',
                    input_checksum=artifact['sha256_hash'],status=status,normalized_payload={},errors=[{'field':'artifact','message':str(exc)}],target_ids={}))
    finalize(engine,rid,keep_running=pending_apply)
    return run_detail(engine,company_id,rid)


def apply_run(engine,company_id,run_id,allow_updates=False):
    run=run_detail(engine,company_id,run_id)
    profile=get_profile(engine,company_id,run['data_source_id'],
        next_version(engine,run['profile_id']))
    key=int.from_bytes(hashlib.sha256(str(run['data_source_id']).encode()).digest()[:8],'big',signed=True)
    with engine.connect() as lease:
        locked=lease.scalar(text('select pg_try_advisory_lock(:key)'),{'key':key});lease.commit()
        if not locked: raise ValueError('Source acquisition or normalization is already running')
        try:
            for item in run['items']:
                if item['status']!='READY': continue
                try: apply_item(engine,item['normalization_item_id'],profile,allow_updates)
                except Exception as exc:
                    with engine.begin() as conn:
                        conn.execute(update(NormalizationItem).where(NormalizationItem.normalization_item_id==item['normalization_item_id']).values(
                            status='NEEDS_REVIEW' if isinstance(exc,NeedsReview) else 'FAILED',errors=[{'field':'apply','message':str(exc)}]))
        finally:
            lease.execute(text('select pg_advisory_unlock(:key)'),{'key':key});lease.commit()
    finalize(engine,identifier(run_id))
    return run_detail(engine,company_id,run_id)


def next_version(engine,profile_id):
    from app.integration_pipeline.models import NormalizationProfile
    with engine.connect() as conn: return conn.scalar(select(NormalizationProfile.version).where(NormalizationProfile.profile_id==profile_id))

from datetime import datetime, time, timedelta, timezone
from sqlalchemy import select, func, case
from app.models.acquisition import DataSource, IngestionRun, RawArtifact
from app.acquisition.services.source_service import identifier

s, r, a = DataSource.__table__, IngestionRun.__table__, RawArtifact.__table__


def history(engine, company_id, source_id=None, status=None, date_from=None, date_to=None, limit=200, offset=0):
    query = select(r, s.c.name.label('source_name')).join(s, r.c.data_source_id == s.c.data_source_id).where(r.c.company_id == identifier(company_id))
    if source_id:
        query = query.where(r.c.data_source_id == identifier(source_id))
    if status:
        query = query.where(r.c.status == status)
    if date_from:
        query = query.where(r.c.started_at >= datetime.combine(date_from, time.min, timezone.utc))
    if date_to:
        query = query.where(r.c.started_at < datetime.combine(date_to+timedelta(days=1), time.min, timezone.utc))
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(query.order_by(r.c.started_at.desc()).limit(limit).offset(offset)).mappings()]
    for row in rows:
        row['duration_seconds'] = (row['finished_at']-row['started_at']).total_seconds() if row['finished_at'] else None
    return rows


def list_artifacts(engine, company_id, source_id=None, kind=None, limit=200, offset=0):
    query = select(a, s.c.name.label('source_name')).join(s, a.c.data_source_id == s.c.data_source_id).where(a.c.company_id == identifier(company_id))
    if source_id:
        query = query.where(a.c.data_source_id == identifier(source_id))
    if kind:
        query = query.where(a.c.artifact_kind == kind)
    with engine.connect() as conn:
        return [dict(x) for x in conn.execute(query.order_by(a.c.acquired_at.desc()).limit(limit).offset(offset)).mappings()]


def overview(engine, company_id):
    cid = identifier(company_id)
    with engine.connect() as conn:
        source_counts = conn.execute(select(func.count().label('sources'), func.count().filter(s.c.is_active).label('active_sources')).where(s.c.company_id == cid)).mappings().one()
        run_counts = conn.execute(select(func.count().label('executions'), func.count().filter(r.c.status == 'SUCCEEDED').label('successful'),
              func.count().filter(r.c.status == 'FAILED').label('failed'), func.coalesce(func.sum(r.c.duplicate_count),0).label('duplicates'),
              func.max(r.c.started_at).label('last_ingestion')).where(r.c.company_id == cid)).mappings().one()
        artifact_counts = conn.execute(select(func.count().label('artifacts'), func.count().filter(a.c.artifact_kind == 'RECORD').label('record_artifacts'),
              func.count().filter(a.c.artifact_kind == 'RESPONSE').label('response_artifacts')).where(a.c.company_id == cid)).mappings().one()
        groups = [dict(x) for x in conn.execute(select(s.c.transport, r.c.status, func.count().label('runs')).join(r, s.c.data_source_id == r.c.data_source_id).where(s.c.company_id == cid).group_by(s.c.transport, r.c.status)).mappings()]
    return dict(**source_counts, **run_counts, **artifact_counts, by_transport=groups)

"""Explicitly delete execution metadata for seeded Week 1 sources only."""
import argparse
from uuid import UUID
from sqlalchemy import create_engine, select, delete
from app.config import get_settings
from app.models.acquisition import DataSource, RawArtifact, IngestionRun
from app.acquisition.seed import PREFIX


def reset_executions(engine, company_id):
    company_id = UUID(str(company_id))
    with engine.begin() as conn:
        ids = list(conn.scalars(select(DataSource.data_source_id).where(DataSource.company_id == company_id,
                        DataSource.source_code.startswith(PREFIX, autoescape=True))))
        # Acquire the same session locks as ingestion before inspecting/deleting.
        import hashlib
        from sqlalchemy import text
        keys = [int.from_bytes(hashlib.sha256(str(i).encode()).digest()[:8], 'big', signed=True) for i in ids]
        locked = []
        try:
            for key in keys:
                if not conn.scalar(text('select pg_try_advisory_lock(:key)'), {'key':key}):
                    raise ValueError('A seeded source is running; wait before resetting')
                locked.append(key)
            if conn.scalar(select(IngestionRun.ingestion_run_id).where(IngestionRun.data_source_id.in_(ids), IngestionRun.status == 'RUNNING').limit(1)):
                raise ValueError('A seeded run is still RUNNING; finish or investigate it before resetting')
            from app.integration_pipeline.models import NormalizationRun,NormalizationItem,SourceEntityLink,ExtractionResult
            run_ids=select(NormalizationRun.normalization_run_id).where(NormalizationRun.company_id==company_id,NormalizationRun.data_source_id.in_(ids))
            artifact_ids=select(RawArtifact.raw_artifact_id).where(RawArtifact.company_id==company_id,RawArtifact.data_source_id.in_(ids))
            # Keep canonical records and their external identity bindings so a
            # replay after an explicit metadata reset remains idempotent.
            from sqlalchemy import update
            conn.execute(update(SourceEntityLink).where(SourceEntityLink.company_id==company_id,SourceEntityLink.data_source_id.in_(ids)).values(normalization_item_id=None))
            conn.execute(delete(NormalizationItem).where(NormalizationItem.company_id==company_id,NormalizationItem.normalization_run_id.in_(run_ids)))
            conn.execute(delete(NormalizationRun).where(NormalizationRun.company_id==company_id,NormalizationRun.data_source_id.in_(ids)))
            conn.execute(delete(ExtractionResult).where(ExtractionResult.company_id==company_id,ExtractionResult.raw_artifact_id.in_(artifact_ids)))
            artifacts = conn.execute(delete(RawArtifact).where(RawArtifact.company_id == company_id, RawArtifact.data_source_id.in_(ids))).rowcount
            runs = conn.execute(delete(IngestionRun).where(IngestionRun.company_id == company_id, IngestionRun.data_source_id.in_(ids))).rowcount
        finally:
            for key in locked:
                conn.execute(text('select pg_advisory_unlock(:key)'), {'key':key})
    return {'artifacts': artifacts, 'runs': runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--company-id', type=UUID, required=True)
    parser.add_argument('--confirm', choices=['RESET_POC_EXECUTIONS'], required=True)
    args = parser.parse_args()
    from app.database import create_app_engine
    print(reset_executions(create_app_engine(), args.company_id))
    print('Source registrations, core tables and raw files retained.')


if __name__ == '__main__':
    main()

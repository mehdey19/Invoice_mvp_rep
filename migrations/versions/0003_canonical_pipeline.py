"""Clone public and separate canonical business data from integration processes."""
from alembic import op, context
import sqlalchemy as sa
from app.integration_pipeline.schema_clone import clone_schema
from app.integration_pipeline.models import (
    NormalizationProfile, NormalizationRun, NormalizationItem, SourceEntityLink, ExtractionResult,
)

revision = "0003_canonical_pipeline"
down_revision = "0002_acquisition_poc"
branch_labels = depends_on = None
PROCESS_TABLES = {"data_source", "ingestion_run", "raw_artifact", "normalization_profile", "normalization_run",
                  "normalization_item", "source_entity_link", "extraction_result"}


def upgrade():
    conn = op.get_bind()
    # Tests may migrate inside their own generated schema. Never clone public
    # or create global schemas as a side effect of those isolated legacy tests.
    origin = conn.scalar(sa.text("select current_schema()"))
    names = context.get_context().config.attributes.get("integration_schemas")
    if origin != "public" and not names:
        return
    canonical = names["canonical"] if names else "canonical"
    pipeline = names["pipeline"] if names else "integration_pipeline"
    clone_schema(conn, origin, canonical, include_data=True)
    clone_schema(conn, origin, pipeline, include_data=True,
                 tables=["data_source", "ingestion_run", "raw_artifact"], external_schema=canonical)
    op.add_column("raw_artifact", sa.Column("document_id", sa.Uuid(), nullable=True), schema=pipeline)
    op.create_foreign_key("fk_raw_artifact_document", "raw_artifact", "document", ["document_id"], ["document_id"],
                          source_schema=pipeline, referent_schema=canonical)
    metadata = sa.MetaData()
    metadata.reflect(conn, schema=canonical)
    metadata.reflect(conn, schema=pipeline)
    def referenced_schema(table, schema, constraint, old_schema):
        name = constraint.elements[0].target_fullname.split(".")[-2]
        return pipeline if name in PROCESS_TABLES else canonical
    new = [cls.__table__.to_metadata(metadata, schema=pipeline, referred_schema_fn=referenced_schema)
           for cls in (NormalizationProfile, NormalizationRun, NormalizationItem, SourceEntityLink, ExtractionResult)]
    metadata.create_all(conn, tables=new)
    op.create_index("idx_normalization_item_run", "normalization_item", ["normalization_run_id"], schema=pipeline)


def downgrade():
    raise RuntimeError("Canonical and pipeline schemas hold independent records; automatic deletion is unsupported")

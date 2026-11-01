"""Adopt existing POC tables and extend them without removing records.

Revision ID: 0002_acquisition_poc
Revises: 0001_initial_schema
"""
from pathlib import Path
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_acquisition_poc"
down_revision = "0001_initial_schema"
branch_labels = depends_on = None


def upgrade():
    # Original CREATE IF NOT EXISTS definitions also support databases where the
    # hand-applied POC tables already exist. No core tables are touched.
    sql = (Path(__file__).parents[2] / "poc_demo/sql/01_schema.sql").read_text()
    sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    for statement in sql.split(";"):
        statement = "\n".join(line for line in statement.splitlines() if not line.startswith("--")).strip()
        if statement and statement not in {"BEGIN", "COMMIT"}:
            op.execute(sa.text(statement))
    existing = {x["name"] for x in sa.inspect(op.get_bind()).get_columns("data_source")}
    if "updated_at" not in existing:
        op.add_column("data_source", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for constraint in sa.inspect(op.get_bind()).get_check_constraints("data_source"):
        if "data_format" in constraint["sqltext"]:
            op.drop_constraint(op.f(constraint["name"]), "data_source", type_="check")
    op.create_check_constraint(op.f("data_source_data_format_check"), "data_source",
                               "data_format IN ('CSV','JSON','XML','IMAGE','PNG','JPG','JPEG','PDF')")
    for table, columns in {
        "ingestion_run": [sa.Column("attempted_count", sa.Integer(), nullable=False, server_default="0"),
                          sa.Column("error_count", sa.Integer(), nullable=False, server_default="0")],
        "raw_artifact": [sa.Column("external_id", sa.Text()), sa.Column("data_format", sa.String(20)),
                         sa.Column("artifact_kind", sa.String(20), nullable=False, server_default="FILE"),
                         sa.Column("acquisition_metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"))],
    }.items():
        names = {x["name"] for x in sa.inspect(op.get_bind()).get_columns(table)}
        for column in columns:
            if column.name not in names:
                op.add_column(table, column)
    op.execute("UPDATE ingestion_run SET attempted_count = acquired_count + duplicate_count, error_count = CASE WHEN status='FAILED' THEN 1 ELSE 0 END")
    op.execute("UPDATE raw_artifact a SET data_format=s.data_format FROM data_source s WHERE a.data_source_id=s.data_source_id AND a.data_format IS NULL")
    op.create_index("idx_raw_artifact_external_id", "raw_artifact", ["data_source_id", "external_id"])


def downgrade():
    raise RuntimeError("This migration adopts pre-existing POC data. Automatic downgrade is intentionally unsupported.")

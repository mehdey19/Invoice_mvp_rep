"""Clone the actual table/enum schema without sharing data or foreign keys."""
from sqlalchemy import inspect, text


def clone_schema(conn, origin, destination, include_data=True, tables=None, external_schema=None):
    inspector = inspect(conn)
    quote = conn.dialect.identifier_preparer.quote
    q = lambda schema, name: quote(schema) + "." + quote(name)
    names = tables or inspector.get_table_names(schema=origin)
    if conn.scalar(text("select exists(select 1 from pg_namespace where nspname=:n)"), {"n": destination}):
        raise ValueError(f"Destination schema {destination} already exists; refusing to overwrite it")
    # Current MVP inventory consists of ordinary tables and enums. Refuse to
    # silently omit objects if that inventory changes in a future deployment.
    if not tables:
        if inspector.get_view_names(schema=origin) or inspector.get_sequence_names(schema=origin):
            raise ValueError("Schema has views/sequences; extend the clone migration before proceeding")
        extra = conn.scalar(text("""select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                                      where n.nspname=:schema"""), {"schema": origin})
        triggers = conn.scalar(text("select count(*) from information_schema.triggers where trigger_schema=:schema"), {"schema": origin})
        if extra or triggers:
            raise ValueError("Schema has routines/triggers; extend the clone migration before proceeding")
    conn.execute(text(f"CREATE SCHEMA {quote(destination)}"))
    enums = {e["name"]: e for e in inspector.get_enums(schema=origin)}
    if not tables:
        for name, enum in enums.items():
            values = ",".join("'"+x.replace("'", "''")+"'" for x in enum["labels"])
            conn.execute(text(f"CREATE TYPE {q(destination, name)} AS ENUM ({values})"))
    for name in names:
        conn.execute(text(f"CREATE TABLE {q(destination, name)} (LIKE {q(origin, name)} INCLUDING ALL)"))
        columns = inspector.get_columns(name, schema=origin)
        selectors = []
        for column in columns:
            col = quote(column["name"])
            typ = column["type"]
            if not tables and getattr(typ, "name", None) in enums:
                enumtype = q(destination, typ.name)
                conn.execute(text(f"ALTER TABLE {q(destination,name)} ALTER COLUMN {col} TYPE {enumtype} USING {col}::text::{enumtype}"))
                selectors.append(f"{col}::text::{enumtype}")
            else:
                selectors.append(col)
        if include_data:
            cols = ",".join(quote(c["name"]) for c in columns)
            conn.execute(text(f"INSERT INTO {q(destination,name)} ({cols}) SELECT {','.join(selectors)} FROM {q(origin,name)}"))
    # LIKE INCLUDING ALL deliberately does not copy foreign keys. Recreate
    # every FK against its new owner, after all data and referenced tables exist.
    for name in names:
        for fk in inspector.get_foreign_keys(name, schema=origin):
            remote = fk["referred_table"]
            owner = destination if remote in names else external_schema or fk.get("referred_schema") or origin
            cols = ",".join(map(quote, fk["constrained_columns"]))
            refs = ",".join(map(quote, fk["referred_columns"]))
            ddl = f"ALTER TABLE {q(destination,name)} ADD CONSTRAINT {quote(fk['name'])} FOREIGN KEY ({cols}) REFERENCES {q(owner,remote)} ({refs})"
            opts = fk.get("options", {})
            for key, keyword in (("onupdate", "ON UPDATE"), ("ondelete", "ON DELETE")):
                if opts.get(key): ddl += " "+keyword+" "+opts[key]
            if opts.get("deferrable"): ddl += " DEFERRABLE"
            if opts.get("initially"): ddl += " INITIALLY "+opts["initially"]
            conn.execute(text(ddl))
    return names

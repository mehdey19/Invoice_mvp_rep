import re
from uuid import UUID, uuid4
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from app.models.acquisition import DataSource
from app.models.company import Company
from app.acquisition.settings import FIXTURES, FORMATS, EXTENSIONS, allowed_path, allowed_url, images_dir

sources = DataSource.__table__
TRANS = ("FILE", "DIRECTORY", "HTTP_GET")
ENTITIES = ("INVOICE", "PAYMENT", "BANK_TRANSACTION")


def identifier(value):
    return value if isinstance(value, UUID) else UUID(str(value))


def validate_source(data):
    data = dict(data)
    code = data.get("source_code", "")
    if not isinstance(code, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", code):
        raise ValueError("Source code must use 1–80 letters, digits, underscores or hyphens")
    if not isinstance(data.get("name"), str) or not data["name"].strip() or len(data["name"]) > 160:
        raise ValueError("Source name must contain 1–160 characters")
    mode, fmt = data.get("transport"), data.get("data_format")
    if mode not in TRANS or fmt not in FORMATS or data.get("entity_type") not in ENTITIES:
        raise ValueError("Unsupported transport, data format or entity type")
    if not isinstance(data.get("is_active", True), bool):
        raise ValueError("is_active must be boolean")
    config, mapping = data.get("config", {}), data.get("field_mapping", {})
    if not isinstance(config, dict) or not isinstance(mapping, dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in mapping.items()):
        raise ValueError("Configuration must be an object; field mappings must map strings to strings")
    allowed_keys = {"path", "relative_path", "env_dir", "extensions", "delimiter", "original_filename"} if mode != "HTTP_GET" else {
        "url", "pagination", "page_size", "max_pages", "records_path", "external_id_path", "next_page_path"}
    if set(config) - allowed_keys:
        raise ValueError("Unsupported configuration keys; credentials and arbitrary headers are not accepted")
    if mode == "HTTP_GET":
        allowed_url(config.get("url", ""))
        if not isinstance(config.get("pagination", False), bool):
            raise ValueError("pagination must be boolean")
        for key, upper in (("page_size", 100), ("max_pages", 100)):
            value = config.get(key, 2 if key == "page_size" else 100)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
                raise ValueError(f"{key} must be an integer between 1 and {upper}")
        if config.get("pagination") and fmt != "JSON":
            raise ValueError("Only the mock JSON page-number protocol supports pagination")
        if bool(config.get("records_path")) != bool(config.get("external_id_path")):
            raise ValueError("records_path and external_id_path must be configured together")
        for key in ("records_path", "external_id_path", "next_page_path"):
            if key in config and (not isinstance(config[key], str) or not re.fullmatch(r"[A-Za-z0-9_.]{1,120}", config[key])):
                raise ValueError(f"Invalid {key}")
    else:
        filename = config.get("original_filename")
        if filename is not None and (mode != "FILE" or not isinstance(filename, str) or not 1 <= len(filename) <= 250 or "/" in filename or "\\" in filename):
            raise ValueError("Original filename must be a simple FILE name of at most 250 characters")
        if config.get("env_dir"):
            if mode != "DIRECTORY" or config["env_dir"] != "POC_IMAGES_DIR":
                raise ValueError("Only DIRECTORY supports env_dir=POC_IMAGES_DIR")
            path = images_dir()
        else:
            value = config.get("path") or config.get("relative_path")
            if not isinstance(value, str) or not value:
                raise ValueError("Provide a fixture path")
            path = allowed_path(value)
        if mode == "FILE" and (not path.is_file() or path.suffix.lower() not in EXTENSIONS[fmt]):
            raise ValueError("Input file must exist and match the selected format")
        if mode == "DIRECTORY" and not path.is_dir():
            raise ValueError("Source directory does not exist")
        if "extensions" in config and (not isinstance(config["extensions"], list) or not set(config["extensions"]).issubset(EXTENSIONS[fmt])):
            raise ValueError("Directory extensions must match the format")
        if "delimiter" in config and (not isinstance(config["delimiter"], str) or len(config["delimiter"]) != 1):
            raise ValueError("CSV delimiter must be one character")
    return {"source_code": code, "name": data["name"].strip(), "transport": mode, "data_format": fmt,
            "entity_type": data["entity_type"], "config": config, "field_mapping": mapping, "is_active": data.get("is_active", True)}


def list_sources(engine, company_id):
    with engine.connect() as conn:
        return [dict(x) for x in conn.execute(select(sources).where(sources.c.company_id == identifier(company_id)).order_by(sources.c.name)).mappings()]


def get_source(engine, company_id, source_id):
    with engine.connect() as conn:
        row = conn.execute(select(sources).where(sources.c.company_id == identifier(company_id), sources.c.data_source_id == identifier(source_id))).mappings().first()
    if not row:
        raise LookupError("Source not found for this company")
    return dict(row)


def save_source(engine, company_id, data, source_id=None):
    values = validate_source(data)
    company_id = identifier(company_id)
    if values["transport"] != "HTTP_GET" and not values["config"].get("env_dir"):
        path = allowed_path(values["config"].get("path") or values["config"].get("relative_path", ""))
        uploads = (FIXTURES / "uploads").resolve()
        if path.is_relative_to(uploads) and not path.is_relative_to(uploads / str(company_id)):
            raise ValueError("Uploaded files are scoped to their company")
    if source_id:
        get_source(engine, company_id, source_id)
    source_id = identifier(source_id) if source_id else uuid4()
    try:
        with engine.begin() as conn:
            if not conn.execute(select(Company.company_id).where(Company.company_id == company_id)).first():
                raise LookupError("Company not found")
            if data.get("data_source_id") and identifier(data["data_source_id"]) != source_id:
                raise ValueError("Source identity is server generated")
            if conn.execute(select(sources.c.data_source_id).where(sources.c.data_source_id == source_id)).first():
                conn.execute(update(sources).where(sources.c.data_source_id == source_id, sources.c.company_id == company_id).values(**values, updated_at=func.now()))
            else:
                conn.execute(sources.insert().values(**values, data_source_id=source_id, company_id=company_id))
    except IntegrityError as exc:
        raise ValueError("Source code is already registered for this company") from exc
    return get_source(engine, company_id, source_id)

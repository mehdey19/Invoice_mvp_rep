"""Optional record interpretation after raw response storage; no normalization."""
import csv
import hashlib
import io
import json
from app.acquisition.connectors.base import RawItem
from app.acquisition.connectors.http_connector import get_path


def interpret(source, item):
    fmt = source["data_format"]
    data = None
    if fmt == "JSON":
        data = json.loads(item.payload)
    elif fmt == "CSV":
        list(csv.reader(io.StringIO(item.payload.decode("utf-8-sig")), delimiter=source["config"].get("delimiter", ","), strict=True))
    # XML and binary formats remain opaque in Week 1.
    config = source["config"]
    if fmt != "JSON" or not config.get("records_path"):
        return
    records = get_path(data, config["records_path"])
    if not isinstance(records, list):
        raise ValueError("records_path must resolve to an array")
    if len(records) > 10000:
        raise ValueError("Response exceeds 10000 records")
    for record in records:
        external_id = get_path(record, config["external_id_path"])
        if not isinstance(external_id, (str, int)) or isinstance(external_id, bool) or not str(external_id):
            raise ValueError("Each API record needs a stable scalar external ID")
        # This derived representation is explicitly distinct from original HTTP
        # bytes, which have already been saved as a RESPONSE artifact.
        payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        yield RawItem("record.json", "application/json", payload, str(external_id),
                      {"response_sha256": hashlib.sha256(item.payload).hexdigest(), "page": item.metadata.get("page"),
                       "representation": "canonical JSON record"}, "RECORD")

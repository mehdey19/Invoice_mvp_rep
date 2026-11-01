import mimetypes
from dataclasses import replace
from app.acquisition.connectors.base import RawItem
from app.acquisition.settings import MAX_BYTES, allowed_path


def read_file(path):
    # Bound reads even if the input grows after stat().
    with path.open("rb") as file:
        payload = file.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("Input exceeds 25 MiB")
    mime = {".xml": "application/xml"}.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return RawItem(path.name, mime, payload,
                   external_id=path.name)


class FileConnector:
    def acquire(self, source):
        config = source["config"]
        path = allowed_path(config.get("path") or config.get("relative_path", ""))
        if not path.is_file():
            raise ValueError("Configured input file does not exist")
        item = read_file(path)
        if config.get("original_filename"):
            item = replace(item, filename=config["original_filename"], external_id=config["original_filename"])
        yield item

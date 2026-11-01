"""Server-controlled acquisition boundaries, shared by API, CLI and connectors."""
import os
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "poc_demo" / "fixtures"
MAX_BYTES = 25 * 1024 * 1024
PREVIEW_BYTES = 2 * 1024 * 1024
FORMATS = ("CSV", "JSON", "XML", "PNG", "JPG", "JPEG", "PDF", "IMAGE")
EXTENSIONS = {"CSV": {".csv"}, "JSON": {".json"}, "XML": {".xml"}, "PDF": {".pdf"},
              "PNG": {".png"}, "JPG": {".jpg", ".jpeg"}, "JPEG": {".jpg", ".jpeg"},
              "IMAGE": {".png", ".jpg", ".jpeg"}}


def raw_root():
    return Path(os.environ.get("POC_RAW_DIR", PROJECT_ROOT / "storage/raw/acquired")).resolve()


def images_dir():
    return Path(os.environ.get("POC_IMAGES_DIR", "/home/elmehdi/Desktop/invoices/test_invoices")).resolve()


def allowed_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    roots = [FIXTURES.resolve(), images_dir()]
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError("Path must be inside the POC fixtures or configured POC_IMAGES_DIR")
    return path


def mock_base():
    return os.environ.get("POC_MOCK_BASE_URL", "http://127.0.0.1:9090").rstrip("/")


def allowed_url(value: str) -> str:
    try:
        target = urlsplit(value)
        origins = os.environ.get("POC_ALLOWED_HTTP_ORIGINS", "http://127.0.0.1:9090,http://localhost:9090,http://mock-api:9090").split(",")
        valid_origin = (target.scheme, target.hostname, target.port) in {
            (p.scheme, p.hostname, p.port) for p in map(urlsplit, origins)
        }
        if (len(value) > 2048 or not valid_origin or target.scheme != "http" or target.username or target.password or target.fragment
                or any(key not in {"scenario", "variant", "page", "page_size"} for key, _ in parse_qsl(target.query))
                or not (target.path.startswith("/mock/") or target.path == "/api/invoices")):
            raise ValueError("URL must use an approved local mock service and /mock/ endpoint")
    except (ValueError, TypeError) as exc:
        raise ValueError("URL must use an approved local mock service and /mock/ endpoint") from exc
    return value

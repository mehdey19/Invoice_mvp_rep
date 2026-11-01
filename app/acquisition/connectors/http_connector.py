"""Bounded HTTP transport. Pagination is replayed; page numbers are not checkpoints."""
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import httpx
from app.acquisition.connectors.base import RawItem
from app.acquisition.settings import MAX_BYTES, allowed_url, mock_base


def get_path(data, path):
    for part in path.split(".") if path else []:
        data = data[part]
    return data


class HTTPConnector:
    def acquire(self, source):
        config = source["config"]
        url = allowed_url(config["url"])
        # Existing host-based registrations remain usable in Docker without
        # changing stored source configuration or accepting new destinations.
        parts = urlsplit(url)
        if parts.hostname in {"localhost", "127.0.0.1"} and parts.port == 9090:
            base = urlsplit(mock_base())
            url = allowed_url(urlunsplit(parts._replace(scheme=base.scheme, netloc=base.netloc)))
        paginated = config.get("pagination", False)
        page, visited = 1, set()
        start = time.monotonic()
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            while True:
                if page in visited or len(visited) >= config.get("max_pages", 100):
                    raise ValueError("Pagination cycle or page limit reached")
                if time.monotonic() - start > 120:
                    raise ValueError("HTTP acquisition exceeded 120 seconds")
                visited.add(page)
                request_url = url
                if paginated:
                    parts = urlsplit(url)
                    query = dict(parse_qsl(parts.query))
                    query.update(page=str(page), page_size=str(config.get("page_size", 2)))
                    request_url = urlunsplit(parts._replace(query=urlencode(query)))
                with client.stream("GET", request_url) as res:
                    res.raise_for_status()
                    if res.status_code != 200:
                        raise ValueError(f"Expected HTTP 200; received {res.status_code}; redirects are disabled")
                    chunks, size = [], 0
                    for chunk in res.iter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise ValueError("HTTP response exceeds 25 MiB")
                        chunks.append(chunk)
                    payload = b"".join(chunks)
                    mime = res.headers.get("content-type", "application/octet-stream")
                filename = urlsplit(url).path.rsplit("/", 1)[-1] or "response"
                if "." not in filename:
                    filename += "." + source["data_format"].lower()
                yield RawItem(filename[:250], mime[:100], payload, metadata={"url": request_url, "page": page}, artifact_kind="RESPONSE")
                if not paginated:
                    break
                # Interpretation happens only after the caller has persisted the
                # original response, including malformed payloads.
                import json
                data = json.loads(payload)
                next_page = get_path(data, config.get("next_page_path", "next_page"))
                if next_page is None:
                    break
                if isinstance(next_page, bool) or not isinstance(next_page, int) or next_page < 1:
                    raise ValueError("Mock pagination requires a positive integer next_page")
                page = next_page

from dataclasses import dataclass, field
from typing import Iterator, Protocol


@dataclass(frozen=True)
class RawItem:
    filename: str
    mime_type: str
    payload: bytes
    external_id: str | None = None
    metadata: dict = field(default_factory=dict)
    artifact_kind: str = "FILE"


class Connector(Protocol):
    def acquire(self, source: dict) -> Iterator[RawItem]: ...

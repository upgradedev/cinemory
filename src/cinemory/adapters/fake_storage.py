"""Offline in-memory object store mimicking Backblaze B2 / S3 semantics.

Real put/get/exists over content-addressed keys, plus a run index (JSONL) so the
"data orchestration" story (queryable catalogue of every generated asset) is
demonstrable offline. The real B2 adapter uses the identical interface.
"""
from __future__ import annotations

import json


class FakeStorage:
    def __init__(self, bucket: str = "cinemory-demo") -> None:
        self.bucket = bucket
        self._objects: dict[str, bytes] = {}
        self.index: list[dict] = []

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        self._objects[key] = data
        self.index.append({"key": key, "size": len(data), "content_type": content_type})
        return f"b2://{self.bucket}/{key}"

    def get(self, key: str) -> bytes:
        if key not in self._objects:
            raise KeyError(key)
        return self._objects[key]

    def exists(self, key: str) -> bool:
        return key in self._objects

    def index_jsonl(self) -> str:
        """Serialise the asset catalogue (Genblaze ParquetSink analogue)."""
        return "\n".join(json.dumps(row, sort_keys=True) for row in self.index)

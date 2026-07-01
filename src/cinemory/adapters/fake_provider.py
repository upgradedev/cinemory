"""Offline fake generative-media provider.

Returns *deterministic* bytes derived from the request (model, prompt, inputs),
so orchestration, content-hashing and provenance are exercised for real with no
API calls. Same request -> same bytes -> same SHA-256, which is what the e2e
test asserts on.

This mimics the network boundary ONLY. It does not fake hashing, storage, or
manifest verification — those run for real.
"""
from __future__ import annotations

import hashlib

from ..models import Modality


class FakeMediaProvider:
    name = "fake-genblaze"

    def __init__(self, clip_size: int = 4096) -> None:
        self.clip_size = clip_size
        self.calls: list[dict] = []

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        modality: Modality,
        inputs: list[bytes] | None = None,
        params: dict | None = None,
    ) -> bytes:
        self.calls.append({"model": model, "prompt": prompt, "modality": modality.value})
        seed = hashlib.sha256()
        seed.update(model.encode())
        seed.update(prompt.encode())
        seed.update(modality.value.encode())
        for blob in inputs or []:
            seed.update(hashlib.sha256(blob).digest())
        # Deterministically expand the seed to a plausible clip-sized artifact.
        out = bytearray(b"FAKECLIP")
        digest = seed.digest()
        while len(out) < self.clip_size:
            digest = hashlib.sha256(digest).digest()
            out += digest
        return bytes(out[: self.clip_size])

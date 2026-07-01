"""Verifiable provenance — the signature Genblaze feature, implemented for real
and fully offline.

Every generated asset is content-addressed by SHA-256. A run manifest captures
provider, model, prompt, params, timestamps and every asset hash. The manifest
itself is sealed with a canonical SHA-256 (``manifest_hash``) computed over its
sorted-key JSON, so tampering with any recorded field is detectable via
:func:`verify_manifest`.

The manifest can be embedded into the reel container (trailing chunk) and
extracted/verified later, mirroring Genblaze's ``Mp4Handler``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from .models import ReelResult, StepRecord

_MAGIC = b"\n--CINEMORY-MANIFEST-v1--\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_manifest(result: ReelResult) -> dict:
    """Build the manifest dict and seal it with a canonical hash."""
    body = {
        "schema": "cinemory/manifest/v1",
        "reel_name": result.reel_name,
        "reel_asset": _asset_dict(result.reel_asset),
        "steps": [_step_dict(s) for s in result.steps],
    }
    body["manifest_hash"] = sha256_bytes(_canonical(body))
    return body


def _asset_dict(asset) -> dict:
    d = asdict(asset)
    d["modality"] = asset.modality.value
    return d


def _step_dict(step: StepRecord) -> dict:
    d = asdict(step)
    d["modality"] = step.modality.value
    d["asset"] = _asset_dict(step.asset)
    return d


def verify_manifest(manifest: dict) -> bool:
    """Recompute the canonical hash and confirm the manifest is intact."""
    claimed = manifest.get("manifest_hash")
    if not claimed:
        return False
    body = {k: v for k, v in manifest.items() if k != "manifest_hash"}
    return sha256_bytes(_canonical(body)) == claimed


def verify_asset(manifest: dict, key: str, data: bytes) -> bool:
    """Confirm that ``data`` matches the reel asset hash recorded in the manifest."""
    return manifest.get("reel_asset", {}).get("sha256") == sha256_bytes(data)


def embed(container: bytes, manifest: dict) -> bytes:
    """Append the manifest as a trailing, extractable chunk."""
    return container + _MAGIC + _canonical(manifest)


def extract(container: bytes) -> dict | None:
    """Recover an embedded manifest, or ``None`` if not present."""
    idx = container.rfind(_MAGIC)
    if idx == -1:
        return None
    payload = container[idx + len(_MAGIC):]
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None

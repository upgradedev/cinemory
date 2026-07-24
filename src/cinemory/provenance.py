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
from collections.abc import Callable
from dataclasses import asdict, dataclass

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
        "occasion": result.occasion,
        "occasion_style": result.occasion_style,
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


def extract_payload(container: bytes) -> bytes | None:
    """Recover the reel bytes that precede an embedded manifest.

    The payload-side inverse of :func:`embed`: returns everything before the
    trailing manifest chunk (i.e. the original reel container), or ``None`` when
    no manifest is embedded. Used by :func:`verify_all` to confirm a stored
    ``reel.provenance.mp4`` wraps exactly the sealed reel bytes.
    """
    idx = container.rfind(_MAGIC)
    if idx == -1:
        return None
    return container[:idx]


# ── aggregate named-check verification receipt ────────────────────────────────
@dataclass
class VerificationReceipt:
    """The outcome of :func:`verify_all` — a named-check attestation.

    ``checks`` is a list of ``{id, label, passed, evidence}`` rows, ``success``
    is the AND of every check, and ``digest`` content-addresses the receipt
    itself. Always fully shaped — even a totally failing verification returns a
    well-formed receipt rather than raising.
    """

    checks: list[dict]
    success: bool
    digest: str

    def to_dict(self) -> dict:
        return {"checks": self.checks, "success": self.success, "digest": self.digest}


def verify_all(
    manifest: dict,
    fetch_bytes: Callable[[str], bytes | None],
) -> VerificationReceipt:
    """Re-verify a sealed reel from stored bytes, as a named-check receipt.

    Built ON TOP of the bare-bool :func:`verify_manifest`; every check is re-run
    from primary evidence (the stored artifact bytes and the sealed body), never
    a cached boolean:

      * ``seal.manifest_hash`` — the canonical seal recomputes;
      * ``artifact.reel`` — the stored reel bytes re-hash to the sealed hash;
      * ``artifact.provenance_reel`` — the stored ``reel.provenance.mp4`` wraps
        exactly the sealed reel bytes (its reel payload re-hashes to the sealed
        reel hash);
      * ``artifact.clip.<i>`` — each per-step clip's stored bytes re-hash to its
        sealed hash;
      * ``structural.embedded_manifest`` — the manifest embedded in the
        provenance-reel equals the standalone manifest;
      * ``structural.step_assets_present`` — every step's asset resolves in the
        store;
      * ``structural.source_citation`` — every step cites non-empty
        ``source_sha256s`` that resolve to stored input photos;
      * ``structural.provider_model`` — every step names a provider and model.

    ``fetch_bytes(logical)`` returns the stored bytes for a logical artifact
    name — ``"reel"``, ``"provenance_reel"``, ``"clip:<sha256>"`` (a per-step
    clip) or ``"photo:<sha256>"`` (a cited source photo) — or ``None`` if it is
    absent. It is only ever called inside a guarded check, so a raising or
    ``None``-returning fetcher degrades that one check to ``passed: false`` with
    the reason as evidence — the receipt is always returned intact.
    """
    if not isinstance(manifest, dict):
        manifest = {}
    checks: list[dict] = []

    def record(check_id: str, label: str,
               fn: Callable[[], tuple[bool, str]]) -> None:
        try:
            passed, evidence = fn()
        except Exception as exc:  # a raising check is a failing check (fail-closed)
            passed, evidence = False, f"{type(exc).__name__}: {exc}"
        checks.append({"id": check_id, "label": label,
                       "passed": bool(passed), "evidence": evidence})

    reel_asset = manifest.get("reel_asset")
    reel_recorded = reel_asset.get("sha256") if isinstance(reel_asset, dict) else None
    steps = manifest.get("steps") or []

    def _seal() -> tuple[bool, str]:
        ok = verify_manifest(manifest)
        return ok, ("canonical SHA-256 over the sealed body matches manifest_hash"
                    if ok else "recomputed canonical SHA-256 does NOT match manifest_hash")

    record("seal.manifest_hash", "Manifest seal recomputes (SHA-256)", _seal)

    def _reel() -> tuple[bool, str]:
        if not reel_recorded:
            return False, "manifest records no reel asset hash"
        data = fetch_bytes("reel")
        if data is None:
            return False, "stored reel bytes could not be fetched"
        actual = sha256_bytes(data)
        return actual == reel_recorded, (
            f"re-hashed stored reel {actual[:12]}… "
            + ("matches the sealed hash" if actual == reel_recorded
               else f"!= sealed {reel_recorded[:12]}…"))

    record("artifact.reel", "Reel bytes match the sealed hash", _reel)

    def _provenance_reel() -> tuple[bool, str]:
        if not reel_recorded:
            return False, "manifest records no reel asset hash to bind against"
        data = fetch_bytes("provenance_reel")
        if data is None:
            return False, "stored provenance-reel bytes could not be fetched"
        payload = extract_payload(data)
        if payload is None:
            return False, "provenance-reel carries no embedded manifest chunk"
        actual = sha256_bytes(payload)
        return actual == reel_recorded, (
            "provenance-reel wraps exactly the sealed reel bytes"
            if actual == reel_recorded
            else f"provenance-reel payload {actual[:12]}… != sealed reel {reel_recorded[:12]}…")

    record("artifact.provenance_reel", "Provenance-reel wraps the sealed reel",
           _provenance_reel)

    for i, step in enumerate(steps):
        asset = (step or {}).get("asset") or {}
        recorded = asset.get("sha256")

        def _clip(recorded: str | None = recorded, i: int = i) -> tuple[bool, str]:
            if not recorded:
                return False, f"step {i} records no clip hash"
            data = fetch_bytes(f"clip:{recorded}")
            if data is None:
                return False, f"stored clip bytes for step {i} could not be fetched"
            actual = sha256_bytes(data)
            return actual == recorded, (
                f"step {i} clip {actual[:12]}… "
                + ("matches the sealed hash" if actual == recorded
                   else f"!= sealed {recorded[:12]}…"))

        record(f"artifact.clip.{i}", f"Step {i} clip bytes match the sealed hash", _clip)

    def _embedded_manifest() -> tuple[bool, str]:
        data = fetch_bytes("provenance_reel")
        if data is None:
            return False, "stored provenance-reel bytes could not be fetched"
        recovered = extract(data)
        if recovered is None:
            return False, "no manifest embedded in the provenance-reel"
        return recovered == manifest, (
            "embedded manifest equals the standalone manifest"
            if recovered == manifest
            else "embedded manifest differs from the standalone manifest")

    record("structural.embedded_manifest",
           "Embedded manifest equals the standalone manifest", _embedded_manifest)

    def _assets_present() -> tuple[bool, str]:
        if not steps:
            return False, "manifest carries no steps"
        missing = [i for i, s in enumerate(steps)
                   if not ((s or {}).get("asset") or {}).get("sha256")
                   or fetch_bytes(f"clip:{((s or {}).get('asset') or {}).get('sha256')}") is None]
        return (not missing), ("every step asset resolves in the store"
                               if not missing
                               else f"steps {missing} have an unresolvable asset")

    record("structural.step_assets_present", "Every step asset resolves in the store",
           _assets_present)

    def _source_citation() -> tuple[bool, str]:
        if not steps:
            return False, "manifest carries no steps"
        bad = []
        for i, s in enumerate(steps):
            cites = (s or {}).get("source_sha256s") or []
            if not cites or any(fetch_bytes(f"photo:{c}") is None for c in cites):
                bad.append(i)
        return (not bad), ("every step cites source photos that resolve in the store"
                           if not bad
                           else f"steps {bad} miss a resolvable source-photo citation")

    record("structural.source_citation",
           "Every step cites resolvable source photos", _source_citation)

    def _provider_model() -> tuple[bool, str]:
        if not steps:
            return False, "manifest carries no steps"
        bad = [i for i, s in enumerate(steps)
               if not ((s or {}).get("provider") and (s or {}).get("model"))]
        return (not bad), ("every step names a provider and model"
                           if not bad else f"steps {bad} miss a provider/model")

    record("structural.provider_model", "Every step names a provider and model",
           _provider_model)

    success = all(c["passed"] for c in checks)
    digest = sha256_bytes(_canonical({"checks": checks, "success": success}))
    return VerificationReceipt(checks=checks, success=success, digest=digest)

#!/usr/bin/env python3
"""Cinemory submission READINESS GATE.

A machine-checkable gate that scores this repo against the four Backblaze
Generative Media Challenge criteria — **Real-World Utility**, **Production
Readiness**, **B2 Storage & Orchestration**, **Use of Genblaze** — and reports a
weighted completeness percentage the CI job enforces.

Design principle: **real evidence, not file-existence.** Every automatable check
*drives the actual code path* (runs the pipeline, hits the API via ``TestClient``,
exercises the real B2 adapter against an in-memory S3 stub, drives the real
Genblaze SDK) and asserts on observable behaviour. A check is one of:

  * ``pass``       — the real path was exercised and behaved correctly
  * ``fail``       — the real path was exercised and misbehaved (fails the gate)
  * ``user-gated`` — genuinely needs a human-held credential / live deploy
                     (a write-entitled B2 key, a GMI_API_KEY, a Cloud Run
                     redeploy). These are *excluded* from the automatable %
                     numerator **and** denominator, and listed for the user.

The gate FAILS (exit 1) when the automatable completeness drops below the
threshold (default 95%). It also emits ``readiness.json`` for CI to archive.

Run:
    python scripts/readiness.py                 # human report + readiness.json
    python scripts/readiness.py --json out.json --min 95
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FRONTEND_API = _REPO_ROOT / "frontend" / "src" / "lib" / "api.ts"

# A tiny, valid 1x1 PNG so the ingest path sees genuine image bytes.
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc``\x00\x00\x00\x04"
    b"\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ── check + criterion model ──────────────────────────────────────────────────
@dataclass
class CheckResult:
    id: str
    label: str
    status: str  # "pass" | "fail" | "user-gated"
    weight: int
    automatable: bool
    detail: str

    @property
    def passed(self) -> bool:
        return self.status == "pass"


@dataclass
class Check:
    id: str
    label: str
    weight: int
    run: Callable[[], tuple[bool, str]] | None = None
    user_gated: bool = False
    gate_detail: str = ""

    def evaluate(self) -> CheckResult:
        if self.user_gated:
            return CheckResult(self.id, self.label, "user-gated", self.weight,
                               automatable=False, detail=self.gate_detail)
        assert self.run is not None
        try:
            ok, detail = self.run()
        except Exception as exc:  # a raising check is a failing check (never crash the gate)
            return CheckResult(self.id, self.label, "fail", self.weight,
                               automatable=True, detail=f"{type(exc).__name__}: {exc}")
        return CheckResult(self.id, self.label, "pass" if ok else "fail", self.weight,
                           automatable=True, detail=detail)


@dataclass
class Criterion:
    id: str
    label: str
    weight: int  # equal-weighted (25 each → /100)
    checks: list[Check] = field(default_factory=list)


# ── evidence runners (each drives the REAL path) ─────────────────────────────
def _fresh_client(mode: str = "offline"):
    """A TestClient over a freshly-reloaded api module at the requested mode.

    Returns ``(client, restore)``; call ``restore()`` to reload the module back
    to the offline default so module-level storage/provider state never leaks
    into a later check.
    """
    from fastapi.testclient import TestClient

    prev = os.environ.get("CINEMORY_MODE")
    os.environ["CINEMORY_MODE"] = mode
    import cinemory.api as api

    reloaded = importlib.reload(api)

    def restore() -> None:
        if prev is None:
            os.environ.pop("CINEMORY_MODE", None)
        else:
            os.environ["CINEMORY_MODE"] = prev
        importlib.reload(api)

    return TestClient(reloaded.app), restore


def check_utility_upload_multipart_e2e() -> tuple[bool, str]:
    """Frontend's exact target: POST /reels/upload-multipart → pipeline → sealed
    provenance, fetchable back by name and cryptographically verifiable."""
    from cinemory.provenance import verify_manifest

    client, restore = _fresh_client()
    try:
        files = [("files", (f"p{i}.png", _PNG_1x1, "image/png")) for i in range(3)]
        r = client.post("/reels/upload-multipart", files=files,
                        data={"name": "readiness-mp", "occasion": "anniversary", "chapters": 2})
        if r.status_code != 200:
            return False, f"upload-multipart returned {r.status_code}"
        body = r.json()
        if len(body["reel_sha256"]) != 64 or not body["manifest_hash"] or body["steps"] != 3:
            return False, f"unexpected reel body: {body}"
        manifest = client.get("/reels/readiness-mp").json()
        if not verify_manifest(manifest):
            return False, "fetched manifest failed SHA-256 verification"
        return True, "3 real photos → multipart → 3 clips → sealed+verified manifest"
    finally:
        restore()


def check_utility_base64_upload() -> tuple[bool, str]:
    """The dependency-free base64 ingest path also seals real provenance."""
    import base64

    client, restore = _fresh_client()
    try:
        photos = [{"filename": "p.png", "content_base64": base64.b64encode(_PNG_1x1).decode()}]
        r = client.post("/reels/upload", json={"name": "readiness-b64", "photos": photos})
        if r.status_code != 200:
            return False, f"base64 upload returned {r.status_code}"
        if len(r.json()["reel_sha256"]) != 64:
            return False, "reel sha256 not sealed"
        return True, "base64 photo bytes → sealed reel"
    finally:
        restore()


def check_utility_frontend_client_contract() -> tuple[bool, str]:
    """Static client-contract check (the frontend CI vitest job is the behavioural
    gate). Confirms the React client streams real File bytes to the multipart
    endpoint — i.e. the frontend half of the utility flow is wired, not stubbed."""
    if not _FRONTEND_API.is_file():
        return False, f"missing {_FRONTEND_API}"
    src = _FRONTEND_API.read_text(encoding="utf-8")
    required = ['"/reels/upload-multipart"', "new FormData()", 'form.append("files"']
    missing = [tok for tok in required if tok not in src]
    if missing:
        return False, f"api.ts missing client-contract tokens: {missing}"
    return True, "uploadReel builds FormData and streams File bytes to /reels/upload-multipart"


def check_utility_occasion_themes() -> tuple[bool, str]:
    """The B2B/consumer utility rests on selectable occasion themes."""
    client, restore = _fresh_client()
    try:
        keys = {o["key"] for o in client.get("/occasions").json()["occasions"]}
        needed = {"anniversary", "graduation", "birthday", "wedding",
                  "year-in-review", "business-event"}
        if not needed.issubset(keys):
            return False, f"missing occasions: {needed - keys}"
        return True, f"{len(keys)} occasion themes served"
    finally:
        restore()


def check_prod_never_500_offline_degrade() -> tuple[bool, str]:
    """Production keystone: CINEMORY_MODE=live with NO credentials still returns a
    real reel + sealed manifest (never 500s), and /health honestly reports the
    degraded backends."""
    for name in ("B2_KEY_ID", "B2_APP_KEY", "B2_ENDPOINT_URL", "B2_REGION",
                 "B2_BUCKET_NAME", "B2_APPLICATION_KEY_ID", "B2_APPLICATION_KEY",
                 "B2_S3_ENDPOINT", "B2_KEY_PREFIX", "B2_PREFIX", "GMI_API_KEY"):
        os.environ.pop(name, None)
    client, restore = _fresh_client(mode="live")
    try:
        r = client.post("/reels", json={"name": "readiness-live", "chapters": 2,
                                        "per_chapter": 2})
        if r.status_code != 200:
            return False, (f"live-no-creds POST /reels returned {r.status_code} "
                           "(should degrade, not 500)")
        body = r.json()
        if len(body["reel_sha256"]) != 64 or not body["manifest_hash"]:
            return False, "degraded reel not sealed"
        health = client.get("/health").json()
        if health["mode"] != "live":
            return False, f"health mode not honest: {health['mode']}"
        if health["provider"] != "fake-genblaze" or health["storage"] != "FakeStorage":
            return False, f"health did not surface degraded backends: {health}"
        return True, "live+no-creds → 200 sealed reel; /health surfaces degraded fakes"
    finally:
        restore()


def check_prod_invalid_request_400() -> tuple[bool, str]:
    """Bad input is a 400, never a 500 — the API validates before doing work."""
    client, restore = _fresh_client()
    try:
        empty = client.post("/reels/upload", json={"name": "e", "photos": []})
        bad = client.post("/reels/upload", json={
            "name": "b", "photos": [{"filename": "p.png", "content_base64": "not!b64!!"}]})
        if empty.status_code != 400:
            return False, f"empty photos returned {empty.status_code}, expected 400"
        if bad.status_code != 400:
            return False, f"bad base64 returned {bad.status_code}, expected 400"
        return True, "empty + malformed uploads → 400 (not 500)"
    finally:
        restore()


def check_prod_health_surfaces_backends() -> tuple[bool, str]:
    client, restore = _fresh_client()
    try:
        health = client.get("/health").json()
        for key in ("mode", "provider", "storage"):
            if key not in health:
                return False, f"/health missing {key!r}"
        return True, "/health reports mode + effective provider + storage"
    finally:
        restore()


def check_b2_content_addressed_keys() -> tuple[bool, str]:
    """Every stored asset lives under a content-addressed (SHA-256) key."""
    from cinemory.adapters import FakeMediaProvider, FakeStorage
    from cinemory.pipeline import ReelPipeline
    from cinemory.synthetic import synth_reel_spec

    storage = FakeStorage(bucket="readiness")
    result = ReelPipeline(FakeMediaProvider(), storage).run(
        synth_reel_spec("cak", chapters=2, per_chapter=1))
    if not result.reel_asset.sha256 or len(result.reel_asset.sha256) != 64:
        return False, "reel asset not content-addressed"
    # Every index key must embed the asset's own SHA-256 (hierarchical layout).
    for row in storage.index:
        parts = row["key"].split("/")
        if len(parts) < 4:  # <reel>/<kind>/<shard>/<sha>/<name>
            return False, f"non-content-addressed key: {row['key']}"
        if not any(len(p) == 64 for p in parts):
            return False, f"no SHA-256 segment in key: {row['key']}"
    return True, f"{len(storage.index)} assets stored under content-addressed keys"


def check_b2_sha256_manifest_chain() -> tuple[bool, str]:
    """The manifest is SHA-256-sealed, tamper-evident, and embeddable+recoverable."""
    from cinemory.adapters import FakeMediaProvider, FakeStorage
    from cinemory.pipeline import ReelPipeline
    from cinemory.provenance import build_manifest, extract, sha256_bytes, verify_manifest
    from cinemory.synthetic import synth_reel_spec

    storage = FakeStorage(bucket="readiness")
    result = ReelPipeline(FakeMediaProvider(), storage).run(
        synth_reel_spec("chain", chapters=2, per_chapter=1))
    manifest = build_manifest(result)
    if not verify_manifest(manifest):
        return False, "freshly sealed manifest failed verification"
    # Tamper-evidence: mutate a recorded hash → verification must reject it.
    tampered = json.loads(json.dumps(manifest))
    tampered["reel_asset"]["sha256"] = "0" * 64
    if verify_manifest(tampered):
        return False, "tampered manifest passed verification (tamper-evidence broken)"
    # The embedded-in-reel manifest is recoverable and still verifies.
    prov_key = next(r["key"] for r in storage.index if r["key"].endswith("reel.provenance.mp4"))
    recovered = extract(storage.get(prov_key))
    if recovered is None or not verify_manifest(recovered):
        return False, "embedded provenance not recoverable/verifiable"
    reel_key = next(r["key"] for r in storage.index
                    if r["key"].startswith("chain/reels/") and r["key"].endswith("reel.mp4"))
    if sha256_bytes(storage.get(reel_key)) != result.reel_asset.sha256:
        return False, "stored reel bytes do not match sealed hash"
    return True, "manifest sealed + tamper-evident + embedded/recoverable + byte-exact"


def check_b2_jsonl_index_roundtrip() -> tuple[bool, str]:
    """The real B2 adapter keeps a durable, queryable index.jsonl in the bucket:
    a fresh worker resolves a reel a prior instance wrote. Driven against an
    in-memory S3-compatible stub (no boto3/creds), so it is real adapter code."""
    for name in ("B2_KEY_ID", "B2_APP_KEY", "B2_ENDPOINT_URL", "B2_REGION",
                 "B2_BUCKET_NAME", "B2_APPLICATION_KEY_ID", "B2_APPLICATION_KEY",
                 "B2_S3_ENDPOINT", "B2_KEY_PREFIX", "B2_PREFIX"):
        os.environ.pop(name, None)
    os.environ["B2_BUCKET_NAME"] = "readiness-live"
    os.environ["B2_S3_ENDPOINT"] = "https://s3.eu-central-003.backblazeb2.com"
    os.environ["B2_KEY_PREFIX"] = "cin"

    from cinemory.adapters.b2_storage import B2Storage

    class _Body:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read(self) -> bytes:
            return self._data

    class _FakeS3:
        def __init__(self) -> None:
            self.store: dict[tuple[str, str], bytes] = {}

        def put_object(self, *, Bucket, Key, Body, ContentType=None):  # noqa: N803
            self.store[(Bucket, Key)] = Body
            return {}

        def get_object(self, *, Bucket, Key):  # noqa: N803
            if (Bucket, Key) not in self.store:
                raise KeyError(Key)
            return {"Body": _Body(self.store[(Bucket, Key)])}

    try:
        s3 = _FakeS3()
        key = "graduation/manifests/ab/abcd/manifest.json"
        payload = json.dumps({"manifest_hash": "cafe"}).encode()
        writer = B2Storage(client=s3)
        url = writer.put(key, payload, content_type="application/json")
        # Logical key indexed (pre-prefix); actual object + index.jsonl prefixed.
        if writer.index[0]["key"] != key:
            return False, "index stored the prefixed key, not the logical key"
        if ("readiness-live", f"cin/{key}") not in s3.store:
            return False, "object not written under key prefix"
        if ("readiness-live", "cin/index.jsonl") not in s3.store:
            return False, "index.jsonl not persisted durably in the bucket"
        if not url.endswith(f"cin/{key}"):
            return False, f"unexpected object URL: {url}"
        # Fresh worker (new instance) inherits + resolves the durable catalogue.
        reader = B2Storage(client=s3)
        match = next((r for r in reader.index
                      if r["key"].startswith("graduation/manifests/")), None)
        if match is None or json.loads(reader.get(match["key"])) != {"manifest_hash": "cafe"}:
            return False, "second instance could not resolve the first instance's reel"
        return True, "durable index.jsonl round-trips across instances (real B2 adapter)"
    finally:
        for name in ("B2_BUCKET_NAME", "B2_S3_ENDPOINT", "B2_KEY_PREFIX"):
            os.environ.pop(name, None)


def _genblaze_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("genblaze_core") is not None


def check_genblaze_real_sdk_contract() -> tuple[bool, str]:
    """Drive the adapter through a REAL genblaze_core.Pipeline (SDK's own mock
    provider) — bytes flow end-to-end and the SDK-sealed manifest verifies."""
    if not _genblaze_available():
        return False, "genblaze-core not installed (it is in requirements-dev.txt; CI installs it)"
    import hashlib

    from genblaze_core.models.asset import Asset as GbAsset
    from genblaze_core.testing import MockProvider

    from cinemory.adapters.genblaze_provider import GenblazeMediaProvider
    from cinemory.models import Modality

    payload = b"READINESS-CLIP" + b"\x00\x01\x02" * 256
    sha = hashlib.sha256(payload).hexdigest()
    url = "https://mock.test/generated.mp4"
    adapter = GenblazeMediaProvider(
        provider_obj=MockProvider(name="mock-video",
                                  assets=[GbAsset(url=url, media_type="video/mp4", sha256=sha)]),
        downloader=lambda _u: payload,
    )
    out = adapter.generate(model="Kling-Image2Video-V2.1-Master",
                           prompt="a quiet memory", modality=Modality.VIDEO)
    if out != payload:
        return False, "bytes did not flow through the real SDK pipeline"
    if adapter.last_manifest is None or adapter.last_manifest.verify_hash() is not True:
        return False, "Genblaze did not seal a verifiable manifest"
    return True, "real genblaze_core.Pipeline drives adapter; SDK manifest verifies"


def check_genblaze_tamper_evidence() -> tuple[bool, str]:
    """Genblaze's per-asset SHA-256 is chained into Cinemory provenance: bytes
    that don't match the sealed hash are rejected, not returned."""
    if not _genblaze_available():
        return False, "genblaze-core not installed"
    from genblaze_core.models.asset import Asset as GbAsset
    from genblaze_core.testing import MockProvider

    from cinemory.adapters.genblaze_provider import GenblazeMediaProvider
    from cinemory.models import Modality

    adapter = GenblazeMediaProvider(
        provider_obj=MockProvider(name="mock-video", assets=[
            GbAsset(url="https://mock.test/tampered.mp4", media_type="video/mp4",
                    sha256="a" * 64)]),
        downloader=lambda _u: b"different-bytes-than-were-sealed",
    )
    try:
        adapter.generate(model="mock", prompt="x", modality=Modality.VIDEO)
    except ValueError as exc:
        if "provenance mismatch" in str(exc):
            return True, "sealed-hash mismatch rejected (provenance mismatch)"
        return False, f"raised ValueError but not a provenance mismatch: {exc}"
    return False, "tampered asset was NOT rejected (tamper-evidence broken)"


def check_genblaze_sink_readback() -> tuple[bool, str]:
    """The load-bearing path: the adapter reads durable bytes back through the
    Genblaze ObjectStorageSink backend (no second network download)."""
    if not _genblaze_available():
        return False, "genblaze-core not installed"
    import hashlib

    from genblaze_core.models.asset import Asset as GbAsset
    from genblaze_core.storage.base import StorageBackend
    from genblaze_core.testing import MockProvider

    from cinemory.adapters.genblaze_provider import GenblazeMediaProvider
    from cinemory.models import Modality

    class MemBackend(StorageBackend):
        _PREFIX = "memory://bucket/"

        def __init__(self) -> None:
            self.store: dict[str, bytes] = {}

        def put(self, key, data, *, content_type=None, metadata=None, extra_args=None):
            self.store[key] = bytes(data) if isinstance(data, bytes | bytearray) else data.read()
            return key

        def get(self, key):
            return self.store[key]

        def exists(self, key):
            return key in self.store

        def delete(self, key):
            self.store.pop(key, None)

        def get_url(self, key, *, expires_in=3600):
            return self.get_durable_url(key)

        def get_durable_url(self, key):
            return f"{self._PREFIX}{key}"

        def key_from_url(self, url):
            return url[len(self._PREFIX):] if url.startswith(self._PREFIX) else None

    payload = b"REAL-CLIP-BYTES" + b"\x07\x08" * 200
    sha = hashlib.sha256(payload).hexdigest()
    backend = MemBackend()
    backend.put("assets/clip0.mp4", payload)
    url = backend.get_durable_url("assets/clip0.mp4")

    def _forbid(_u: str) -> bytes:
        raise AssertionError("must read back through the backend, not download")

    adapter = GenblazeMediaProvider(
        provider_obj=MockProvider(name="mock-video", assets=[
            GbAsset(url=url, media_type="video/mp4", sha256=sha, size_bytes=len(payload))]),
        backend=backend,
        downloader=_forbid,
    )
    out = adapter.generate(model="m", prompt="p", modality=Modality.VIDEO)
    if out != payload:
        return False, "bytes did not round-trip through the Genblaze sink backend"
    return True, "asset read back through ObjectStorageSink backend (no download)"


# ── criteria wiring ──────────────────────────────────────────────────────────
def build_criteria() -> list[Criterion]:
    return [
        Criterion("utility", "Real-World Utility", 25, [
            Check("utility.upload_multipart_e2e",
                  "Real-photo upload E2E (frontend→/reels/upload-multipart→pipeline→provenance)",
                  3, run=check_utility_upload_multipart_e2e),
            Check("utility.base64_upload",
                  "Dependency-free base64 photo ingest seals provenance",
                  2, run=check_utility_base64_upload),
            Check("utility.frontend_client_contract",
                  "React client streams real File bytes to the multipart endpoint",
                  2, run=check_utility_frontend_client_contract),
            Check("utility.occasion_themes",
                  "Six occasion themes served (consumer + B2B wedge)",
                  1, run=check_utility_occasion_themes),
        ]),
        Criterion("production", "Production Readiness", 25, [
            Check("production.never_500_offline_degrade",
                  "Live mode with no creds never 500s; /health surfaces degraded backends",
                  3, run=check_prod_never_500_offline_degrade),
            Check("production.invalid_request_400",
                  "Invalid uploads return 400, never 500",
                  2, run=check_prod_invalid_request_400),
            Check("production.health_surfaces_backends",
                  "/health surfaces effective provider + storage",
                  1, run=check_prod_health_surfaces_backends),
            Check("production.live_redeploy",
                  "Cloud Run redeployed with entitled creds; /health = mode=live "
                  "provider=genblaze storage=B2Storage",
                  2, user_gated=True,
                  gate_detail="Run `bash deploy/deploy-cloudrun.sh` with GMI_API_KEY + the "
                  "write-entitled B2 vars, then confirm "
                  "https://cinemory-595784992266.europe-west1.run.app/health reports "
                  "mode=live, provider=genblaze, storage=B2Storage "
                  "(needs the write-entitled key)."),
        ]),
        Criterion("b2", "B2 Storage & Orchestration", 25, [
            Check("b2.content_addressed_keys",
                  "Every asset stored under a content-addressed SHA-256 key",
                  2, run=check_b2_content_addressed_keys),
            Check("b2.sha256_manifest_chain",
                  "SHA-256 manifest: sealed, tamper-evident, embedded+recoverable",
                  2, run=check_b2_sha256_manifest_chain),
            Check("b2.jsonl_index_roundtrip",
                  "Durable index.jsonl round-trips across instances (real B2 adapter, mock S3)",
                  2, run=check_b2_jsonl_index_roundtrip),
            Check("b2.live_objects_written",
                  "Real B2 objects (reel + manifest + index.jsonl) written to the live bucket",
                  2, user_gated=True,
                  gate_detail="Provision a B2 application key entitled for PutObject, then run "
                  "`CINEMORY_MODE=live bash demo/capture-demo.sh` and confirm the reel, "
                  "manifest, and index.jsonl objects landed in the bucket (needs the "
                  "write-entitled key)."),
        ]),
        Criterion("genblaze", "Use of Genblaze", 25, [
            Check("genblaze.real_sdk_contract",
                  "Adapter drives a real genblaze_core.Pipeline; SDK manifest verifies",
                  3, run=check_genblaze_real_sdk_contract),
            Check("genblaze.tamper_evidence",
                  "Genblaze per-asset SHA-256 chained in; mismatched bytes rejected",
                  2, run=check_genblaze_tamper_evidence),
            Check("genblaze.sink_readback",
                  "Asset read back through Genblaze ObjectStorageSink backend",
                  2, run=check_genblaze_sink_readback),
            Check("genblaze.live_reel_generated",
                  "A real generated reel produced live (not the deterministic fallback)",
                  2, user_gated=True,
                  gate_detail="Issue a GMI_API_KEY (GMI Cloud gives ~270 free credits) and run one "
                  "`CINEMORY_MODE=live` generation; confirm a real generated reel, not the "
                  "offline deterministic fallback (needs the live GMI key)."),
        ]),
    ]


# ── scoring ──────────────────────────────────────────────────────────────────
def evaluate() -> dict:
    criteria = build_criteria()
    crit_reports: list[dict] = []
    user_gated: list[dict] = []
    auto_score_sum = 0.0  # Σ over criteria of (criterion_weight × automatable pass fraction)
    full_score_sum = 0.0  # same, but user-gated checks counted as pending in the denominator

    for crit in criteria:
        results = [c.evaluate() for c in crit.checks]
        auto = [r for r in results if r.automatable]
        auto_total = sum(r.weight for r in auto) or 1
        auto_pass = sum(r.weight for r in auto if r.passed)
        full_total = sum(r.weight for r in results) or 1
        auto_pct = 100.0 * auto_pass / auto_total
        full_pct = 100.0 * auto_pass / full_total
        auto_score_sum += crit.weight * auto_pass / auto_total
        full_score_sum += crit.weight * auto_pass / full_total

        for r in results:
            if r.status == "user-gated":
                user_gated.append({"id": r.id, "criterion": crit.id,
                                   "label": r.label, "action": r.detail})
        crit_reports.append({
            "id": crit.id,
            "label": crit.label,
            "weight": crit.weight,
            "automatable_pct": round(auto_pct, 1),
            "full_pct_user_gated_pending": round(full_pct, 1),
            "checks": [{"id": r.id, "label": r.label, "status": r.status,
                        "weight": r.weight, "automatable": r.automatable,
                        "detail": r.detail} for r in results],
        })

    return {
        "schema": "cinemory/readiness/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "challenge": "Backblaze Generative Media Challenge",
        "target_pct": 90,
        "automatable_pct": round(auto_score_sum, 1),
        "full_pct_user_gated_pending": round(full_score_sum, 1),
        "criteria": crit_reports,
        "user_gated": user_gated,
    }


# ── rendering + CLI ──────────────────────────────────────────────────────────
_ICON = {"pass": "PASS", "fail": "FAIL", "user-gated": "GATE"}


def render(report: dict, threshold: float) -> str:
    lines: list[str] = []
    lines.append("=" * 74)
    lines.append(" CINEMORY READINESS GATE — " + report["challenge"])
    lines.append("=" * 74)
    for crit in report["criteria"]:
        lines.append("")
        lines.append(f"[{crit['label']}]  automatable {crit['automatable_pct']}%  "
                     f"(full {crit['full_pct_user_gated_pending']}%)")
        for c in crit["checks"]:
            lines.append(f"  {_ICON[c['status']]}  {c['id']}")
            lines.append(f"        {c['detail']}")
    lines.append("")
    lines.append("-" * 74)
    lines.append(f" Automatable completeness : {report['automatable_pct']}%   "
                 f"(gate threshold {threshold}%)")
    lines.append(f" Full (user-gated pending): {report['full_pct_user_gated_pending']}%   "
                 f"target {report['target_pct']}%")
    if report["user_gated"]:
        lines.append("")
        lines.append(" USER-GATED (needs a human-held credential / live deploy):")
        for g in report["user_gated"]:
            lines.append(f"   • [{g['criterion']}] {g['label']}")
            lines.append(f"       {g['action']}")
    lines.append("-" * 74)
    passed = report["automatable_pct"] >= threshold
    lines.append(f" GATE: {'PASS' if passed else 'FAIL'} "
                 f"(automatable {report['automatable_pct']}% "
                 f"{'>=' if passed else '<'} {threshold}%)")
    lines.append("=" * 74)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cinemory submission readiness gate")
    parser.add_argument("--json", default=str(_REPO_ROOT / "readiness.json"),
                        help="path to write readiness.json (default: repo root)")
    parser.add_argument("--min", type=float, default=95.0,
                        help="minimum automatable completeness %% to pass (default: 95)")
    parser.add_argument("--quiet", action="store_true", help="only print the final gate line")
    args = parser.parse_args(argv)

    try:  # keep the human report readable regardless of the console code page
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    report = evaluate()
    Path(args.json).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    rendered = render(report, args.min)
    if args.quiet:
        print(rendered.splitlines()[-2])
    else:
        print(rendered)

    return 0 if report["automatable_pct"] >= args.min else 1


if __name__ == "__main__":
    sys.exit(main())

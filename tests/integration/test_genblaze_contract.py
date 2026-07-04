"""SDK-boundary contract test for the real Genblaze adapter.

This is the test that makes "meaningful Genblaze usage" *defensible*: it drives
``GenblazeMediaProvider`` through a **real** ``genblaze_core.Pipeline`` using the
SDK's own shipped mock provider (``genblaze_core.testing``) — not a Cinemory
fake. Only the terminal network read (fetching hosted asset bytes) is stubbed;
everything else is the genuine SDK:

* ``Pipeline(name).step(provider, model=, prompt=, modality=, **params)``
* ``.run(sink=..., timeout=..., raise_on_failure=True) -> PipelineResult``
* ``PipelineResult.run`` / ``PipelineResult.manifest`` (with ``verify_hash()``)
* ``result.run.steps[-1].assets[0]`` → a URL-addressed ``Asset``
  (``url`` / ``sha256`` / ``media_type``; **no** ``.read()`` / ``.bytes``)
* provider classes import from ``genblaze_gmicloud`` as ``GMICloud*Provider``

If a future ``genblaze`` release changes any of these shapes, this test fails —
which is exactly the guard the "untested against the real SDK" gap needed.

``genblaze-core`` is a pure-Python dependency with no credentials, installed in
CI via ``requirements-dev.txt``, so this test *runs* (it does not skip).
"""
from __future__ import annotations

import hashlib
import inspect

import pytest

from cinemory.adapters.genblaze_provider import GenblazeMediaProvider
from cinemory.models import Modality

genblaze_core = pytest.importorskip(
    "genblaze_core",
    reason="genblaze-core must be installed for the SDK-boundary contract test "
    "(it is in requirements-dev.txt; CI installs it)",
)


def _mock_provider(assets):
    from genblaze_core.testing import MockProvider

    return MockProvider(name="mock-video", assets=assets)


def _gb_asset(url: str, media_type: str, sha256: str):
    from genblaze_core.models.asset import Asset as GbAsset

    return GbAsset(url=url, media_type=media_type, sha256=sha256)


# ---------------------------------------------------------------------------
# 1. The adapter runs a real Genblaze pipeline and returns the asset's bytes.
# ---------------------------------------------------------------------------
def test_adapter_drives_real_pipeline_and_returns_bytes():
    payload = b"CINEMORY-CLIP" + b"\x00\x01\x02" * 512
    sha = hashlib.sha256(payload).hexdigest()
    url = "https://mock.test/generated.mp4"

    seen: dict = {}

    def fake_downloader(u: str) -> bytes:
        seen["url"] = u
        return payload

    adapter = GenblazeMediaProvider(
        provider_obj=_mock_provider([_gb_asset(url, "video/mp4", sha)]),
        downloader=fake_downloader,
    )

    out = adapter.generate(
        model="Kling-Image2Video-V2.1-Master",
        prompt="a quiet memory",
        modality=Modality.VIDEO,
    )

    # Bytes flowed through the real SDK result and back out of our port.
    assert out == payload
    assert seen["url"] == url

    # Genblaze sealed a manifest for the run and we surfaced it (provenance chain).
    assert adapter.last_manifest is not None
    assert adapter.last_manifest.verify_hash() is True


# ---------------------------------------------------------------------------
# 2. Genblaze's per-asset SHA-256 is chained into Cinemory's provenance:
#    a mismatch between the sealed hash and the fetched bytes is rejected.
# ---------------------------------------------------------------------------
def test_provenance_mismatch_is_rejected():
    url = "https://mock.test/tampered.mp4"
    sealed_but_wrong = "a" * 64  # not the hash of what the downloader returns

    adapter = GenblazeMediaProvider(
        provider_obj=_mock_provider([_gb_asset(url, "video/mp4", sealed_but_wrong)]),
        downloader=lambda _u: b"different-bytes-than-were-sealed",
    )

    with pytest.raises(ValueError, match="provenance mismatch"):
        adapter.generate(model="mock", prompt="x", modality=Modality.VIDEO)


# ---------------------------------------------------------------------------
# 3. A generation failure is raised, not silently returned as garbage bytes.
# ---------------------------------------------------------------------------
def test_generation_failure_raises():
    from genblaze_core.testing import MockProvider

    adapter = GenblazeMediaProvider(
        provider_obj=MockProvider(name="mock-video", should_fail=True),
        downloader=lambda _u: b"never-reached",
    )
    with pytest.raises(Exception):  # noqa: B017 - SDK raises PipelineError/ProviderError
        adapter.generate(model="mock", prompt="x", modality=Modality.VIDEO)


# ---------------------------------------------------------------------------
# 4. Static shape guards: the SDK entry points our adapter calls still exist
#    with the parameters we pass. Fails on SDK signature drift.
# ---------------------------------------------------------------------------
def test_sdk_signatures_match_adapter_assumptions():
    from genblaze_core import Modality as GbModality
    from genblaze_core import ObjectStorageSink, Pipeline, PipelineResult

    step_params = inspect.signature(Pipeline.step).parameters
    for p in ("provider", "model", "prompt", "modality"):
        assert p in step_params, f"Pipeline.step lost parameter {p!r}"

    run_params = inspect.signature(Pipeline.run).parameters
    for p in ("sink", "timeout", "raise_on_failure"):
        assert p in run_params, f"Pipeline.run lost parameter {p!r}"

    # PipelineResult carries the run + sealed manifest we navigate.
    result_params = inspect.signature(PipelineResult.__init__).parameters
    assert "run" in result_params and "manifest" in result_params

    # ObjectStorageSink accepts a storage backend positionally.
    sink_params = list(inspect.signature(ObjectStorageSink.__init__).parameters)
    assert sink_params[1] == "backend"

    # Every cinemory Modality maps onto a real Genblaze Modality member.
    for m in (Modality.IMAGE, Modality.VIDEO, Modality.AUDIO):
        assert hasattr(GbModality, m.name)


# ---------------------------------------------------------------------------
# 5. The live GMICloud provider classes exist under the documented import path
#    (guards the provider-resolution mapping). Skips if the optional extra is
#    not installed — it is not part of offline CI's dependency set.
# ---------------------------------------------------------------------------
def test_gmicloud_provider_classes_importable_when_installed():
    gmi = pytest.importorskip(
        "genblaze_gmicloud",
        reason="optional live extra 'genblaze[gmicloud]' not installed",
    )
    for cls in ("GMICloudVideoProvider", "GMICloudImageProvider", "GMICloudAudioProvider"):
        assert hasattr(gmi, cls), f"genblaze_gmicloud missing {cls}"

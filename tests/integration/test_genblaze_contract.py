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


@pytest.fixture(autouse=True)
def _clear_b2_env(monkeypatch):
    for name in (
        "B2_KEY_ID", "B2_APP_KEY", "B2_ENDPOINT_URL", "B2_REGION", "B2_BUCKET_NAME",
        "B2_APPLICATION_KEY_ID", "B2_APPLICATION_KEY", "B2_S3_ENDPOINT",
        "B2_KEY_PREFIX", "B2_PREFIX"
    ):
        monkeypatch.delenv(name, raising=False)



def _mock_provider(assets):
    from genblaze_core.testing import MockProvider

    return MockProvider(name="mock-video", assets=assets)


def _gb_asset(url: str, media_type: str, sha256: str, size_bytes: int | None = None):
    from genblaze_core.models.asset import Asset as GbAsset

    return GbAsset(url=url, media_type=media_type, sha256=sha256, size_bytes=size_bytes)


def _mem_backend():
    """A faithful in-memory implementation of Genblaze's ``StorageBackend`` ABC.

    Exercises the *real* sink → store → readback path offline (no B2 creds), so
    the load-bearing branch of the adapter is genuinely covered — not hidden
    behind ``# pragma: no cover``.
    """
    from genblaze_core.storage.base import StorageBackend

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
            return url[len(self._PREFIX) :] if url.startswith(self._PREFIX) else None

    return MemBackend()


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
# 1b. The load-bearing path: Genblaze's ObjectStorageSink persists the asset and
#     the adapter reads the durable bytes back THROUGH the same backend (no
#     network download). This exercises sink attachment + URL->key roundtrip +
#     backend readback + sha256 chaining, fully offline against the real SDK.
# ---------------------------------------------------------------------------
def test_adapter_reads_back_through_genblaze_sink():
    payload = b"REAL-CLIP-BYTES" + b"\x07\x08" * 400
    sha = hashlib.sha256(payload).hexdigest()

    backend = _mem_backend()
    key = "assets/clip0.mp4"
    backend.put(key, payload)  # asset already lives in the backend
    url = backend.get_durable_url(key)

    # size_bytes + sha256 present => the sink recognises the asset as already
    # transferred and keeps the durable URL (the real B2 steady state).
    provider = _mock_provider([_gb_asset(url, "video/mp4", sha, size_bytes=len(payload))])

    def _forbid_download(_u: str) -> bytes:
        raise AssertionError("must read back through the backend, not download")

    adapter = GenblazeMediaProvider(
        provider_obj=provider,
        backend=backend,  # adapter attaches ObjectStorageSink(backend) internally
        downloader=_forbid_download,
    )

    out = adapter.generate(model="m", prompt="p", modality=Modality.VIDEO)

    assert out == payload  # bytes came back through backend.get(key_from_url(url))
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
    for p in ("provider", "model", "prompt", "modality", "external_inputs"):
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


# ---------------------------------------------------------------------------
# 6. Photo inputs actually reach the SDK. This is the live-path bug the tests
#    above never caught: ``generate(inputs=[...])`` built the step WITHOUT its
#    inputs, so GMI rejected every I2V submit with
#    ``400: invalid payload parameters: image (Required parameter is missing)``.
#    The step the provider receives MUST carry one input Asset per byte-string
#    — hosted through the same storage backend, content-addressed, sha256-sealed.
# ---------------------------------------------------------------------------
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


def _forbid_download(_u: str) -> bytes:
    raise AssertionError("must read back through the backend, not download")


def _adapter_with_stored_clip(clip: bytes):
    """MockProvider + MemBackend wiring where the output clip is already durable
    (the real B2 steady state), so ``generate`` exercises hosting + readback
    with zero network."""
    backend = _mem_backend()
    backend.put("assets/clip.mp4", clip)
    url = backend.get_durable_url("assets/clip.mp4")
    provider = _mock_provider(
        [_gb_asset(url, "video/mp4", hashlib.sha256(clip).hexdigest(), size_bytes=len(clip))]
    )
    adapter = GenblazeMediaProvider(
        provider_obj=provider, backend=backend, downloader=_forbid_download
    )
    return adapter, provider, backend


def test_generate_attaches_photo_input_as_external_asset():
    photo = _PNG_MAGIC + b"real-photo-bytes" * 32
    photo_sha = hashlib.sha256(photo).hexdigest()
    clip = b"CLIP" + b"\x03\x04" * 400
    adapter, provider, backend = _adapter_with_stored_clip(clip)

    out = adapter.generate(
        model="Kling-Image2Video-V2.1-Master",
        prompt="a quiet memory",
        modality=Modality.VIDEO,
        inputs=[photo],
    )

    assert out == clip
    # The Step the SDK handed the provider carries the photo as an input Asset.
    step = provider.received_steps[-1]
    assert len(step.inputs) == 1, "photo input was dropped before reaching the provider"
    asset = step.inputs[0]
    assert asset.sha256 == photo_sha
    assert asset.media_type == "image/png"
    assert asset.size_bytes == len(photo)
    # The bytes are hosted through the SAME backend the sink uses, at a
    # content-addressed key the asset URL resolves back to.
    key = backend.key_from_url(asset.url)
    assert key == f"chain-inputs/{photo_sha}.png"
    assert backend.get(key) == photo


def test_generate_attaches_both_flf2v_frames_in_order():
    first = _JPEG_MAGIC + b"first-frame" * 24
    last = _PNG_MAGIC + b"last-frame" * 24
    clip = b"BRIDGE" + b"\x05\x06" * 300
    adapter, provider, _backend = _adapter_with_stored_clip(clip)

    out = adapter.generate(
        model="seedance-2-0-260128",
        prompt="smooth match-cut transition",
        modality=Modality.VIDEO,
        inputs=[first, last],
        params={"kind": "flf2v", "from": "c0", "to": "c1"},
    )

    assert out == clip
    step = provider.received_steps[-1]
    # Both frames, in order — positional order is what routes first vs last.
    assert [a.sha256 for a in step.inputs] == [
        hashlib.sha256(first).hexdigest(),
        hashlib.sha256(last).hexdigest(),
    ]
    assert [a.media_type for a in step.inputs] == ["image/jpeg", "image/png"]


def test_pipeline_step_receives_external_inputs_kwarg(monkeypatch):
    """Pin the exact regression: the step must be built WITH ``external_inputs=``
    (a step built without it compiles and runs — and silently drops the photos)."""
    from genblaze_core import Pipeline

    seen: dict = {}
    real_step = Pipeline.step

    def spying_step(self, provider, **kwargs):
        seen.update(kwargs)
        return real_step(self, provider, **kwargs)

    monkeypatch.setattr(Pipeline, "step", spying_step)

    photo = _PNG_MAGIC + b"spy-photo" * 16
    clip = b"SPYCLIP" + b"\x07" * 200
    adapter, _provider, _backend = _adapter_with_stored_clip(clip)
    adapter.generate(model="m", prompt="p", modality=Modality.VIDEO, inputs=[photo])

    external = seen.get("external_inputs")
    assert external, "Pipeline.step was not given external_inputs="
    assert len(external) == 1
    assert external[0].sha256 == hashlib.sha256(photo).hexdigest()


def test_generate_without_inputs_passes_no_external_assets():
    """Text-only steps stay input-free (no phantom assets, no hosted inputs)."""
    clip = b"T2V" + b"\x08" * 200
    adapter, provider, backend = _adapter_with_stored_clip(clip)

    adapter.generate(model="Kling-Text2Video-V2.1-Master", prompt="p",
                     modality=Modality.VIDEO)

    assert provider.received_steps[-1].inputs == []
    # The sink may write its own run manifest, but nothing was hosted as input.
    assert not [k for k in backend.store if k.startswith("chain-inputs/")]


def test_inputs_without_backend_are_rejected_loudly():
    """No storage backend means the provider could never fetch the photo —
    fail fast with an actionable message instead of an opaque upstream 400."""
    adapter = GenblazeMediaProvider(
        provider_obj=_mock_provider(
            [_gb_asset("https://mock.test/clip.mp4", "video/mp4", "0" * 64)]
        ),
        downloader=lambda _u: b"never-reached",
    )
    with pytest.raises(ValueError, match="storage backend"):
        adapter.generate(model="m", prompt="p", modality=Modality.VIDEO,
                         inputs=[_PNG_MAGIC + b"photo"])


# ---------------------------------------------------------------------------
# 7. FLF2V slot routing. gmicloud 0.3.3 ships no seedance family: the slug
#    resolves to the permissive fallback whose ``route_images(slots=("image",))``
#    (a) emits the wrong native slot name for seedance and (b) drops every image
#    after the first. The registered user spec must route both frames into GMI's
#    documented ``first_frame``/``last_frame`` slots — driven here through the
#    real ``ModelRegistry.prepare_payload`` pipeline (genblaze-core only).
# ---------------------------------------------------------------------------
def test_seedance_flf2v_spec_routes_both_frames_to_native_slots():
    from genblaze_core import Modality as GbModality
    from genblaze_core.models.step import Step
    from genblaze_core.providers.model_registry import ModelRegistry

    from cinemory.adapters.genblaze_provider import SEEDANCE_FLF2V_MODEL, seedance_flf2v_spec

    registry = ModelRegistry()
    registry.register(seedance_flf2v_spec())

    step = Step(
        provider="gmicloud",
        model=SEEDANCE_FLF2V_MODEL,
        modality=GbModality.VIDEO,
        prompt="smooth match-cut transition",
        params={"kind": "flf2v", "from": "c0", "to": "c1"},
        inputs=[
            _gb_asset("https://cdn.test/first.png", "image/png", "a" * 64, size_bytes=10),
            _gb_asset("https://cdn.test/last.png", "image/png", "b" * 64, size_bytes=10),
        ],
    )
    payload = registry.prepare_payload(step)

    assert payload["first_frame"] == "https://cdn.test/first.png"
    assert payload["last_frame"] == "https://cdn.test/last.png"
    assert payload["prompt"] == "smooth match-cut transition"
    # Cinemory-internal bookkeeping params are dropped by the allowlist (the
    # SDK's standard drop-with-warning), never sent to GMI.
    for junk in ("kind", "from", "to"):
        assert junk not in payload


def test_flf2v_registry_overrides_gmicloud_fallback_when_installed():
    """With the live extra installed, the per-instance registry must resolve the
    seedance slug to the FLF2V spec (not the single-slot fallback) while the
    Kling I2V family keeps its native single ``image`` slot."""
    pytest.importorskip(
        "genblaze_gmicloud",
        reason="optional live extra 'genblaze[gmicloud]' not installed",
    )
    from genblaze_gmicloud import GMICloudVideoProvider

    from cinemory.adapters.genblaze_provider import (
        SEEDANCE_FLF2V_MODEL,
        _flf2v_video_registry,
    )

    registry = _flf2v_video_registry(GMICloudVideoProvider)
    frames = [
        _gb_asset("https://cdn.test/a.png", "image/png", "a" * 64, size_bytes=1),
        _gb_asset("https://cdn.test/b.png", "image/png", "b" * 64, size_bytes=1),
    ]

    seedance = registry.get(SEEDANCE_FLF2V_MODEL)
    assert seedance.input_mapping(frames) == {
        "first_frame": "https://cdn.test/a.png",
        "last_frame": "https://cdn.test/b.png",
    }

    kling = registry.get("Kling-Image2Video-V2.1-Master")
    assert kling.input_mapping(frames[:1]) == {"image": "https://cdn.test/a.png"}

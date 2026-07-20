"""Real Genblaze-backed generative-media provider.

Wraps a Genblaze single-step ``Pipeline`` behind the :class:`MediaProvider` port.
Genblaze is imported lazily so the offline package and CI depend on neither it
nor any provider API key.

Shape verified against the pinned SDK
-------------------------------------
The navigation and call shape below are confirmed against the real published
release (``genblaze-core`` 0.3.6, ``genblaze-s3`` 0.3.5, ``genblaze-gmicloud``
0.3.3 — the versions the ``genblaze`` 0.4.3 metapackage resolves):

* ``Pipeline(name).step(provider, model=, prompt=, modality=,
  external_inputs=, **params).run(sink=, timeout=, raise_on_failure=)
  -> PipelineResult``
* ``external_inputs`` is the SDK's only mechanism for caller-held input media:
  it seeds ``Step.inputs`` with ``Asset`` objects whose **HTTPS URLs** the
  provider's ``input_mapping`` routes into native payload slots (GMICloud
  Kling I2V: ``image``). Raw bytes and ``data:`` URIs are rejected by the
  SDK's SSRF gate, so photo bytes are first persisted through the storage
  backend and passed as short-lived presigned URLs (see
  :meth:`GenblazeMediaProvider._external_inputs`).
* ``PipelineResult`` exposes ``.run`` (a ``Run``) and ``.manifest`` (a sealed
  ``Manifest`` with ``verify_hash()``).
* ``result.run.steps[-1].assets[0]`` is an ``Asset`` — **URL-addressed**
  (``url``, ``sha256``, ``size_bytes``, ``media_type``); it carries no inline
  bytes. Bytes are obtained from durable storage or the hosted URL.
* GMICloud provider classes import from ``genblaze_gmicloud`` as
  ``GMICloud{Video,Image,Audio}Provider``.

``tests/integration/test_genblaze_contract.py`` drives this adapter through a
*real* ``Pipeline`` using the SDK's own ``genblaze_core.testing`` mock provider,
so any future SDK drift in these shapes fails CI.

How Genblaze is used (meaningfully, not as a dumb byte source)
--------------------------------------------------------------
On the live path this adapter attaches Genblaze's own ``ObjectStorageSink`` over
a Backblaze B2 backend, so **Genblaze** performs generation *and* content-
addressed B2 persistence *and* seals a SHA-256 provenance manifest for every
generated asset. Cinemory then reads the durable bytes back through the same
backend to stitch the final reel, and **chains Genblaze's per-asset SHA-256 into
its own reel-level provenance** (:mod:`cinemory.provenance`). Genblaze owns
per-asset gen+provenance+storage; Cinemory owns the composed-reel provenance.

Env:
  GENBLAZE_PROVIDER   one of: gmicloud (others: not wired yet)
  GMI_API_KEY         GMICloud credential
  B2_BUCKET_NAME      B2 bucket for Genblaze's asset persistence (+ B2 creds; see
                      genblaze_s3.S3StorageBackend.for_backblaze / env)
"""
from __future__ import annotations

import hashlib
import os
import urllib.request
from collections.abc import Callable
from typing import Any

from ..models import Modality

# Matches genblaze AssetTransfer's default download cap (5 GiB).
_MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024 * 1024

#: The FLF2V chapter-bridge model (see ``ReelPipeline.bridge_model``).
#: gmicloud 0.3.3 ships no seedance model family, so this slug resolves to the
#: registry's permissive fallback whose ``route_images(slots=("image",))``
#: mapping (a) emits the wrong native slot name for seedance and (b) drops
#: every image after the first — both bridge frames must instead reach GMI as
#: ``first_frame`` / ``last_frame`` (docs.gmicloud.ai, seedance-2-0-260128).
SEEDANCE_FLF2V_MODEL = "seedance-2-0-260128"
_SEEDANCE_FRAME_SLOTS = ("first_frame", "last_frame")

#: Positive magic-byte sniffs for the photo formats the ingest path accepts.
#: The provider-side image router only routes ``image/*`` assets, and every
#: byte-string reaching :meth:`GenblazeMediaProvider.generate` is a photo by
#: pipeline contract (ingest rejects executables/markup), so unrecognised
#: bytes default to the pipeline's canonical photo type rather than an
#: ``application/octet-stream`` that would silently un-route the frame.
_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
)
_MEDIA_TYPE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _image_media_type(data: bytes) -> str:
    """Best-effort MIME sniff for an input photo (default ``image/png``)."""
    for magic, media_type in _IMAGE_MAGIC:
        if data.startswith(magic):
            return media_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def seedance_flf2v_spec() -> Any:
    """A genblaze ``ModelSpec`` wiring seedance's first/last-frame slots.

    Mirrors the SDK's own named-family idiom (``ParamSurface.for_modality`` +
    ``route_images`` + the GMI ``payload`` envelope) so junk params are dropped
    with the SDK's standard warning instead of reaching GMI, and both FLF2V
    frames are routed positionally into the documented native slots.
    """
    from genblaze_core import Modality as GbModality  # type: ignore
    from genblaze_core.providers import (  # type: ignore
        ModelSpec,
        ParamSurface,
        route_images,
    )

    surface = ParamSurface.for_modality(GbModality.VIDEO).extend(*_SEEDANCE_FRAME_SLOTS)
    return ModelSpec(
        model_id=SEEDANCE_FLF2V_MODEL,
        modality=GbModality.VIDEO,
        input_mapping=route_images(slots=_SEEDANCE_FRAME_SLOTS),
        extras={"envelope_key": "payload"},
        **surface.build(),
    )


def _flf2v_video_registry(provider_cls: Any) -> Any:
    """The video provider's default registry + the seedance FLF2V user spec."""
    registry = provider_cls.create_registry()
    registry.register(seedance_flf2v_spec())
    return registry


def _https_download(url: str, *, timeout: float = 120.0) -> bytes:  # pragma: no cover - network
    """Fetch an asset's hosted bytes. HTTPS-only (credentials never in URLs)."""
    if not url.lower().startswith("https://"):
        raise ValueError(f"refusing to download non-HTTPS asset URL: {url!r}")
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - scheme checked
        data = resp.read(_MAX_DOWNLOAD_BYTES + 1)
    if len(data) > _MAX_DOWNLOAD_BYTES:
        raise ValueError(f"asset exceeds {_MAX_DOWNLOAD_BYTES}-byte download cap: {url!r}")
    return data


class GenblazeMediaProvider:
    name = "genblaze"

    def __init__(
        self,
        provider: str | None = None,
        *,
        provider_obj: Any | None = None,
        backend: Any | None = None,
        bucket: str | None = None,
        downloader: Callable[[str], bytes] | None = None,
    ) -> None:
        """
        Args:
            provider: Genblaze provider family (default ``gmicloud``).
            provider_obj: an already-constructed Genblaze provider instance. When
                supplied, credential-bound resolution is bypassed — used by the
                SDK-boundary contract test to inject a mock provider.
            backend: an already-constructed Genblaze ``StorageBackend``. When
                supplied, bypasses live B2 backend construction.
            bucket: B2 bucket name (falls back to ``B2_BUCKET_NAME``).
            downloader: byte-fetch seam for the hosted-URL path (injectable for
                tests); defaults to a HTTPS-only GET.
        """
        self.provider_name = provider or os.environ.get("GENBLAZE_PROVIDER", "gmicloud")
        self._provider_obj = provider_obj
        self._backend = backend
        self._bucket = bucket or os.environ.get("B2_BUCKET_NAME")
        self._download = downloader or _https_download
        #: The sealed Genblaze manifest from the most recent ``generate`` call.
        self.last_manifest: Any | None = None

    # -- provider / storage wiring (credential-bound; resolved lazily) ---------

    def _resolve_provider(self, modality: Modality) -> Any:
        if self._provider_obj is not None:
            return self._provider_obj
        return self._real_provider(modality)

    def _real_provider(self, modality: Modality) -> Any:  # pragma: no cover - GMICloud SDK + key
        if self.provider_name == "gmicloud":
            from genblaze_gmicloud import (  # type: ignore
                GMICloudAudioProvider,
                GMICloudImageProvider,
                GMICloudVideoProvider,
            )

            if modality is Modality.VIDEO:
                # Per-instance registry override (the SDK's documented
                # extension point) so the FLF2V bridge model routes both
                # frames — see ``seedance_flf2v_spec``.
                return GMICloudVideoProvider(models=_flf2v_video_registry(GMICloudVideoProvider))
            return {
                Modality.IMAGE: GMICloudImageProvider,
                Modality.AUDIO: GMICloudAudioProvider,
            }[modality]()
        raise NotImplementedError(f"provider {self.provider_name!r} not wired yet")

    def _resolve_backend(self) -> Any | None:
        if self._backend is not None:
            return self._backend
        return self._real_backend()

    def _real_backend(self) -> Any | None:  # pragma: no cover - needs B2 creds
        if not self._bucket:
            return None
        from genblaze_s3 import S3StorageBackend  # type: ignore

        from ..config import resolve_b2_config

        cfg = resolve_b2_config()
        prefix = cfg.key_prefix or ""
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        class PrefixedS3StorageBackend(S3StorageBackend):
            def put(self, key, data, *args, **kwargs):
                return super().put(f"{prefix}{key}", data, *args, **kwargs)

            def get(self, key, *args, **kwargs):
                return super().get(f"{prefix}{key}", *args, **kwargs)

            def exists(self, key, *args, **kwargs):
                return super().exists(f"{prefix}{key}", *args, **kwargs)

            def delete(self, key, *args, **kwargs):
                return super().delete(f"{prefix}{key}", *args, **kwargs)

            def get_url(self, key, *args, **kwargs):
                return super().get_url(f"{prefix}{key}", *args, **kwargs)

            def get_durable_url(self, key, *args, **kwargs):
                return super().get_durable_url(f"{prefix}{key}", *args, **kwargs)

            def key_from_url(self, url, *args, **kwargs):
                key = super().key_from_url(url, *args, **kwargs)
                if key and prefix and key.startswith(prefix):
                    return key[len(prefix):]
                return key

        return PrefixedS3StorageBackend.for_backblaze(
            self._bucket,
            region=cfg.region,
            key_id=cfg.key_id,
            app_key=cfg.app_key,
        )

    # -- generation -----------------------------------------------------------

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        modality: Modality,
        inputs: list[bytes] | None = None,
        params: dict | None = None,
    ) -> bytes:
        from genblaze_core import Modality as GbModality  # type: ignore
        from genblaze_core import ObjectStorageSink, Pipeline

        provider = self._resolve_provider(modality)
        gb_modality = getattr(GbModality, modality.name)
        backend = self._resolve_backend()
        pipeline = Pipeline("cinemory-step").step(
            provider,
            model=model,
            prompt=prompt,
            modality=gb_modality,
            external_inputs=self._external_inputs(inputs, backend),
            **(params or {}),
        )
        sink = ObjectStorageSink(backend) if backend is not None else None
        result = pipeline.run(sink=sink, timeout=600, raise_on_failure=True)

        # Genblaze sealed a provenance manifest for this run — surface it so the
        # caller can chain it into Cinemory's reel-level provenance.
        self.last_manifest = result.manifest

        asset = result.run.steps[-1].assets[0]
        data = self._read_asset_bytes(asset, backend)
        self._verify_provenance(asset, data)
        return data

    #: Content-addressed namespace for hosted step inputs (photo frames),
    #: separate from the sink's generated-asset layout.
    _INPUT_KEY_PREFIX = "chain-inputs"
    #: Presigned-URL lifetime for the provider's server-side input fetch.
    _INPUT_URL_EXPIRES_SECS = 3600

    def _external_inputs(
        self, inputs: list[bytes] | None, backend: Any | None
    ) -> list[Any] | None:
        """Turn caller-held photo bytes into Genblaze ``external_inputs`` Assets.

        ``Pipeline.step(external_inputs=...)`` seeds ``Step.inputs``; the
        provider's ``input_mapping`` then routes each Asset **URL** into its
        native payload slot (GMICloud Kling I2V: ``image``; seedance FLF2V:
        ``first_frame``/``last_frame``). The SDK's SSRF gate accepts only
        HTTPS URLs — never raw bytes or ``data:`` URIs — so each input is
        persisted through the same storage backend under a content-addressed
        key and handed over as a short-lived presigned URL. ``sha256`` is
        sealed on every Asset so step cache keys and the Genblaze manifest
        hash stay stable across reruns (presigned URLs rotate).
        """
        if not inputs:
            return None
        if backend is None:
            raise ValueError(
                "photo inputs require the Genblaze storage backend so the "
                "provider can fetch them: configure B2 (B2_BUCKET_NAME + "
                "credentials) or inject backend=."
            )
        from genblaze_core.models.asset import Asset as GbAsset  # type: ignore

        assets: list[Any] = []
        for data in inputs:
            digest = hashlib.sha256(data).hexdigest()
            media_type = _image_media_type(data)
            key = f"{self._INPUT_KEY_PREFIX}/{digest}{_MEDIA_TYPE_EXT[media_type]}"
            if not backend.exists(key):
                backend.put(key, data, content_type=media_type)
            url = backend.get_url(key, expires_in=self._INPUT_URL_EXPIRES_SECS)
            assets.append(
                GbAsset(url=url, media_type=media_type, sha256=digest, size_bytes=len(data))
            )
        return assets

    def _read_asset_bytes(self, asset: Any, backend: Any | None) -> bytes:
        """Return the generated asset's bytes.

        When Genblaze persisted to our B2 backend, read the durable object back
        through the *same* backend (no second, unauthenticated network fetch);
        otherwise pull the provider's hosted asset URL via the download seam.
        """
        if backend is not None:
            key = backend.key_from_url(asset.url)
            if key is not None:
                return backend.get(key)
        return self._download(asset.url)

    @staticmethod
    def _verify_provenance(asset: Any, data: bytes) -> None:
        """Chain Genblaze's provenance into Cinemory's.

        If Genblaze sealed a real SHA-256 for this asset, the bytes we return
        MUST match it — otherwise the asset was tampered with in transit.
        (The all-zero placeholder some providers emit pre-sink is ignored.)
        """
        sha = asset.sha256
        if sha and set(sha) != {"0"}:
            got = hashlib.sha256(data).hexdigest()
            if got != sha:
                raise ValueError(
                    f"Genblaze provenance mismatch: sealed sha256={sha}, downloaded={got}"
                )

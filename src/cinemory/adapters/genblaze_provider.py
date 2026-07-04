"""Real Genblaze-backed generative-media provider.

Wraps a Genblaze single-step ``Pipeline`` behind the :class:`MediaProvider` port.
Genblaze is imported lazily so the offline package and CI depend on neither it
nor any provider API key.

Shape verified against the pinned SDK
-------------------------------------
The navigation and call shape below are confirmed against the real published
release (``genblaze-core`` 0.3.4, ``genblaze-s3`` 0.3.4, ``genblaze-gmicloud``
0.3.2 — the versions the ``genblaze`` 0.4.1 metapackage resolves):

* ``Pipeline(name).step(provider, model=, prompt=, modality=, **params).run(
  sink=, timeout=, raise_on_failure=) -> PipelineResult``
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

            return {
                Modality.VIDEO: GMICloudVideoProvider,
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

        # Resolve creds + region from either the legacy or the canonical B2 env
        # names, and pass them explicitly (region derived from the endpoint host
        # when B2_REGION is unset) so a user's canonical vars reach Genblaze's own
        # S3 backend with no .env edit.
        cfg = resolve_b2_config()
        return S3StorageBackend.for_backblaze(
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
        pipeline = Pipeline("cinemory-step").step(
            provider, model=model, prompt=prompt, modality=gb_modality, **(params or {})
        )
        backend = self._resolve_backend()
        sink = ObjectStorageSink(backend) if backend is not None else None
        result = pipeline.run(sink=sink, timeout=600, raise_on_failure=True)

        # Genblaze sealed a provenance manifest for this run — surface it so the
        # caller can chain it into Cinemory's reel-level provenance.
        self.last_manifest = result.manifest

        asset = result.run.steps[-1].assets[0]
        data = self._read_asset_bytes(asset, backend)
        self._verify_provenance(asset, data)
        return data

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

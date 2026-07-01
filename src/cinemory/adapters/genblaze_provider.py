"""Real Genblaze-backed generative-media provider.

Wraps a Genblaze single-step Pipeline behind the ``MediaProvider`` port. Genblaze
is imported lazily so the package and offline CI do not depend on it or on any
provider API key.

IMPORTANT (wiring note for maintainers): the exact Genblaze import paths, provider
class names and ``run`` return shape should be confirmed against the pinned
Genblaze release (https://github.com/backblaze-labs/genblaze) when credentials are
added. This adapter is the ONLY place that needs to change — the pipeline,
provenance and tests are decoupled from it via the port. The mapping below
follows the documented API: ``Pipeline().step(provider, model=, prompt=,
modality=).run(sink=...)``.

Env:
  GENBLAZE_PROVIDER   one of: gmicloud | openai | google | runway | luma
  GMI_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY   provider credential
"""
from __future__ import annotations

import os

from ..models import Modality


class GenblazeMediaProvider:
    name = "genblaze"

    def __init__(self, provider: str | None = None) -> None:
        self.provider_name = provider or os.environ.get("GENBLAZE_PROVIDER", "gmicloud")
        self._provider_obj = None  # resolved lazily on first call

    def _resolve_provider(self, modality: Modality):  # pragma: no cover - real-path only
        # Import inside the method: absent in offline CI, present once wired.
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

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        modality: Modality,
        inputs: list[bytes] | None = None,
        params: dict | None = None,
    ) -> bytes:  # pragma: no cover - real-path only
        from genblaze_core import Modality as GbModality  # type: ignore
        from genblaze_core import Pipeline

        gb_modality = getattr(GbModality, modality.name)
        provider = self._resolve_provider(modality)
        pipeline = Pipeline("cinemory-step").step(
            provider, model=model, prompt=prompt, modality=gb_modality, **(params or {})
        )
        result = pipeline.run(timeout=600)
        # The generated asset bytes are read back from the step's asset.
        asset = result.run.steps[-1].assets[0]
        return asset.read() if hasattr(asset, "read") else asset.bytes

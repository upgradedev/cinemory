"""Opt-in, consent-gated live connectors.

These modules integrate external accounts (Google Photos import; YouTube upload;
LinkedIn share). They are **live-only** features, explicitly separate from the
offline reference pipeline:

- They are NEVER wired into ``cinemory.config`` and NEVER run in CI or the demo.
- They require the user's own OAuth tokens / credentials, supplied at call time
  (no defaults, no ambient network).
- Every network call goes through the injectable :class:`~cinemory.connectors._http.Transport`
  seam, so their multi-step flows are unit-tested offline with a fake transport
  and the package imports with no third-party HTTP dependency.

Install the live dependency with the ``connectors`` extra:
``pip install 'cinemory[connectors]'``.
"""
from __future__ import annotations

from ._http import HttpError, HttpResponse, RequestsTransport, Transport
from .google_photos import GoogleOAuth, GooglePhotosPicker
from .linkedin import LinkedInShare
from .youtube import YouTubeUploader

__all__ = [
    "Transport",
    "RequestsTransport",
    "HttpResponse",
    "HttpError",
    "GoogleOAuth",
    "GooglePhotosPicker",
    "YouTubeUploader",
    "LinkedInShare",
]

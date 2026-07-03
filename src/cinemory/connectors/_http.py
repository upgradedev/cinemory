"""A tiny HTTP transport seam shared by the opt-in connectors.

The connectors (Google Photos Picker, YouTube, LinkedIn) are OPT-IN, live-only
features. To keep them fully testable **offline** — and to guarantee the
package imports with zero third-party HTTP deps in CI — every connector talks to
this narrow :class:`Transport` protocol instead of calling ``requests``
directly.

- :class:`RequestsTransport` is the live implementation; ``requests`` is
  imported **lazily** inside it (never at module scope), mirroring the B2 and
  Genblaze adapters. It is installed via the ``connectors`` extra.
- Tests inject a scripted fake transport, so the multi-step connector flows are
  exercised for real with no network, no credentials and no third-party import.
"""
from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> Any:
        return _json.loads(self.body.decode("utf-8")) if self.body else {}


class HttpError(RuntimeError):
    """Raised for a non-2xx response (carries the response for inspection)."""

    def __init__(self, response: HttpResponse, message: str = "") -> None:
        self.response = response
        super().__init__(message or f"HTTP {response.status}: {response.body[:300]!r}")


@runtime_checkable
class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: bytes | dict | None = None,
        json: Any | None = None,
    ) -> HttpResponse:
        ...


class RequestsTransport:
    """Live transport backed by ``requests`` (imported lazily)."""

    def __init__(self, timeout: float = 120.0) -> None:
        try:
            import requests  # noqa: F401
        except ImportError as exc:  # pragma: no cover - real-path only
            raise RuntimeError(
                "requests is required for live connectors: "
                "pip install 'cinemory[connectors]'"
            ) from exc
        self.timeout = timeout

    def request(  # pragma: no cover - real-path only
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: bytes | dict | None = None,
        json: Any | None = None,
    ) -> HttpResponse:
        import requests

        resp = requests.request(
            method, url, headers=headers, params=params, data=data,
            json=json, timeout=self.timeout,
        )
        return HttpResponse(status=resp.status_code, headers=dict(resp.headers),
                            body=resp.content)


def bearer(token: str) -> dict[str, str]:
    """Authorization header for an OAuth 2.0 bearer token."""
    return {"Authorization": f"Bearer {token}"}


def raise_for_status(resp: HttpResponse) -> HttpResponse:
    if not resp.ok:
        raise HttpError(resp)
    return resp

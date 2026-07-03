"""Google Photos **Picker API** connector — opt-in, consented photo import.

Why the Picker API (not the Library API): Google removed the broad
library-read scopes for most apps, so "auto-curate the user's whole library" is
no longer possible. The Picker API is the sanctioned replacement — the user
hand-picks photos inside Google's own UI and the app only ever sees *those*
items. Cinemory implements exactly that flow:

    1. OAuth consent        — user grants the photospicker read-only scope
    2. Create a session     — POST /v1/sessions  -> pickerUri + sessionId
    3. User picks in Google — open pickerUri; user selects photos in Google's UI
    4. Poll the session     — GET /v1/sessions/{id} until mediaItemsSet == true
    5. List + download      — GET /v1/mediaItems?sessionId=… then GET baseUrl=d

⚠️ LEAD-TIME / GO-LIVE (user step): the OAuth **consent screen must be
published and the app verified by Google** for the photospicker scope (a
sensitive scope). Until then only test users you add in the Google Cloud
console can consent. Endpoint paths / scope strings below follow the current
Picker API docs — re-confirm them against the live docs when wiring credentials.

This connector is never imported by the offline pipeline and never runs in CI;
it is a live, consent-gated feature. All I/O goes through the injectable
transport, so its flow logic is unit-tested with a fake transport (no network,
no credentials, no real photos).
"""
from __future__ import annotations

import time
from urllib.parse import urlencode

from ._http import HttpError, HttpResponse, Transport, bearer, raise_for_status

# ── Endpoints & scope (verify against current docs before go-live) ───────────
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
PICKER_BASE = "https://photospicker.googleapis.com/v1"
PICKER_SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"


class GoogleOAuth:
    """Authorization-code OAuth 2.0 helper for the Picker scope."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        *,
        transport: Transport | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self._transport = transport

    def authorization_url(
        self, *, scope: str = PICKER_SCOPE, state: str | None = None,
        access_type: str = "offline", prompt: str = "consent",
    ) -> str:
        """Build the consent URL to send the user to. Pure (no I/O)."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": scope,
            "access_type": access_type,
            "prompt": prompt,
        }
        if state:
            params["state"] = state
        return f"{AUTH_URI}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict:
        """Exchange an authorization code for an access/refresh token."""
        resp = self._require_transport().request(
            "POST", TOKEN_URI,
            data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        return raise_for_status(resp).json()

    def _require_transport(self) -> Transport:
        if self._transport is None:  # pragma: no cover - real-path only
            from ._http import RequestsTransport

            self._transport = RequestsTransport()
        return self._transport


class GooglePhotosPicker:
    """Drive a Google Photos Picker session and download the picked bytes."""

    def __init__(self, access_token: str, *, transport: Transport | None = None) -> None:
        self.access_token = access_token
        self._transport = transport

    # ── session lifecycle ────────────────────────────────────────────────────
    def create_session(self) -> dict:
        """Create a Picker session; returns the session incl. ``pickerUri``."""
        resp = self._t().request("POST", f"{PICKER_BASE}/sessions",
                                 headers=self._auth(), json={})
        return raise_for_status(resp).json()

    def get_session(self, session_id: str) -> dict:
        resp = self._t().request("GET", f"{PICKER_BASE}/sessions/{session_id}",
                                 headers=self._auth())
        return raise_for_status(resp).json()

    def wait_for_selection(
        self, session_id: str, *, max_attempts: int = 60,
        interval: float = 2.0, sleeper=time.sleep,
    ) -> dict:
        """Poll until the user has finished picking (``mediaItemsSet`` true).

        ``sleeper`` is injectable so tests run with no real delay.
        """
        for _ in range(max_attempts):
            session = self.get_session(session_id)
            if session.get("mediaItemsSet"):
                return session
            interval = float(session.get("pollingConfig", {})
                             .get("pollInterval_seconds", interval) or interval)
            sleeper(interval)
        raise HttpError(HttpResponse(408), "picker selection timed out")

    # ── media items ──────────────────────────────────────────────────────────
    def list_media_items(self, session_id: str) -> list[dict]:
        """List the items the user picked in this session (handles paging)."""
        items: list[dict] = []
        page_token: str | None = None
        while True:
            params: dict[str, str] = {"sessionId": session_id, "pageSize": "100"}
            if page_token:
                params["pageToken"] = page_token
            resp = self._t().request("GET", f"{PICKER_BASE}/mediaItems",
                                     headers=self._auth(), params=params)
            payload = raise_for_status(resp).json()
            items.extend(payload.get("mediaItems", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                return items

    def download_media_item(self, media_item: dict) -> bytes:
        """Download the full-resolution bytes of a picked item.

        The Picker returns a short-lived ``baseUrl``; appending ``=d`` requests
        the original/download rendition (per Google's baseUrl parameters).
        """
        base_url = (media_item.get("mediaFile") or {}).get("baseUrl") \
            or media_item.get("baseUrl")
        if not base_url:
            raise ValueError("media item has no baseUrl")
        resp = self._t().request("GET", f"{base_url}=d", headers=self._auth())
        return raise_for_status(resp).body

    # ── helpers ──────────────────────────────────────────────────────────────
    def _auth(self) -> dict[str, str]:
        return bearer(self.access_token)

    def _t(self) -> Transport:
        if self._transport is None:  # pragma: no cover - real-path only
            from ._http import RequestsTransport

            self._transport = RequestsTransport()
        return self._transport

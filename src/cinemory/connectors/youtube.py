"""YouTube upload connector — opt-in, OAuth-gated ``videos.insert``.

Publishes a finished reel to the authenticated user's YouTube channel using the
Data API v3 **resumable** upload:

    1. POST .../upload/youtube/v3/videos?uploadType=resumable&part=snippet,status
       with the video metadata as JSON  ->  201 + a ``Location`` upload URL
    2. PUT the raw video bytes to that Location  ->  the created video resource

⚠️ ACCOUNT-TYPE / AUDIT CAVEATS (document for go-live):
- Scope ``https://www.googleapis.com/auth/youtube.upload``.
- **Until the OAuth app passes Google's verification/audit, uploads from an
  unverified app are forced to ``privacyStatus=private`` and the project is
  subject to a daily upload cap.** Public/unlisted at scale requires the audit.
- The channel must have no upload restrictions and, for some features, be a
  verified channel.

Never used in CI/demo. All HTTP goes through the injectable transport, so the
two-step resumable flow is tested offline with a fake transport.
"""
from __future__ import annotations

from ._http import Transport, bearer, raise_for_status

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


class YouTubeUploader:
    def __init__(self, access_token: str, *, transport: Transport | None = None) -> None:
        self.access_token = access_token
        self._transport = transport

    def upload(
        self,
        video_bytes: bytes,
        *,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        category_id: str = "22",
        privacy_status: str = "private",
        content_type: str = "video/mp4",
    ) -> dict:
        """Upload a reel; returns ``{"id", "url", "privacy_status"}``."""
        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
                "categoryId": category_id,
            },
            "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False},
        }
        # Step 1 — initiate the resumable session.
        init = self._t().request(
            "POST", UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                **bearer(self.access_token),
                "X-Upload-Content-Type": content_type,
                "X-Upload-Content-Length": str(len(video_bytes)),
            },
            json=metadata,
        )
        raise_for_status(init)
        location = init.headers.get("Location") or init.headers.get("location")
        if not location:
            raise ValueError("resumable init returned no upload Location")

        # Step 2 — upload the bytes to the session URL.
        put = self._t().request(
            "PUT", location,
            headers={**bearer(self.access_token), "Content-Type": content_type},
            data=video_bytes,
        )
        resource = raise_for_status(put).json()
        video_id = resource.get("id", "")
        return {
            "id": video_id,
            "url": f"https://youtu.be/{video_id}" if video_id else "",
            "privacy_status": (resource.get("status") or {}).get(
                "privacyStatus", privacy_status),
        }

    def _t(self) -> Transport:
        if self._transport is None:  # pragma: no cover - real-path only
            from ._http import RequestsTransport

            self._transport = RequestsTransport()
        return self._transport

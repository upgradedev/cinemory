"""LinkedIn share connector — opt-in, OAuth-gated.

Two share paths, both through the versioned LinkedIn REST API:

- :meth:`share_link` — post commentary + the reel's public URL (one call to
  ``POST /rest/posts``). The simplest, most broadly available share.
- :meth:`share_video` — upload the reel as native video, then post it:
    1. POST /rest/videos?action=initializeUpload   -> uploadUrl(s) + video URN
    2. PUT the bytes to each uploadUrl              -> upload part(s)
    3. POST /rest/videos?action=finalizeUpload      -> finalize
    4. POST /rest/posts with the video URN          -> the published post

⚠️ ACCOUNT-TYPE / AUDIT CAVEATS (document for go-live):
- Requires an approved LinkedIn app **product**: "Share on LinkedIn"
  (w_member_social) for member posts, or the **Community Management API** for
  organization posts — both need LinkedIn review/approval.
- ``author`` is a URN: ``urn:li:person:{id}`` (member) or
  ``urn:li:organization:{id}`` (company page; requires an admin role).
- The REST API is date-versioned — send the ``LinkedIn-Version`` header
  (e.g. ``202401``). Re-confirm the endpoints/version against current docs
  before wiring credentials.

Never used in CI/demo. All HTTP goes through the injectable transport, so the
multi-step flows are tested offline with a fake transport.
"""
from __future__ import annotations

from ._http import Transport, bearer, raise_for_status

POSTS_URL = "https://api.linkedin.com/rest/posts"
VIDEOS_URL = "https://api.linkedin.com/rest/videos"
MEMBER_SCOPE = "w_member_social"
DEFAULT_VERSION = "202401"


class LinkedInShare:
    def __init__(
        self,
        access_token: str,
        author_urn: str,
        *,
        version: str = DEFAULT_VERSION,
        transport: Transport | None = None,
    ) -> None:
        self.access_token = access_token
        self.author_urn = author_urn
        self.version = version
        self._transport = transport

    # ── simple link share ────────────────────────────────────────────────────
    def share_link(self, commentary: str, url: str, *, visibility: str = "PUBLIC") -> dict:
        """Publish a text post that links to the reel's public URL."""
        body = {
            "author": self.author_urn,
            "commentary": commentary,
            "visibility": visibility,
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "content": {"article": {"source": url, "title": "Cinemory reel"}},
            "lifecycleState": "PUBLISHED",
        }
        resp = self._t().request("POST", POSTS_URL, headers=self._headers(), json=body)
        raise_for_status(resp)
        return {"post_id": resp.headers.get("x-restli-id") or resp.headers.get("X-RestLi-Id", "")}

    # ── native video share ───────────────────────────────────────────────────
    def share_video(
        self, video_bytes: bytes, commentary: str, *, visibility: str = "PUBLIC",
        content_type: str = "video/mp4",
    ) -> dict:
        """Upload the reel as native video and publish it."""
        # 1. initialize
        init = self._t().request(
            "POST", VIDEOS_URL, params={"action": "initializeUpload"},
            headers=self._headers(),
            json={"initializeUploadRequest": {
                "owner": self.author_urn,
                "fileSizeBytes": len(video_bytes),
                "uploadCaptions": False,
                "uploadThumbnail": False,
            }},
        )
        value = raise_for_status(init).json().get("value", {})
        video_urn = value.get("video", "")
        instructions = value.get("uploadInstructions", [])
        if not video_urn or not instructions:
            raise ValueError("initializeUpload returned no video URN / instructions")

        # 2. upload each part; collect the returned ETags
        etags: list[str] = []
        for part in instructions:
            put = self._t().request(
                "PUT", part["uploadUrl"],
                headers={**bearer(self.access_token), "Content-Type": content_type},
                data=video_bytes,
            )
            raise_for_status(put)
            etags.append(put.headers.get("ETag") or put.headers.get("etag", ""))

        # 3. finalize
        finalize = self._t().request(
            "POST", VIDEOS_URL, params={"action": "finalizeUpload"},
            headers=self._headers(),
            json={"finalizeUploadRequest": {
                "video": video_urn,
                "uploadToken": "",
                "uploadedPartIds": etags,
            }},
        )
        raise_for_status(finalize)

        # 4. create the post that carries the video
        post = self._t().request(
            "POST", POSTS_URL, headers=self._headers(),
            json={
                "author": self.author_urn,
                "commentary": commentary,
                "visibility": visibility,
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "content": {"media": {"id": video_urn, "title": "Cinemory reel"}},
                "lifecycleState": "PUBLISHED",
            },
        )
        raise_for_status(post)
        return {
            "video_urn": video_urn,
            "post_id": post.headers.get("x-restli-id") or post.headers.get("X-RestLi-Id", ""),
        }

    # ── helpers ──────────────────────────────────────────────────────────────
    def _headers(self) -> dict[str, str]:
        return {
            **bearer(self.access_token),
            "LinkedIn-Version": self.version,
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def _t(self) -> Transport:
        if self._transport is None:  # pragma: no cover - real-path only
            from ._http import RequestsTransport

            self._transport = RequestsTransport()
        return self._transport

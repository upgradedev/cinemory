"""Offline tests for the opt-in live connectors.

Every network call is served by an in-memory ``FakeTransport`` — no third-party
HTTP library is imported, no credentials are used, no real photos or accounts
are touched. These tests prove the multi-step connector *flows* (OAuth exchange,
Picker session lifecycle, YouTube resumable upload, LinkedIn share) are wired
correctly, entirely offline.
"""
import json

import pytest

from cinemory.connectors._http import HttpError, HttpResponse, raise_for_status
from cinemory.connectors.google_photos import (
    PICKER_SCOPE,
    GoogleOAuth,
    GooglePhotosPicker,
)
from cinemory.connectors.linkedin import LinkedInShare
from cinemory.connectors.youtube import YouTubeUploader


class FakeTransport:
    """Serves queued responses in order and records every request."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def request(self, method, url, *, headers=None, params=None, data=None, json=None):
        self.calls.append({"method": method, "url": url, "headers": headers,
                           "params": params, "data": data, "json": json})
        if not self._responses:
            raise AssertionError(f"unexpected request: {method} {url}")
        return self._responses.pop(0)


def jresp(status=200, obj=None, headers=None, body=None):
    b = body if body is not None else (json.dumps(obj).encode() if obj is not None else b"")
    return HttpResponse(status=status, headers=headers or {}, body=b)


# ── _http ────────────────────────────────────────────────────────────────────
def test_raise_for_status_raises_on_error():
    with pytest.raises(HttpError):
        raise_for_status(jresp(403, {"error": "nope"}))


def test_httpresponse_json_and_ok():
    r = jresp(201, {"a": 1})
    assert r.ok and r.json() == {"a": 1}


# ── Google OAuth ──────────────────────────────────────────────────────────────
def test_authorization_url_is_pure_and_has_picker_scope():
    oauth = GoogleOAuth("cid", "secret", "https://app/cb")
    url = oauth.authorization_url(state="xyz")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=cid" in url and "state=xyz" in url
    assert "photospicker.mediaitems.readonly" in url
    assert PICKER_SCOPE.split("/")[-1] in url


def test_exchange_code_posts_and_returns_token():
    t = FakeTransport([jresp(200, {"access_token": "tok", "refresh_token": "r"})])
    oauth = GoogleOAuth("cid", "secret", "https://app/cb", transport=t)
    tok = oauth.exchange_code("authcode")
    assert tok["access_token"] == "tok"
    call = t.calls[0]
    assert call["method"] == "POST"
    assert call["data"]["grant_type"] == "authorization_code"
    assert call["data"]["code"] == "authcode"


# ── Google Photos Picker ──────────────────────────────────────────────────────
def test_picker_full_flow_offline():
    t = FakeTransport([
        jresp(200, {"id": "sess1", "pickerUri": "https://photos.google.com/pick/sess1",
                    "mediaItemsSet": False}),
        jresp(200, {"id": "sess1", "mediaItemsSet": False,
                    "pollingConfig": {"pollInterval_seconds": 1}}),
        jresp(200, {"id": "sess1", "mediaItemsSet": True}),
        jresp(200, {"mediaItems": [{"id": "m1", "mediaFile": {"baseUrl": "https://b/m1"}}],
                    "nextPageToken": "p2"}),
        jresp(200, {"mediaItems": [{"id": "m2", "mediaFile": {"baseUrl": "https://b/m2"}}]}),
        jresp(200, body=b"\x89PNG-bytes-1"),
    ])
    picker = GooglePhotosPicker("access-tok", transport=t)

    session = picker.create_session()
    assert session["id"] == "sess1"
    assert session["pickerUri"].endswith("sess1")

    sleeps = []
    ready = picker.wait_for_selection("sess1", sleeper=sleeps.append)
    assert ready["mediaItemsSet"] is True
    assert sleeps  # polled at least once with the configured interval

    items = picker.list_media_items("sess1")
    assert [i["id"] for i in items] == ["m1", "m2"]  # paging followed nextPageToken

    data = picker.download_media_item(items[0])
    assert data == b"\x89PNG-bytes-1"
    # baseUrl requested with the =d download parameter + bearer auth
    dl_call = t.calls[-1]
    assert dl_call["url"] == "https://b/m1=d"
    assert dl_call["headers"]["Authorization"] == "Bearer access-tok"


def test_picker_download_requires_base_url():
    picker = GooglePhotosPicker("tok", transport=FakeTransport([]))
    with pytest.raises(ValueError):
        picker.download_media_item({"id": "x"})


# ── YouTube ───────────────────────────────────────────────────────────────────
def test_youtube_resumable_upload_two_step():
    t = FakeTransport([
        jresp(200, headers={"Location": "https://upload.googleapis.com/resumable/xyz"}),
        jresp(200, {"id": "vid123", "status": {"privacyStatus": "private"}}),
    ])
    up = YouTubeUploader("yt-token", transport=t)
    result = up.upload(b"MP4BYTES", title="My Reel", description="d", privacy_status="private")

    assert result["id"] == "vid123"
    assert result["url"] == "https://youtu.be/vid123"
    assert result["privacy_status"] == "private"

    init, put = t.calls
    assert init["method"] == "POST"
    assert init["params"] == {"uploadType": "resumable", "part": "snippet,status"}
    assert init["json"]["snippet"]["title"] == "My Reel"
    assert put["method"] == "PUT"
    assert put["url"] == "https://upload.googleapis.com/resumable/xyz"
    assert put["data"] == b"MP4BYTES"


def test_youtube_upload_without_location_raises():
    t = FakeTransport([jresp(200, {}, headers={})])
    with pytest.raises(ValueError):
        YouTubeUploader("tok", transport=t).upload(b"x", title="t")


# ── LinkedIn ──────────────────────────────────────────────────────────────────
def test_linkedin_share_link():
    t = FakeTransport([jresp(201, {}, headers={"x-restli-id": "urn:li:share:1"})])
    li = LinkedInShare("li-token", "urn:li:person:abc", transport=t)
    res = li.share_link("Check out my reel", "https://cinemory/r/1")
    assert res["post_id"] == "urn:li:share:1"
    call = t.calls[0]
    assert call["json"]["author"] == "urn:li:person:abc"
    assert call["json"]["content"]["article"]["source"] == "https://cinemory/r/1"
    assert call["headers"]["LinkedIn-Version"]


def test_linkedin_share_video_multistep():
    t = FakeTransport([
        jresp(200, {"value": {"video": "urn:li:video:v1",
                              "uploadInstructions": [{"uploadUrl": "https://up/1"}]}}),
        jresp(200, {}, headers={"ETag": "etag-1"}),
        jresp(200, {}),  # finalize
        jresp(201, {}, headers={"x-restli-id": "urn:li:share:2"}),
    ])
    li = LinkedInShare("li-token", "urn:li:organization:99", transport=t)
    res = li.share_video(b"MP4", "our event highlight")
    assert res["video_urn"] == "urn:li:video:v1"
    assert res["post_id"] == "urn:li:share:2"

    methods = [c["method"] for c in t.calls]
    assert methods == ["POST", "PUT", "POST", "POST"]  # init, upload, finalize, post
    assert t.calls[1]["data"] == b"MP4"

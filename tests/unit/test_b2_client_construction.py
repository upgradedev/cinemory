"""Unit tests pinning boto3 client construction for B2 presigned URLs.

B2 rejects **region-less** presigned GET URLs with 401 Unauthorized while
direct put/get tolerate the omission — so a mis-built client breaks ONLY
playback, the worst kind of partial failure. Proven live 2026-07-22: the
box-minted presign 401'd; a region-scoped SigV4 presign of the SAME object
returned 200. The adapter must therefore build its client with the resolved
region + ``signature_version="s3v4"``.

The construction tests stub the ``boto3``/``botocore.config`` import seam
(neither is installed in offline CI — they live in the ``[live]`` extra) and
spy on the kwargs. A final test runs REAL boto3 signing when the library is
available locally and asserts the presigned URL shape end-to-end.
"""
from __future__ import annotations

import sys
import types

import pytest

from cinemory.adapters.b2_storage import B2Storage

_B2_ENV = (
    "B2_KEY_ID", "B2_APP_KEY", "B2_ENDPOINT_URL", "B2_REGION", "B2_BUCKET_NAME",
    "B2_APPLICATION_KEY_ID", "B2_APPLICATION_KEY", "B2_S3_ENDPOINT",
    "B2_KEY_PREFIX", "B2_PREFIX",
)


@pytest.fixture(autouse=True)
def _b2_env(monkeypatch):
    for name in _B2_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("B2_BUCKET_NAME", "cinemory-live")
    monkeypatch.setenv("B2_S3_ENDPOINT", "https://s3.eu-central-003.backblazeb2.com")
    # Dummy creds so the real-path branch (client is None) is taken; presign
    # signing is purely local, so no network call ever carries these.
    monkeypatch.setenv("B2_KEY_ID", "unit-test-key-id")
    monkeypatch.setenv("B2_APP_KEY", "unit-test-app-key")


def _stub_boto3(monkeypatch):
    """Install stub ``boto3``/``botocore.config`` modules; spy on ``client()``."""
    recorded: dict = {}

    class _StubConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _StubClient:
        def get_object(self, **kwargs):  # no index.jsonl yet → empty catalogue
            raise KeyError(kwargs.get("Key"))

    boto3_mod = types.ModuleType("boto3")

    def _client(service, **kwargs):
        recorded["service"] = service
        recorded["kwargs"] = kwargs
        return _StubClient()

    boto3_mod.client = _client
    botocore_mod = types.ModuleType("botocore")
    botocore_config_mod = types.ModuleType("botocore.config")
    botocore_config_mod.Config = _StubConfig
    botocore_mod.config = botocore_config_mod
    monkeypatch.setitem(sys.modules, "boto3", boto3_mod)
    monkeypatch.setitem(sys.modules, "botocore", botocore_mod)
    monkeypatch.setitem(sys.modules, "botocore.config", botocore_config_mod)
    return recorded


def test_client_constructed_with_derived_region_and_sigv4(monkeypatch):
    rec = _stub_boto3(monkeypatch)
    store = B2Storage()
    assert rec["service"] == "s3"
    # Region derived from the s3.<region>.backblazeb2.com endpoint host.
    assert store.region == "eu-central-003"
    assert rec["kwargs"]["region_name"] == "eu-central-003"
    assert rec["kwargs"]["config"].kwargs == {"signature_version": "s3v4"}
    assert rec["kwargs"]["endpoint_url"] == "https://s3.eu-central-003.backblazeb2.com"


def test_explicit_b2_region_env_wins_over_derivation(monkeypatch):
    monkeypatch.setenv("B2_REGION", "us-west-004")
    rec = _stub_boto3(monkeypatch)
    store = B2Storage()
    assert store.region == "us-west-004"
    assert rec["kwargs"]["region_name"] == "us-west-004"


def test_underivable_region_omits_region_name_but_keeps_sigv4(monkeypatch):
    """A non-B2 endpoint (e.g. a local S3 stand-in) has no derivable region:
    never guess one — fall back to the SDK default — but SigV4 stays pinned."""
    monkeypatch.setenv("B2_S3_ENDPOINT", "https://minio.internal:9000")
    rec = _stub_boto3(monkeypatch)
    store = B2Storage()
    assert store.region is None
    assert "region_name" not in rec["kwargs"]
    assert rec["kwargs"]["config"].kwargs == {"signature_version": "s3v4"}


def test_presigned_url_carries_sigv4_algorithm_and_region_scope(monkeypatch):
    """REAL boto3 signing (skipped where boto3 is absent, e.g. offline CI):
    the minted URL must advertise ``X-Amz-Algorithm=AWS4-HMAC-SHA256`` and
    scope the credential to the region, on the region endpoint host — the
    exact URL shape B2 answered 200 where the region-less one 401'd.
    Host and query are PARSED (never substring-matched on the raw URL)."""
    pytest.importorskip("boto3")
    from urllib.parse import parse_qs, urlsplit

    # Signing is local; forbid the only construction-time network call.
    monkeypatch.setattr(B2Storage, "reload_index", lambda self: [])
    store = B2Storage()
    url = store.get_url("graduation/reels/aa/bb/reel.mp4", expires_in=600)

    parts = urlsplit(url)
    endpoint_host = "s3.eu-central-003.backblazeb2.com"
    # Signed against the region endpoint (virtual-hosted or path addressing).
    assert parts.hostname == endpoint_host or parts.hostname.endswith(f".{endpoint_host}")
    query = parse_qs(parts.query)
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert "/eu-central-003/" in query["X-Amz-Credential"][0]  # region in scope
    assert query["X-Amz-Expires"] == ["600"]

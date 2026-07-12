"""Unit tests for Backblaze B2 env resolution (:mod:`cinemory.config`).

The live path accepts two equally-valid env name sets — Cinemory's legacy names
and Backblaze's own canonical names — so a user who already exports the
canonical set needs no ``.env`` edit. These tests pin that fallback chain, the
endpoint-scheme normalization, the region derivation, legacy-over-canonical
precedence, and that the offline default is untouched by any of it.
"""
from __future__ import annotations

import pytest

from cinemory import config
from cinemory.adapters import FakeMediaProvider, FakeStorage

# Every B2 env name either resolver reads. The dev machine that authored this
# has the canonical set exported, so each test starts from a clean slate and
# sets only what it exercises — otherwise CI (empty env) and local diverge.
_B2_ENV = (
    "B2_KEY_ID",
    "B2_APP_KEY",
    "B2_ENDPOINT_URL",
    "B2_REGION",
    "B2_BUCKET_NAME",
    "B2_APPLICATION_KEY_ID",
    "B2_APPLICATION_KEY",
    "B2_S3_ENDPOINT",
    "B2_KEY_PREFIX",
    "B2_PREFIX",
)


@pytest.fixture(autouse=True)
def _clear_b2_env(monkeypatch):
    for name in _B2_ENV:
        monkeypatch.delenv(name, raising=False)


# (a) Canonical Backblaze-native names resolve when the legacy names are absent.
def test_canonical_names_resolve_as_fallback(monkeypatch):
    monkeypatch.setenv("B2_APPLICATION_KEY_ID", "canon-key-id")
    monkeypatch.setenv("B2_APPLICATION_KEY", "canon-app-key")
    monkeypatch.setenv("B2_BUCKET_NAME", "cinemory-demo")
    monkeypatch.setenv("B2_S3_ENDPOINT", "https://s3.eu-central-003.backblazeb2.com")

    cfg = config.resolve_b2_config()

    assert cfg.key_id == "canon-key-id"
    assert cfg.app_key == "canon-app-key"
    assert cfg.bucket == "cinemory-demo"
    assert cfg.endpoint_url == "https://s3.eu-central-003.backblazeb2.com"


# (b) A scheme-less endpoint (the canonical B2_S3_ENDPOINT form) gets https://.
def test_schemeless_endpoint_gets_https_prefix(monkeypatch):
    monkeypatch.setenv("B2_S3_ENDPOINT", "s3.eu-central-003.backblazeb2.com")

    cfg = config.resolve_b2_config()

    assert cfg.endpoint_url == "https://s3.eu-central-003.backblazeb2.com"


def test_existing_scheme_is_preserved(monkeypatch):
    monkeypatch.setenv("B2_ENDPOINT_URL", "http://localhost:9000")

    cfg = config.resolve_b2_config()

    assert cfg.endpoint_url == "http://localhost:9000"


# (c) Region is derived from the s3.<region>.backblazeb2.com host.
def test_region_derived_from_endpoint_host(monkeypatch):
    monkeypatch.setenv("B2_S3_ENDPOINT", "s3.eu-central-003.backblazeb2.com")

    cfg = config.resolve_b2_config()

    assert cfg.region == "eu-central-003"


def test_region_underivable_is_none(monkeypatch):
    monkeypatch.setenv("B2_ENDPOINT_URL", "https://minio.internal.example/")

    cfg = config.resolve_b2_config()

    assert cfg.region is None


def test_explicit_region_wins_over_derivation(monkeypatch):
    monkeypatch.setenv("B2_S3_ENDPOINT", "s3.eu-central-003.backblazeb2.com")
    monkeypatch.setenv("B2_REGION", "us-west-004")

    cfg = config.resolve_b2_config()

    assert cfg.region == "us-west-004"


# (d) The legacy name takes precedence over the canonical fallback.
def test_legacy_key_id_wins_over_canonical(monkeypatch):
    monkeypatch.setenv("B2_KEY_ID", "legacy-key-id")
    monkeypatch.setenv("B2_APPLICATION_KEY_ID", "canon-key-id")
    monkeypatch.setenv("B2_APP_KEY", "legacy-app-key")
    monkeypatch.setenv("B2_APPLICATION_KEY", "canon-app-key")
    monkeypatch.setenv("B2_ENDPOINT_URL", "https://s3.us-west-004.backblazeb2.com")
    monkeypatch.setenv("B2_S3_ENDPOINT", "https://s3.eu-central-003.backblazeb2.com")

    cfg = config.resolve_b2_config()

    assert cfg.key_id == "legacy-key-id"
    assert cfg.app_key == "legacy-app-key"
    assert cfg.endpoint_url == "https://s3.us-west-004.backblazeb2.com"
    assert cfg.region == "us-west-004"


# (e) Offline mode is unaffected: no B2 env, default mode, fakes wired.
def test_offline_mode_unaffected_by_b2_resolution(monkeypatch):
    monkeypatch.delenv("CINEMORY_MODE", raising=False)

    assert config.mode() == "offline"

    # With no credentials at all the resolver still returns cleanly (all None) —
    # it never raises, so importing/using config offline is safe.
    cfg = config.resolve_b2_config()
    assert cfg == config.B2Config(
        bucket=None, endpoint_url=None, key_id=None, app_key=None, region=None, key_prefix=None
    )

    # The offline build path returns the fakes regardless of B2 config.
    from cinemory.adapters import FakeMediaProvider, FakeStorage

    assert isinstance(config.build_storage(), FakeStorage)
    assert isinstance(config.build_provider(), FakeMediaProvider)


def test_prefix_resolution(monkeypatch):
    monkeypatch.setenv("B2_KEY_PREFIX", "cinemory/")
    cfg = config.resolve_b2_config()
    assert cfg.key_prefix == "cinemory/"

    monkeypatch.delenv("B2_KEY_PREFIX")
    monkeypatch.setenv("B2_PREFIX", "other-prefix")
    cfg = config.resolve_b2_config()
    assert cfg.key_prefix == "other-prefix"


# ── Degrade-to-offline: live mode without creds must still wire the fakes ──────
# so the core action (POST /reels) never 500s. See config._b2_ready / build_*.
def test_live_without_b2_creds_degrades_to_fake_storage(monkeypatch):
    monkeypatch.setenv("CINEMORY_MODE", "live")
    # _clear_b2_env already stripped every B2 var — no creds present.
    assert config.storage_ready() is False
    assert isinstance(config.build_storage(), FakeStorage)


def test_live_without_gmi_key_degrades_to_fake_provider(monkeypatch):
    monkeypatch.setenv("CINEMORY_MODE", "live")
    monkeypatch.delenv("GMI_API_KEY", raising=False)
    assert config.provider_ready() is False
    assert isinstance(config.build_provider(), FakeMediaProvider)


def test_b2_ready_true_when_all_creds_present(monkeypatch):
    # Do NOT construct B2Storage (needs boto3, not in CI) — assert the predicate.
    monkeypatch.setenv("CINEMORY_MODE", "live")
    monkeypatch.setenv("B2_BUCKET_NAME", "cinemory-demo")
    monkeypatch.setenv("B2_ENDPOINT_URL", "https://s3.eu-central-003.backblazeb2.com")
    monkeypatch.setenv("B2_KEY_ID", "id")
    monkeypatch.setenv("B2_APP_KEY", "secret")
    import importlib.util
    expected = importlib.util.find_spec("boto3") is not None
    assert config._b2_ready() is expected


def test_genblaze_ready_reflects_gmi_key(monkeypatch):
    monkeypatch.setenv("CINEMORY_MODE", "live")
    monkeypatch.setenv("GENBLAZE_PROVIDER", "gmicloud")
    monkeypatch.delenv("GMI_API_KEY", raising=False)
    assert config._genblaze_ready() is False
    monkeypatch.setenv("GMI_API_KEY", "gmi-secret")
    import importlib.util
    expected = importlib.util.find_spec("genblaze_core") is not None
    assert config._genblaze_ready() is expected

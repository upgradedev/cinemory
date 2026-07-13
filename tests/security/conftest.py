"""Shared fixtures for the pen-test (application-security) suite.

Every test here drives the *real* FastAPI app / pipeline / adapters — no mocked
security controls. The suite is fully offline (no boto3, no credentials, no
network), exactly as it runs in CI.
"""
from __future__ import annotations

import importlib
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

# A genuine 1x1 PNG so the ingest path sees real image magic bytes.
PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc``\x00\x00\x00\x04"
    b"\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Env vars that carry live B2 / provider credentials. The suite scrubs these so
# the app is exercised in its offline/degraded posture (the CI reality).
_CRED_VARS = (
    "B2_KEY_ID", "B2_APP_KEY", "B2_ENDPOINT_URL", "B2_REGION", "B2_BUCKET_NAME",
    "B2_APPLICATION_KEY_ID", "B2_APPLICATION_KEY", "B2_S3_ENDPOINT",
    "B2_KEY_PREFIX", "B2_PREFIX", "GMI_API_KEY",
)


def fresh_client(mode: str = "offline") -> tuple[TestClient, callable]:
    """A TestClient over a freshly-reloaded api module at ``mode``.

    Returns ``(client, restore)``; ``restore()`` reloads the module back to the
    offline default so module-level storage/provider state never leaks into a
    later test (mirrors the readiness gate's isolation pattern — no module-scope
    ``os.environ`` mutation left dangling).
    """
    prev = os.environ.get("CINEMORY_MODE")
    os.environ["CINEMORY_MODE"] = mode
    import cinemory.api as api

    reloaded = importlib.reload(api)

    def restore() -> None:
        if prev is None:
            os.environ.pop("CINEMORY_MODE", None)
        else:
            os.environ["CINEMORY_MODE"] = prev
        importlib.reload(api)

    return TestClient(reloaded.app), restore


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Offline TestClient with clean isolation before and after."""
    c, restore = fresh_client("offline")
    try:
        yield c
    finally:
        restore()


@pytest.fixture
def scrub_credentials() -> Iterator[None]:
    """Remove any B2/provider creds for the duration of a test, then restore."""
    saved = {k: os.environ.pop(k, None) for k in _CRED_VARS}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

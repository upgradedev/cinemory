"""PEN-TEST — Multitenancy isolation.

Threat: a signed-in caller's reels/uploads must be isolated to their own
tenant. This file adversarially proves the isolation boundary from the
outside, driving the real FastAPI app exactly as CI runs it (offline,
FakeStorage, no network — see ``tests/security/conftest.py``):

  * a forged/garbage/expired bearer credential is REJECTED (401) on every
    route that resolves a tenant — never silently downgraded to guest;
  * cross-tenant (and guest) reads of another tenant's reel 404 — the row is
    physically absent from the caller's own tenant-scoped index, not merely
    rejected by a comparison;
  * ``DELETE /me/data`` cannot be steered outside the caller's own prefix;
  * the tenant cannot be spoofed via a query param, a non-``Authorization``
    header, or a request-body field — only a verified token sets it.

Functional/wiring coverage (happy paths, ``/me/library`` shape, async job
polling, the ``get_url`` presign branch, direct ``_TenantScopedStorage``
construction tests) lives in
``tests/integration/test_api_multitenancy.py`` — it counts toward the
coverage gate this file does not (``tests/security`` runs in its own
pen-test CI job). Tokens here are signed with a LOCALLY generated RSA
keypair (no network) via the same offline ``key_source`` seam
``tests/unit/test_auth.py`` uses.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from cinemory import auth

PROJECT_ID = "cinemory-sec-mt-test-project"
KID = "sec-mt-test-signing-key"


def _generate_keypair_and_cert() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "cinemory-sec-mt-test")])
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(private_key, hashes.SHA256())
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    return private_pem, cert_pem


def _token_for(uid: str, private_pem: str, **overrides) -> str:
    now = time.time()
    claims = {
        "iss": f"https://securetoken.google.com/{PROJECT_ID}",
        "aud": PROJECT_ID,
        "sub": uid,
        "iat": int(now) - 30,
        "exp": int(now) + 3600,
        "auth_time": int(now) - 30,
    }
    claims.update(overrides)
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": KID})


@pytest.fixture
def bearer_for(client, monkeypatch):
    """Wires ``FIREBASE_PROJECT_ID`` + an offline ``key_source`` (local RSA
    keypair, no network), then returns ``bearer_for(uid) -> headers``.
    Depends on the ``client`` fixture (see ``conftest.py``) so it runs after
    that fixture's module reload.
    """
    private_pem, cert_pem = _generate_keypair_and_cert()
    monkeypatch.setenv("FIREBASE_PROJECT_ID", PROJECT_ID)
    monkeypatch.setattr(auth, "_default_key_source", lambda: {KID: cert_pem})

    def _make(uid: str, **overrides) -> dict:
        return {"Authorization": f"Bearer {_token_for(uid, private_pem, **overrides)}"}

    return _make


def _garbage_headers() -> dict:
    return {"Authorization": "Bearer this-is-not-a-valid-jwt-at-all"}


# ── (1) forged/garbage token -> 401 on EVERY wired route, never guest ────────
# Deliberately excludes /health and /occasions: those have no tenant
# dependency by design (a liveness probe must never 401 on a bad credential —
# see test_forged_token_does_not_break_unauthenticated_routes below), so
# including them here would be testing the wrong contract.

_WIRED_ROUTE_CALLS = [
    ("POST /reels", lambda c, h: c.post(
        "/reels", json={"name": "sec-401-a", "chapters": 1, "per_chapter": 1}, headers=h)),
    ("POST /reels/upload", lambda c, h: c.post("/reels/upload", json={
        "name": "sec-401-b",
        "photos": [{"filename": "p.png", "content_base64": "cHg="}]}, headers=h)),
    ("POST /reels/upload-multipart", lambda c, h: c.post(
        "/reels/upload-multipart",
        files=[("files", ("p.png", b"px", "image/png"))],
        data={"name": "sec-401-c"}, headers=h)),
    ("POST /reels/jobs", lambda c, h: c.post("/reels/jobs", json={
        "name": "sec-401-d",
        "photos": [{"filename": "p.png", "content_base64": "cHg="}]}, headers=h)),
    ("GET /reels/jobs/{id}", lambda c, h: c.get(
        "/reels/jobs/nonexistent-job-id", headers=h)),
    ("GET /reels/{name}", lambda c, h: c.get("/reels/nonexistent-reel", headers=h)),
    ("GET /reels/{name}/video", lambda c, h: c.get(
        "/reels/nonexistent-reel/video", headers=h)),
    ("GET /reels/{name}/verify", lambda c, h: c.get(
        "/reels/nonexistent-reel/verify", headers=h)),
    ("GET /me/library", lambda c, h: c.get("/me/library", headers=h)),
    ("DELETE /me/data", lambda c, h: c.delete("/me/data", headers=h)),
]


@pytest.mark.parametrize(
    "call", [c for _, c in _WIRED_ROUTE_CALLS], ids=[label for label, _ in _WIRED_ROUTE_CALLS]
)
def test_forged_token_is_401_on_every_wired_route(client, monkeypatch, call):
    """A bad credential is a hard 401 everywhere the tenant dependency is
    wired — proving ``get_tenant`` never lets a present-but-invalid token
    fall through as guest, on ANY of the 10 routes it guards. The route
    handler body never even runs (FastAPI resolves dependencies first), so
    an otherwise-404-worthy nonexistent name/id is irrelevant here.

    Requires ``FIREBASE_PROJECT_ID`` set: with it unset, ``get_tenant``
    correctly treats EVERY request as guest without even looking at the
    header (see ``test_project_id_unset_treats_a_bearer_header_as_guest`` in
    the integration suite) — so a forged token would be silently ignored
    exactly like a valid one, and this test would be proving nothing.
    """
    monkeypatch.setenv("FIREBASE_PROJECT_ID", PROJECT_ID)
    r = call(client, _garbage_headers())
    assert r.status_code == 401


def test_forged_token_does_not_break_unauthenticated_routes(client):
    """/health and /occasions carry no tenant dependency by design — a
    liveness probe must keep working even with a garbage credential in
    flight (nothing about them is tenant-scoped)."""
    headers = _garbage_headers()
    assert client.get("/health", headers=headers).status_code == 200
    assert client.get("/occasions", headers=headers).status_code == 200


def test_expired_token_is_401_not_guest(client, bearer_for):
    headers = bearer_for("sec-mt-expired",
                         iat=int(time.time()) - 7200, exp=int(time.time()) - 3600)
    assert client.get("/me/library", headers=headers).status_code == 401


def test_malformed_bearer_scheme_is_401_not_guest(client):
    r = client.get("/me/library", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert r.status_code == 401


def test_token_signed_by_attacker_key_is_401(client, bearer_for):
    """The classic forged-token shape: signed with an unrelated private key
    but CLAIMING the legitimate kid. ``key_source`` resolves the real public
    cert for that kid, so the signature check fails even though the kid
    lookup succeeds."""
    attacker_private, _attacker_cert = _generate_keypair_and_cert()
    forged = _token_for("sec-mt-forger", attacker_private)
    r = client.get("/me/library", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


# ── (2) cross-tenant leak: the flagship isolation proof ──────────────────────


def test_cross_tenant_reel_leak_is_impossible(client, bearer_for):
    """Tenant A generates a reel named 'foo'. Tenant B's GET must 404 — A's
    row is physically absent from B's tenant-scoped index, not merely
    rejected by a name comparison. A GUEST's GET must 404 too — A's reel
    lives under ``tenants/<A>/`` which a guest's unprefixed scan never
    matches."""
    a = bearer_for("sec-mt-tenant-a")
    b = bearer_for("sec-mt-tenant-b")

    r = client.post("/reels", json={"name": "foo", "chapters": 1, "per_chapter": 1}, headers=a)
    assert r.status_code == 200

    assert client.get("/reels/foo", headers=a).status_code == 200  # sanity: A sees it
    assert client.get("/reels/foo", headers=b).status_code == 404
    assert client.get("/reels/foo").status_code == 404
    assert client.get("/reels/foo/video", headers=b).status_code == 404
    assert client.get("/reels/foo/verify", headers=b).status_code == 404
    # B's own library is empty — A's reel is not merely hidden from GET, it
    # never appears in any enumeration B can perform either.
    assert client.get("/me/library", headers=b).json() == {"reels": []}


# ── (3) DELETE /me/data cannot reach outside the caller's own prefix ────────


def test_delete_my_data_cannot_reach_outside_own_prefix(client, bearer_for):
    a = bearer_for("sec-mt-del-a")
    b = bearer_for("sec-mt-del-b")
    client.post("/reels", json={"name": "mine", "chapters": 1, "per_chapter": 1}, headers=a)
    client.post("/reels", json={"name": "not-mine", "chapters": 1, "per_chapter": 1}, headers=b)
    client.post("/reels", json={"name": "guest-untouched", "chapters": 1, "per_chapter": 1})

    r = client.delete("/me/data", headers=a)
    assert r.status_code == 200
    assert r.json()["deleted"] >= 1

    assert client.get("/reels/mine", headers=a).status_code == 404
    # Neither tenant B's reel nor the guest reel were reachable through this
    # call — there is no key this loop could ever construct outside
    # tenants/sec-mt-del-a/.
    assert client.get("/reels/not-mine", headers=b).status_code == 200
    assert client.get("/reels/guest-untouched").status_code == 200


def test_delete_my_data_guest_is_401_never_deletes_anything(client):
    r = client.delete("/me/data")
    assert r.status_code == 401


# ── (4) tenant cannot be spoofed via non-token channels ──────────────────────


def test_spoofed_tenant_via_query_header_or_body_is_ignored(client, bearer_for):
    a = bearer_for("sec-mt-spoof-a")
    b = bearer_for("sec-mt-spoof-b")
    client.post("/reels", json={"name": "spoof-target", "chapters": 1, "per_chapter": 1},
               headers=a)

    # Attacker B, authenticated as themselves, tries every non-token channel
    # to reach into A's data.
    r1 = client.get("/reels/spoof-target?tenant=sec-mt-spoof-a", headers=b)
    r2 = client.get("/reels/spoof-target", headers={**b, "X-Tenant": "sec-mt-spoof-a"})
    assert r1.status_code == 404
    assert r2.status_code == 404

    # A body field named "tenant" on a create is silently ignored (Pydantic
    # drops unknown fields) — B's own reel, not attributed to A.
    r3 = client.post("/reels", json={"name": "spoof-attempt", "chapters": 1,
                                     "per_chapter": 1, "tenant": "sec-mt-spoof-a"}, headers=b)
    assert r3.status_code == 200
    assert client.get("/reels/spoof-attempt", headers=a).status_code == 404
    assert client.get("/reels/spoof-attempt", headers=b).status_code == 200

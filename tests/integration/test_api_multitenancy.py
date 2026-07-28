"""Integration tests for optional per-user multitenancy.

Every token here is signed with a LOCALLY generated RSA keypair — no network,
no real Firebase project — mirroring the offline ``key_source`` injection seam
``tests/unit/test_auth.py`` uses for :mod:`cinemory.auth` directly, one layer
up through the real FastAPI app: ``cinemory.auth._default_key_source`` is
monkeypatched so ``GET /me/library`` etc. verify these tokens with zero
network calls, exactly as CI runs it.

These tests drive the SAME shared ``client``/``api._storage`` every other
``tests/integration/test_api_*.py`` file uses (see those files' own
docstrings) — isolation between tenants therefore has to hold even though
every test in this file (and every other integration test) shares one
process-wide storage object. That is the point: a tenant's reel lives under
``tenants/<uid>/...`` in that SAME store, and this file proves a caller can
never read/list/delete outside their own prefix. Reel/tenant names below are
distinctive (``mt-...``) so they never collide with another test file's guest
reels sharing the same storage.

``tests/security/test_multitenancy_isolation.py`` covers the same feature
from a pure adversarial angle (forged tokens across every wired route,
spoofing attempts) as bonus assurance in the separate pen-test CI job; the
functional/wiring coverage that counts toward the coverage gate lives here.
"""
from __future__ import annotations

import base64
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

import cinemory.api as api
import cinemory.auth as auth
from cinemory.adapters import FakeStorage
from cinemory.keys import safe_component

client = TestClient(api.app)

PROJECT_ID = "cinemory-mt-test-project"
KID = "mt-test-signing-key"


# ── local RSA keypair + Firebase-ID-token minting (offline, no network) ──────


def _generate_keypair_and_cert() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "cinemory-mt-test")])
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
def bearer_for(monkeypatch):
    """Wires ``FIREBASE_PROJECT_ID`` + an offline ``key_source`` (local RSA
    keypair, no network — see module docstring), then returns
    ``bearer_for(uid) -> {"Authorization": "Bearer <valid token for uid>"}``.
    """
    private_pem, cert_pem = _generate_keypair_and_cert()
    monkeypatch.setenv("FIREBASE_PROJECT_ID", PROJECT_ID)
    monkeypatch.setattr(auth, "_default_key_source", lambda: {KID: cert_pem})

    def _make(uid: str, **overrides) -> dict:
        return {"Authorization": f"Bearer {_token_for(uid, private_pem, **overrides)}"}

    return _make


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ── (a) authed happy path: create + fetch own reel ───────────────────────────


def test_authed_tenant_creates_and_fetches_own_reel(bearer_for):
    headers = bearer_for("mt-tenant-solo")
    r = client.post("/reels", json={"name": "mt-solo", "chapters": 2, "per_chapter": 1},
                    headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["reel_name"] == "mt-solo"
    assert len(body["reel_sha256"]) == 64

    fetched = client.get("/reels/mt-solo", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["reel_name"] == "mt-solo"

    # The underlying key is really namespaced under this tenant's prefix.
    prefix = "tenants/" + safe_component("mt-tenant-solo") + "/"
    assert any(row["key"].startswith(prefix + "mt-solo/")
              for row in api._storage.index), "reel not stored under the tenant prefix"


def test_authed_tenant_upload_and_verify_round_trip(bearer_for):
    headers = bearer_for("mt-tenant-verify")
    photos = [{"filename": "p.png", "content_base64": _b64(b"mt-verify-pixels")}]
    r = client.post("/reels/upload", json={"name": "mt-verify", "photos": photos},
                    headers=headers)
    assert r.status_code == 200

    receipt = client.get("/reels/mt-verify/verify", headers=headers).json()
    assert receipt["success"] is True

    video = client.get("/reels/mt-verify/video", headers=headers)
    assert video.status_code == 200
    assert video.headers["content-type"].startswith("video/mp4")


# ── (b)/(c) cross-tenant + guest isolation: THE flagship proof ───────────────


def test_cross_tenant_and_guest_cannot_see_each_others_reel(bearer_for):
    a = bearer_for("mt-tenant-a1")
    b = bearer_for("mt-tenant-b1")

    r = client.post("/reels", json={"name": "mt-foo", "chapters": 1, "per_chapter": 1},
                    headers=a)
    assert r.status_code == 200

    # Tenant A sees it.
    assert client.get("/reels/mt-foo", headers=a).status_code == 200
    # Tenant B cannot — physically absent from B's tenant-scoped index.
    assert client.get("/reels/mt-foo", headers=b).status_code == 404
    # Guest cannot either — mt-foo's key lives under tenants/<a>/..., which a
    # guest's unprefixed scan never matches.
    assert client.get("/reels/mt-foo").status_code == 404
    # Same for playback and verify.
    assert client.get("/reels/mt-foo/video", headers=b).status_code == 404
    assert client.get("/reels/mt-foo/video").status_code == 404
    assert client.get("/reels/mt-foo/verify", headers=b).status_code == 404


def test_two_tenants_can_use_the_identical_reel_name_independently(bearer_for):
    """Namespacing is per-tenant, not global — the SAME reel name is fine for
    two different tenants and each only ever sees their own."""
    a = bearer_for("mt-tenant-a2")
    b = bearer_for("mt-tenant-b2")

    ra = client.post("/reels", json={"name": "mt-shared-name", "chapters": 1,
                                     "per_chapter": 1}, headers=a)
    rb = client.post("/reels", json={"name": "mt-shared-name", "chapters": 2,
                                     "per_chapter": 1}, headers=b)
    assert ra.status_code == 200 and rb.status_code == 200
    # Different content (different chapter counts) -> different sealed hash,
    # proving each tenant generated and stored their OWN object, not a shared
    # collision.
    assert ra.json()["reel_sha256"] != rb.json()["reel_sha256"]

    fetched_a = client.get("/reels/mt-shared-name", headers=a).json()
    fetched_b = client.get("/reels/mt-shared-name", headers=b).json()
    assert fetched_a["manifest_hash"] != fetched_b["manifest_hash"]
    assert fetched_a["reel_asset"]["sha256"] == ra.json()["reel_sha256"]
    assert fetched_b["reel_asset"]["sha256"] == rb.json()["reel_sha256"]


# ── (d)/(e) GET /me/library ───────────────────────────────────────────────────


def test_me_library_lists_only_the_authed_tenants_own_reels(bearer_for):
    a = bearer_for("mt-tenant-lib-a")
    b = bearer_for("mt-tenant-lib-b")
    client.post("/reels", json={"name": "mt-lib-1", "chapters": 1, "per_chapter": 1},
               headers=a)
    client.post("/reels", json={"name": "mt-lib-2", "chapters": 1, "per_chapter": 1},
               headers=a)
    client.post("/reels", json={"name": "mt-lib-b-reel", "chapters": 1, "per_chapter": 1},
               headers=b)

    lib_a = client.get("/me/library", headers=a).json()
    names_a = {r["reel_name"] for r in lib_a["reels"]}
    assert {"mt-lib-1", "mt-lib-2"} <= names_a
    assert "mt-lib-b-reel" not in names_a

    lib_b = client.get("/me/library", headers=b).json()
    names_b = {r["reel_name"] for r in lib_b["reels"]}
    assert "mt-lib-b-reel" in names_b
    assert "mt-lib-1" not in names_b and "mt-lib-2" not in names_b

    # Shape: manifest_hash + created/updated surfaced when available.
    row = next(r for r in lib_a["reels"] if r["reel_name"] == "mt-lib-1")
    assert row["manifest_hash"]
    assert row["created_at"] and row["updated_at"]


def test_me_library_degrades_gracefully_on_an_unreadable_manifest(bearer_for):
    """Mirrors ``verify_reel``'s honest-degrade contract: a manifest object
    that is indexed but can't be read/parsed still lists the reel
    (best-effort, name + null hash/timestamps) rather than 500-ing the whole
    library over one bad object."""
    a = bearer_for("mt-tenant-lib-broken")
    client.post("/reels", json={"name": "mt-lib-broken", "chapters": 1, "per_chapter": 1},
               headers=a)
    prefix = api._tenant_prefix("mt-tenant-lib-broken") + "mt-lib-broken/"
    man_key = next(k for k in api._storage._objects
                  if k.startswith(prefix) and k.endswith("/manifest.json"))
    del api._storage._objects[man_key]

    r = client.get("/me/library", headers=a)
    assert r.status_code == 200
    row = next(x for x in r.json()["reels"] if x["reel_name"] == "mt-lib-broken")
    assert row["manifest_hash"] is None
    assert row["created_at"] is None and row["updated_at"] is None


def test_me_library_guest_is_401():
    r = client.get("/me/library")
    assert r.status_code == 401


def test_me_library_empty_for_a_fresh_tenant(bearer_for):
    r = client.get("/me/library", headers=bearer_for("mt-tenant-never-used"))
    assert r.status_code == 200
    assert r.json() == {"reels": []}


# ── (f)/(g) DELETE /me/data — structural scope proof ──────────────────────────


def test_me_data_delete_scope_proof(bearer_for):
    """The flagship DELETE proof: tenant A's own reel is gone; a reel owned by
    tenant B AND a guest reel both still resolve afterward."""
    a = bearer_for("mt-tenant-del-a")
    b = bearer_for("mt-tenant-del-b")

    client.post("/reels", json={"name": "mt-del-mine", "chapters": 1, "per_chapter": 1},
               headers=a)
    client.post("/reels", json={"name": "mt-del-other-tenant", "chapters": 1,
                                "per_chapter": 1}, headers=b)
    client.post("/reels", json={"name": "mt-del-guest-reel", "chapters": 1,
                                "per_chapter": 1})  # no header -> guest

    # Sanity: all three exist before the delete.
    assert client.get("/reels/mt-del-mine", headers=a).status_code == 200
    assert client.get("/reels/mt-del-other-tenant", headers=b).status_code == 200
    assert client.get("/reels/mt-del-guest-reel").status_code == 200

    resp = client.delete("/me/data", headers=a)
    assert resp.status_code == 200
    assert resp.json()["deleted"] >= 1

    # Tenant A's own reel is gone.
    assert client.get("/reels/mt-del-mine", headers=a).status_code == 404
    assert client.get("/me/library", headers=a).json() == {"reels": []}
    # Tenant B's reel and the guest reel are UNTOUCHED — the delete could
    # never construct a key outside tenants/mt-tenant-del-a/.
    assert client.get("/reels/mt-del-other-tenant", headers=b).status_code == 200
    assert client.get("/reels/mt-del-guest-reel").status_code == 200


def test_me_data_delete_guest_is_401():
    r = client.delete("/me/data")
    assert r.status_code == 401


def test_me_data_delete_is_idempotent_on_an_empty_tenant(bearer_for):
    headers = bearer_for("mt-tenant-del-empty")
    r = client.delete("/me/data", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"deleted": 0}
    # A second call is still a clean 200/0 — never errors on "nothing to delete".
    r2 = client.delete("/me/data", headers=headers)
    assert r2.status_code == 200
    assert r2.json() == {"deleted": 0}


# ── async job submit + poll, tenant-scoped ────────────────────────────────────


def _poll_until_terminal(headers: dict, job_id: str, *, timeout: float = 5.0) -> dict:
    from cinemory import jobs as jobs_module

    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        r = client.get(f"/reels/jobs/{job_id}", headers=headers)
        if r.status_code == 200:
            body = r.json()
            if body.get("status") in jobs_module.TERMINAL_STATUSES:
                return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach a terminal status within {timeout}s")


def test_tenant_job_submit_and_poll_end_to_end(bearer_for):
    headers = bearer_for("mt-tenant-job")
    photos = [{"filename": "p.png", "content_base64": _b64(b"mt-job-pixels")}]
    r = client.post("/reels/jobs", json={"name": "mt-job-reel", "photos": photos},
                    headers=headers)
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    status = _poll_until_terminal(headers, job_id)
    assert status["status"] == "done"
    assert status["result"]["reel_name"] == "mt-job-reel"

    # The reel really landed under this tenant's storage.
    assert client.get("/reels/mt-job-reel", headers=headers).status_code == 200


def test_other_tenant_and_guest_cannot_poll_a_known_job_id(bearer_for):
    """Even knowing the (unguessable, but suppose leaked) job id, polling it
    under a DIFFERENT verified tenant resolves to nothing — the job status
    object lives under the submitting tenant's own prefix."""
    owner = bearer_for("mt-tenant-job-owner")
    other = bearer_for("mt-tenant-job-other")
    photos = [{"filename": "p.png", "content_base64": _b64(b"mt-job-owner-pixels")}]
    r = client.post("/reels/jobs", json={"name": "mt-job-owned", "photos": photos},
                    headers=owner)
    job_id = r.json()["job_id"]
    _poll_until_terminal(owner, job_id)

    assert client.get(f"/reels/jobs/{job_id}", headers=other).status_code == 404
    assert client.get(f"/reels/jobs/{job_id}").status_code == 404  # guest


# ── FIREBASE_PROJECT_ID unset: proves the additive default ───────────────────


def test_project_id_unset_treats_a_bearer_header_as_guest(bearer_for, monkeypatch):
    """The critical additive-default proof: even a WELL-FORMED, validly-signed
    bearer token is ignored (not 401'd, not honoured) when this deployment has
    no FIREBASE_PROJECT_ID configured — multitenancy is off, full stop."""
    headers = bearer_for("mt-tenant-should-be-ignored")
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)

    r = client.post("/reels", json={"name": "mt-project-off", "chapters": 1,
                                    "per_chapter": 1}, headers=headers)
    assert r.status_code == 200  # not 401 — the header was never even inspected

    # Stored as a GUEST reel: fetchable with NO header at all.
    fetched = client.get("/reels/mt-project-off")
    assert fetched.status_code == 200
    assert fetched.json()["reel_name"] == "mt-project-off"

    # And it is NOT namespaced under any tenant prefix.
    assert not any(row["key"].startswith("tenants/") and "mt-project-off" in row["key"]
                  for row in api._storage.index)


# ── spoofing resistance: only the verified token can set the tenant ─────────


def test_tenant_cannot_be_spoofed_via_query_param_header_or_body(bearer_for):
    a = bearer_for("mt-tenant-spoof-victim")
    client.post("/reels", json={"name": "mt-spoof-target", "chapters": 1,
                                "per_chapter": 1}, headers=a)

    # An UNAUTHENTICATED caller tries every non-token channel to claim tenant A.
    attempts = [
        client.get("/reels/mt-spoof-target?tenant=mt-tenant-spoof-victim"),
        client.get("/reels/mt-spoof-target",
                   headers={"X-Tenant": "mt-tenant-spoof-victim"}),
        client.get("/me/library?tenant=mt-tenant-spoof-victim"),
        client.get("/me/library", headers={"X-Tenant": "mt-tenant-spoof-victim"}),
    ]
    # Every one of these still resolves as GUEST: the reel lookup 404s (guest
    # cannot see a tenant-scoped reel) and /me/library still demands real auth.
    assert attempts[0].status_code == 404
    assert attempts[1].status_code == 404
    assert attempts[2].status_code == 401
    assert attempts[3].status_code == 401

    # A body field named "tenant" on a POST is silently ignored by Pydantic
    # (extra fields are dropped) — the reel is still created as GUEST, not
    # attributed to the claimed tenant.
    r = client.post("/reels", json={"name": "mt-spoof-body", "chapters": 1,
                                    "per_chapter": 1, "tenant": "mt-tenant-spoof-victim"})
    assert r.status_code == 200
    assert not any(row["key"].startswith("tenants/") and "mt-spoof-body" in row["key"]
                  for row in api._storage.index)


def test_authed_caller_cannot_override_their_own_tenant_via_spoofing(bearer_for):
    """A DIFFERENT, more dangerous shape of the same attack: tenant B is
    authenticated (valid token) but tries to reach into tenant A's data via a
    query param / header / body field. The verified token wins every time."""
    a = bearer_for("mt-tenant-spoof-a")
    b = bearer_for("mt-tenant-spoof-b")
    client.post("/reels", json={"name": "mt-spoof-a-reel", "chapters": 1,
                                "per_chapter": 1}, headers=a)

    r1 = client.get("/reels/mt-spoof-a-reel?tenant=mt-tenant-spoof-a", headers=b)
    r2 = client.get("/reels/mt-spoof-a-reel", headers={**b, "X-Tenant": "mt-tenant-spoof-a"})
    assert r1.status_code == 404  # still resolves as tenant B, not A
    assert r2.status_code == 404

    lib = client.get("/me/library?tenant=mt-tenant-spoof-a", headers=b).json()
    assert lib["reels"] == []  # B's own (empty) library, never A's


# ── forged/invalid credentials -> 401, never a silent guest downgrade ────────


def test_garbage_bearer_token_is_401_not_guest():
    r = client.get("/me/library", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert r.status_code == 401


def test_expired_token_is_401(bearer_for):
    headers = bearer_for("mt-tenant-expired",
                         iat=int(time.time()) - 7200, exp=int(time.time()) - 3600)
    r = client.get("/me/library", headers=headers)
    assert r.status_code == 401


def test_token_signed_by_a_different_key_is_401(bearer_for):
    """The classic forged-token shape: the attacker's own (unrelated) private
    key signs a token that CLAIMS the legitimate ``kid``. ``key_source``
    resolves the real public cert for that kid, so the signature check fails
    even though the kid lookup itself succeeds — ``bearer_for`` wires
    ``FIREBASE_PROJECT_ID`` + the real key_source seam this depends on."""
    attacker_private, _attacker_cert = _generate_keypair_and_cert()
    forged = _token_for("mt-tenant-forger", attacker_private)
    assert jwt.get_unverified_header(forged)["kid"] == KID  # claims the real kid
    r = client.get("/me/library", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


# ── direct construction: the isolation-core wrapper's own contract ──────────


def test_tenant_scoped_storage_prefixes_every_operation():
    base = FakeStorage()
    wrapper = api._TenantScopedStorage(base, "tenants/mt-direct/")
    url = wrapper.put("a/b.txt", b"payload", content_type="text/plain")
    assert base.get("tenants/mt-direct/a/b.txt") == b"payload"
    assert wrapper.get("a/b.txt") == b"payload"
    assert wrapper.exists("a/b.txt") is True
    assert base.exists("a/b.txt") is False  # unprefixed key never touched
    assert "tenants/mt-direct/a/b.txt" in url


def test_tenant_scoped_storage_index_is_filtered_and_stripped():
    base = FakeStorage()
    base.put("tenants/mt-x/foo/reels/ab/abcd/reel.mp4", b"1")
    base.put("tenants/mt-y/bar/reels/cd/cdef/reel.mp4", b"2")
    base.put("guest-reel/reels/ef/efgh/reel.mp4", b"3")

    wrapper = api._TenantScopedStorage(base, "tenants/mt-x/")
    assert wrapper.index == [
        {"key": "foo/reels/ab/abcd/reel.mp4", "size": 1, "content_type": "application/octet-stream"}
    ]


def test_tenant_scoped_storage_get_url_exposed_only_when_base_has_it():
    class _NoGetUrl:
        def put(self, key, data, *, content_type="application/octet-stream"):
            return key

        def get(self, key):
            return b""

        def exists(self, key):
            return False

    assert not hasattr(api._TenantScopedStorage(_NoGetUrl(), "tenants/x/"), "get_url")

    class _WithGetUrl(_NoGetUrl):
        def get_url(self, key, *, expires_in=3600):
            return f"https://example.test/{key}?exp={expires_in}"

    wrapper = api._TenantScopedStorage(_WithGetUrl(), "tenants/mt-z/")
    assert hasattr(wrapper, "get_url")
    assert wrapper.get_url("v.mp4") == "https://example.test/tenants/mt-z/v.mp4?exp=3600"


def test_tenant_scoped_storage_delete_exposed_only_when_base_has_it():
    class _NoDelete:
        def put(self, key, data, *, content_type="application/octet-stream"):
            return key

        def get(self, key):
            return b""

        def exists(self, key):
            return False

    assert not hasattr(api._TenantScopedStorage(_NoDelete(), "tenants/x/"), "delete")

    # FakeStorage has delete (added for multitenancy) -> exposed and prefixed.
    base = FakeStorage()
    base.put("tenants/mt-w/r/reels/aa/bb/reel.mp4", b"x")
    wrapper = api._TenantScopedStorage(base, "tenants/mt-w/")
    wrapper.delete("r/reels/aa/bb/reel.mp4")
    assert base.exists("tenants/mt-w/r/reels/aa/bb/reel.mp4") is False


def test_tenant_scoped_storage_reload_index_is_always_safe():
    base = FakeStorage()  # no reload_index of its own
    assert not hasattr(base, "reload_index")
    wrapper = api._TenantScopedStorage(base, "tenants/mt-v/")
    assert wrapper.reload_index() == []  # no-op, never raises


def test_tenant_scoped_storage_reload_index_delegates_when_base_has_one():
    """The B2Storage-shaped case: when the base DOES expose ``reload_index``
    (query-time freshness against the durable bucket index), the wrapper
    really calls it, not just skips it — mirrors the ``FakeStorage`` case
    above (which proves the absent-case no-op) from the other side."""
    calls = []

    class _WithReload:
        def __init__(self) -> None:
            self.index: list[dict] = []

        def reload_index(self) -> list[dict]:
            calls.append(1)
            self.index = [{"key": "tenants/mt-r/reloaded/reels/a/b/reel.mp4",
                          "size": 1, "content_type": "video/mp4"}]
            return self.index

    wrapper = api._TenantScopedStorage(_WithReload(), "tenants/mt-r/")
    result = wrapper.reload_index()
    assert calls == [1]
    assert result == [{"key": "reloaded/reels/a/b/reel.mp4",
                       "size": 1, "content_type": "video/mp4"}]


def test_tenant_prefix_sanitises_a_hostile_uid():
    """Defence in depth: even though a Firebase uid is never attacker-chosen,
    ``_tenant_prefix`` still runs it through ``safe_component`` — a uid that
    somehow contained a path separator could never escape ``tenants/``."""
    assert api._tenant_prefix("normal-uid-123") == "tenants/normal-uid-123/"
    assert api._tenant_prefix("../../etc/passwd") == "tenants/passwd/"


# ── get_url present branch: authed tenant playback 302s with the prefixed key ─


class _PresigningStorage:
    """Minimal live-shaped backend: durable index + a ``get_url`` presigner —
    mirrors ``tests/integration/test_api_video.py``'s guest-path double, here
    used to exercise the AUTHED branch of ``_TenantScopedStorage``."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self.index: list[dict] = []
        self.signed: list[str] = []

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream"):
        self._objects[key] = data
        self.index.append({"key": key, "size": len(data), "content_type": content_type})
        return f"https://bucket.example/{key}"

    def get(self, key: str) -> bytes:
        return self._objects[key]

    def exists(self, key: str) -> bool:
        return key in self._objects

    def get_url(self, key: str, *, expires_in: int = 3600) -> str:
        self.signed.append(key)
        return f"https://bucket.example/{key}?X-Amz-Expires={expires_in}&sig={len(self.signed)}"


def test_authed_tenant_video_redirects_to_a_presigned_url_under_the_tenant_prefix(
    bearer_for, monkeypatch
):
    storage = _PresigningStorage()
    monkeypatch.setattr(api, "_storage", storage)
    headers = bearer_for("mt-tenant-presign")
    prefix = api._tenant_prefix("mt-tenant-presign")
    key = "livereel/reels/ab/" + "a" * 64 + "/reel.mp4"
    storage.put(f"{prefix}{key}", b"real-video-bytes", content_type="video/mp4")

    r = client.get("/reels/livereel/video", headers=headers, follow_redirects=False)
    assert r.status_code == 302
    location = r.headers["location"]
    # The PREFIXED key was signed — never the bare tenant-relative key.
    assert location.startswith(f"https://bucket.example/{prefix}{key}?")
    assert storage.signed == [f"{prefix}{key}"]

    # A guest (or a different tenant) still gets a clean 404, not a signed
    # guess at someone else's object.
    assert client.get("/reels/livereel/video").status_code == 404

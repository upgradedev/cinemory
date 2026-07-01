from fastapi.testclient import TestClient

from cinemory.api import app

client = TestClient(app)


def test_health_reports_offline_mode():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] == "offline"


def test_create_reel_returns_provenance():
    r = client.post("/reels", json={"name": "apitest", "chapters": 2, "per_chapter": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["reel_name"] == "apitest"
    assert len(body["reel_sha256"]) == 64
    assert body["manifest_hash"]
    assert body["steps"] == 4


def test_get_reel_returns_verifiable_manifest():
    client.post("/reels", json={"name": "fetchme", "chapters": 2, "per_chapter": 1})
    r = client.get("/reels/fetchme")
    assert r.status_code == 200
    manifest = r.json()
    assert manifest["reel_name"] == "fetchme"
    assert manifest["manifest_hash"]


def test_get_unknown_reel_is_404():
    assert client.get("/reels/does-not-exist").status_code == 404

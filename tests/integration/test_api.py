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


def test_list_occasions():
    r = client.get("/occasions")
    assert r.status_code == 200
    keys = {o["key"] for o in r.json()["occasions"]}
    assert {"anniversary", "graduation", "birthday", "wedding",
            "year-in-review", "business-event"}.issubset(keys)


def test_create_reel_with_occasion_is_sealed_in_manifest():
    r = client.post("/reels", json={"name": "gradreel", "chapters": 2,
                                    "per_chapter": 1, "occasion": "graduation"})
    assert r.status_code == 200
    assert r.json()["occasion"] == "graduation"
    manifest = client.get("/reels/gradreel").json()
    assert manifest["occasion"] == "graduation"
    # The occasion's full creative direction is sealed into the manifest, and
    # pacing/music ride on each generative step's params.
    style = manifest["occasion_style"]
    assert style["title_style"] and style["transition"] and style["music_style"]
    clip_step = next(s for s in manifest["steps"] if s["params"].get("chapter"))
    assert clip_step["params"]["target_seconds"] == style["seconds_per_clip"]
    assert clip_step["params"]["music_style"] == style["music_style"]

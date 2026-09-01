from __future__ import annotations

from fastapi.testclient import TestClient

from engram import vector_store
from engram.api import app


def test_api_memory_lifecycle(tmp_path, monkeypatch):
    db_path = tmp_path / "api.sqlite3"
    monkeypatch.setenv("ENGRAM_DB", str(db_path))
    monkeypatch.setattr(vector_store, "upsert_engram", lambda *args, **kwargs: False)
    monkeypatch.setattr(vector_store, "search", lambda *args, **kwargs: [])
    monkeypatch.setattr(vector_store, "is_available", lambda: False)

    client = TestClient(app)

    assert client.post("/init").json()["status"] == "initialized"
    session = client.post("/sessions", json={"project": "API", "title": "Lifecycle"}).json()
    user_turn = client.post(
        "/turns",
        json={"session_id": session["id"], "role": "user", "content": "Remember compact icon buttons."},
    ).json()
    assistant_turn = client.post(
        "/turns",
        json={
            "session_id": session["id"],
            "role": "assistant",
            "phase": "final",
            "content": "Stored as a durable UI preference.",
        },
    ).json()
    engram = client.post(
        "/engrams",
        json={
            "session_id": session["id"],
            "source_turn_start": user_turn["id"],
            "source_turn_end": assistant_turn["id"],
            "kind": "preference",
            "title": "Prefer compact icon buttons",
            "summary": "Prefer compact icon buttons for toolbar controls.",
            "durable": "high",
            "tags": ["ui", "buttons"],
        },
    ).json()

    recall = client.get("/recall", params={"query": "toolbar button", "mode": "fts"}).json()
    shown = client.get(f"/engrams/{engram['id']}", params={"transcript": "true"}).json()

    assert recall["mode"] == "fts"
    assert recall["engrams"][0]["id"] == engram["id"]
    assert shown["transcript"][0]["id"] == user_turn["id"]


def test_api_checkpoint_and_reindex_routes(tmp_path, monkeypatch):
    db_path = tmp_path / "api.sqlite3"
    monkeypatch.setenv("ENGRAM_DB", str(db_path))
    monkeypatch.setattr(vector_store, "upsert_engram", lambda *args, **kwargs: False)
    monkeypatch.setattr(vector_store, "is_available", lambda: False)

    client = TestClient(app)

    checkpoint = client.post(
        "/checkpoints",
        json={"project": "Engram", "summary": "Hybrid recall exists.", "active_topics": ["hybrid"]},
    ).json()
    fetched = client.get("/checkpoints/Engram").json()
    reindex = client.post("/vectors/reindex").json()

    assert checkpoint["project"] == "Engram"
    assert fetched["summary"] == "Hybrid recall exists."
    assert fetched["active_topics"] == ["hybrid"]
    assert reindex["vector_available"] is False


def test_api_import_transcript(tmp_path, monkeypatch):
    db_path = tmp_path / "api.sqlite3"
    transcript = tmp_path / "chat.txt"
    transcript.write_text("User: Capture old work context.\nAssistant: Imported successfully.\n", encoding="utf-8")
    monkeypatch.setenv("ENGRAM_DB", str(db_path))

    client = TestClient(app)
    imported = client.post(
        "/imports/transcript",
        json={"path": str(transcript), "project": "API", "title": "Import"},
    ).json()

    assert imported["turn_count"] == 2
    assert imported["pending_consolidation"] is True

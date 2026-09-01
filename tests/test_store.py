from __future__ import annotations

import sqlite3

from engram import store, vector_store


def test_session_turn_capture_and_transcript_span(db_path, no_vectors):
    store.init_db(db_path)
    session = store.start_session("Test Project", "Capture flow", db_path=db_path)

    user_turn = store.capture_turn(session["id"], "user", "Please add a compact icon button.", db_path=db_path)
    assistant_turn = store.capture_turn(
        session["id"],
        "assistant",
        "Done with the existing toolbar style.",
        phase="final",
        db_path=db_path,
    )

    span = store.transcript_span(user_turn["id"], assistant_turn["id"], db_path=db_path)

    assert [turn["role"] for turn in span] == ["user", "assistant"]
    assert span[0]["content"] == "Please add a compact icon button."
    assert store.pending(db_path)[0]["id"] == session["id"]

    result = store.mark_consolidated(session["id"], db_path)
    assert result["last_consolidated_turn_id"] == assistant_turn["id"]
    assert store.pending(db_path) == []


def test_remember_recall_show_and_search_turns(db_path, no_vectors):
    session = store.start_session("Test Project", "Buttons", db_path=db_path)
    first = store.capture_turn(session["id"], "user", "We prefer icon toolbar controls.", db_path=db_path)
    last = store.capture_turn(session["id"], "assistant", "I will remember the toolbar preference.", db_path=db_path)

    memory = store.remember(
        title="Prefer icon-first toolbar controls",
        summary="Toolbar controls should prefer recognizable icons and restrained styling.",
        body="Use tooltips for icon-only controls and follow the existing design system.",
        kind="preference",
        continuity="low",
        durable="high",
        importance=5,
        session_id=session["id"],
        source_turn_start=first["id"],
        source_turn_end=last["id"],
        tags=["ui", "buttons", "toolbar"],
        files=["frontend/src/Toolbar.vue"],
        db_path=db_path,
    )

    recalled = store.recall("toolbar button", include_body=True, db_path=db_path, mode="fts")
    shown = store.show_engram(memory["id"], include_transcript=True, db_path=db_path)
    turns = store.search_turns("icon toolbar", db_path=db_path)

    assert recalled[0]["id"] == memory["id"]
    assert recalled[0]["durable"] == "high"
    assert recalled[0]["tags"] == ["buttons", "toolbar", "ui"]
    assert shown["transcript"][0]["id"] == first["id"]
    assert turns[0]["content"] == "We prefer icon toolbar controls."


def test_vector_recall_uses_chroma_results_when_fts_would_not_match(db_path, monkeypatch):
    monkeypatch.setattr(vector_store, "upsert_engram", lambda *args, **kwargs: True)
    indexed_ids: list[int] = []

    memory = store.remember(
        title="Prefer icon-first toolbar controls",
        summary="Toolbar controls should prefer recognizable icons and restrained styling.",
        body="Use tooltips for icon-only controls.",
        kind="preference",
        durable="high",
        db_path=db_path,
    )
    indexed_ids.append(memory["id"])
    monkeypatch.setattr(vector_store, "search", lambda query, limit=8: [(indexed_ids[0], 0.91)])

    assert store.recall("visual affordance", db_path=db_path, mode="fts") == []
    vector_results = store.recall("visual affordance", db_path=db_path, mode="vector")
    hybrid_results = store.recall("visual affordance", db_path=db_path, mode="hybrid")

    assert vector_results[0]["id"] == memory["id"]
    assert hybrid_results[0]["id"] == memory["id"]


def test_superseding_memory_retires_old_memory_and_deletes_vector(db_path, monkeypatch):
    deleted: list[int] = []
    monkeypatch.setattr(vector_store, "upsert_engram", lambda *args, **kwargs: True)
    monkeypatch.setattr(vector_store, "delete_engram", lambda engram_id: deleted.append(engram_id) or True)

    old = store.remember("Old button rule", "Use large text buttons.", db_path=db_path)
    new = store.remember(
        "New button rule",
        "Use compact icon buttons.",
        supersedes_id=old["id"],
        db_path=db_path,
    )

    with sqlite3.connect(db_path) as conn:
        old_status = conn.execute("SELECT status FROM engrams WHERE id = ?", (old["id"],)).fetchone()[0]

    assert new["id"] != old["id"]
    assert old_status == "superseded"
    assert deleted == [old["id"]]
    recalled_ids = [row["id"] for row in store.recall("large text buttons", db_path=db_path, mode="fts")]
    assert old["id"] not in recalled_ids
    assert new["id"] in recalled_ids


def test_checkpoint_replaces_active_checkpoint_for_project(db_path, no_vectors):
    first = store.save_checkpoint("Engram", "Initial summary", ["first"], db_path=db_path)
    second = store.save_checkpoint("Engram", "Updated summary", ["second"], db_path=db_path)
    active = store.get_checkpoint("Engram", db_path=db_path)

    assert first["id"] != second["id"]
    assert active["summary"] == "Updated summary"
    assert active["active_topics"] == ["second"]

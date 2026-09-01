from __future__ import annotations

import asyncio

from engram import vector_store
from engram import mcp_server


def test_mcp_server_registers_expected_tools():
    tool_names = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}

    assert {
        "recall_memory",
        "show_memory",
        "search_transcript",
        "start_memory_session",
        "ensure_memory_session",
        "capture_memory_turn",
        "remember_memory",
        "pending_consolidation",
        "propose_memories",
        "mark_session_consolidated",
        "save_project_checkpoint",
        "get_project_checkpoint",
        "reindex_vector_memory",
        "import_transcript_file",
    }.issubset(tool_names)


def test_mcp_memory_lifecycle(tmp_path, monkeypatch):
    db_path = tmp_path / "mcp.sqlite3"
    monkeypatch.setenv("ENGRAM_DB", str(db_path))
    monkeypatch.setattr(vector_store, "upsert_engram", lambda *args, **kwargs: False)
    monkeypatch.setattr(vector_store, "search", lambda *args, **kwargs: [])
    monkeypatch.setattr(vector_store, "is_available", lambda: False)

    session = mcp_server.start_memory_session("MCP", "Lifecycle")
    first = mcp_server.capture_memory_turn(
        session_id=session["id"],
        role="user",
        content="Remember that toolbar controls should use compact icons.",
    )
    last = mcp_server.capture_memory_turn(
        session_id=session["id"],
        role="assistant",
        phase="final",
        content="Stored the icon-control preference.",
    )
    memory = mcp_server.remember_memory(
        title="Prefer compact icon controls",
        summary="Toolbar controls should use compact recognizable icons.",
        durable="high",
        session_id=session["id"],
        source_turn_start=first["id"],
        source_turn_end=last["id"],
        tags=["ui", "toolbar"],
    )

    recalled = mcp_server.recall_memory("toolbar controls", mode="fts")
    shown = mcp_server.show_memory(memory["id"], transcript=True)
    pending = mcp_server.pending_consolidation()
    consolidated = mcp_server.mark_session_consolidated(session["id"])

    assert recalled["engrams"][0]["id"] == memory["id"]
    assert shown["transcript"][0]["id"] == first["id"]
    assert pending["sessions"][0]["id"] == session["id"]
    assert consolidated["last_consolidated_turn_id"] == last["id"]


def test_mcp_ensure_session_and_propose_memories(tmp_path, monkeypatch):
    db_path = tmp_path / "mcp.sqlite3"
    monkeypatch.setenv("ENGRAM_DB", str(db_path))
    monkeypatch.setattr(vector_store, "upsert_engram", lambda *args, **kwargs: False)

    first = mcp_server.ensure_memory_session("MCP", "Sticky")
    second = mcp_server.ensure_memory_session("MCP", "Sticky")
    turn = mcp_server.capture_memory_turn(
        session_id=first["id"],
        role="user",
        content="We prefer MCP tools for Claude integration instead of ad hoc curl.",
    )
    proposed = mcp_server.propose_memories(first["id"])

    assert first["created"] is True
    assert second["created"] is False
    assert second["id"] == first["id"]
    assert proposed["candidates"][0]["source_turn_start"] == turn["id"]
    assert proposed["candidates"][0]["kind"] == "preference"
    assert "mcp" in proposed["candidates"][0]["tags"]


def test_mcp_checkpoint_tools(tmp_path, monkeypatch):
    db_path = tmp_path / "mcp.sqlite3"
    monkeypatch.setenv("ENGRAM_DB", str(db_path))

    saved = mcp_server.save_project_checkpoint("Engram", "MCP wrapper added.", ["mcp"])
    fetched = mcp_server.get_project_checkpoint("Engram")

    assert saved["project"] == "Engram"
    assert fetched["summary"] == "MCP wrapper added."
    assert fetched["active_topics"] == ["mcp"]


def test_mcp_import_transcript_file(tmp_path, monkeypatch):
    db_path = tmp_path / "mcp.sqlite3"
    transcript = tmp_path / "chat.md"
    transcript.write_text("# User\nImport this work history.\n\n# Assistant\nDone.\n", encoding="utf-8")
    monkeypatch.setenv("ENGRAM_DB", str(db_path))

    imported = mcp_server.import_transcript_file(str(transcript), "MCP", "Import")

    assert imported["turn_count"] == 2
    assert imported["project"] == "MCP"

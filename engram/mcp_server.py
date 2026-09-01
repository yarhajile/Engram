from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from . import store

MemoryRole = Literal["system", "user", "assistant", "tool", "developer"]
RecallMode = Literal["hybrid", "fts", "vector"]
Retention = Literal["high", "low"]

mcp = FastMCP("Engram")


def database_path() -> Path:
    return Path(os.environ.get("ENGRAM_DB", str(store.DEFAULT_DB)))


@mcp.tool()
def recall_memory(
    query: str,
    limit: int = 8,
    include_body: bool = False,
    mode: RecallMode = "hybrid",
) -> dict[str, Any]:
    """Search Engram's curated memories.

    Use this before substantial work, and use targeted follow-up queries when
    the request mentions UI, buttons, controls, icons, files, architecture,
    prior decisions, bugs, or user preferences.
    """
    return {
        "query": query,
        "mode": mode,
        "engrams": store.recall(query, limit, include_body, database_path(), mode),
    }


@mcp.tool()
def show_memory(engram_id: int, transcript: bool = False, max_chars: int = 4000) -> dict[str, Any]:
    """Show one curated memory, optionally including its raw source transcript span."""
    return store.show_engram(engram_id, transcript, max_chars, database_path())


@mcp.tool()
def search_transcript(query: str, limit: int = 5, max_chars: int = 1200) -> dict[str, Any]:
    """Search raw transcript turns deliberately when curated memories are insufficient."""
    return {
        "query": query,
        "turns": store.search_turns(query, limit, max_chars, database_path()),
    }


@mcp.tool()
def start_memory_session(
    project: str,
    title: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a transcript session for a task or conversation."""
    return store.start_session(project, title, metadata or {}, database_path())


@mcp.tool()
def ensure_memory_session(
    project: str,
    title: str = "",
    metadata: dict[str, Any] | None = None,
    reuse_active: bool = True,
) -> dict[str, Any]:
    """Reuse an active transcript session for a project/title or create one.

    Use this near the start of work so later capture/consolidation calls have
    a stable session id without manually bootstrapping every turn.
    """
    return store.ensure_session(project, title, metadata or {}, reuse_active, database_path())


@mcp.tool()
def capture_memory_turn(
    session_id: int,
    role: MemoryRole,
    content: str,
    phase: str = "active",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a raw transcript turn to a memory session."""
    return store.capture_turn(session_id, role, content, phase, metadata or {}, database_path())


@mcp.tool()
def remember_memory(
    title: str,
    summary: str,
    body: str = "",
    kind: str = "note",
    continuity: Retention = "low",
    durable: Retention = "low",
    importance: int = 3,
    confidence: float = 0.8,
    supersedes_id: int | None = None,
    session_id: int | None = None,
    source_turn_start: int | None = None,
    source_turn_end: int | None = None,
    tags: list[str] | None = None,
    files: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a curated Engram memory.

    Store durable preferences, project decisions, root causes, rejected
    approaches, implementation gotchas, and recurring agent behavior notes.
    Do not store secrets.
    """
    return store.remember(
        title=title,
        summary=summary,
        body=body,
        kind=kind,
        continuity=continuity,
        durable=durable,
        importance=importance,
        confidence=confidence,
        supersedes_id=supersedes_id,
        session_id=session_id,
        source_turn_start=source_turn_start,
        source_turn_end=source_turn_end,
        tags=tags or [],
        files=files or [],
        metadata=metadata or {},
        db_path=database_path(),
    )


@mcp.tool()
def pending_consolidation() -> dict[str, Any]:
    """List sessions with transcript turns that have not been consolidated."""
    return {"sessions": store.pending(database_path())}


@mcp.tool()
def propose_memories(
    session_id: int,
    limit: int = 8,
    max_body_chars: int = 1600,
) -> dict[str, Any]:
    """Suggest candidate curated memories from unconsolidated transcript turns.

    This is a deterministic helper, not an approval step. Review candidates
    and call remember_memory only for durable knowledge worth keeping.
    """
    return store.propose_memories(session_id, limit, max_body_chars, database_path())


@mcp.tool()
def mark_session_consolidated(session_id: int) -> dict[str, Any]:
    """Mark all current turns in a session as consolidated."""
    return store.mark_consolidated(session_id, database_path())


@mcp.tool()
def save_project_checkpoint(
    project: str,
    summary: str,
    active_topics: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save the active checkpoint summary for a project."""
    return store.save_checkpoint(project, summary, active_topics or [], metadata or {}, database_path())


@mcp.tool()
def get_project_checkpoint(project: str) -> dict[str, Any] | None:
    """Get the active checkpoint summary for a project."""
    return store.get_checkpoint(project, database_path())


@mcp.tool()
def reindex_vector_memory() -> dict[str, Any]:
    """Rebuild the optional ChromaDB semantic index from active SQLite memories."""
    return store.reindex_vectors(database_path())


@mcp.tool()
def import_transcript_file(
    path: str,
    project: str,
    title: str = "",
    format: Literal["auto", "jsonl", "json", "markdown", "role-prefix", "claude-code"] = "auto",
    mark_consolidated: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Import a historical transcript file as raw Engram turns.

    Supported formats are JSONL, JSON, Markdown role headings, simple
    role-prefixed plain text, and native Claude Code session JSONL
    (~/.claude/projects/*/*.jsonl — auto-detected). Imported sessions are
    pending consolidation by default so a later curator or agent can create
    durable engrams from them.
    """
    return store.import_transcript(
        path=Path(path),
        project=project,
        title=title,
        fmt=format,
        metadata=metadata or {},
        mark_consolidated_after_import=mark_consolidated,
        db_path=database_path(),
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from . import importer
from . import vector_store

DEFAULT_DB = Path(".engram/engram.sqlite3")
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schema.sql"


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4)) if text else 0


def connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(engrams)")}
    additions = {
        "supersedes_id": "ALTER TABLE engrams ADD COLUMN supersedes_id INTEGER REFERENCES engrams(id) ON DELETE SET NULL",
        "continuity": "ALTER TABLE engrams ADD COLUMN continuity TEXT NOT NULL DEFAULT 'low'",
        "durable": "ALTER TABLE engrams ADD COLUMN durable TEXT NOT NULL DEFAULT 'low'",
    }
    for column, sql in additions.items():
        if column not in existing:
            conn.execute(sql)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_status ON engrams(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_retention ON engrams(continuity, durable)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_engrams_supersedes ON engrams(supersedes_id)")


def init_db(db_path: Path = DEFAULT_DB) -> dict[str, str]:
    with connect(db_path) as conn:
        migrate(conn)
    return {"database": str(db_path), "status": "initialized"}


def normalize_metadata(metadata: dict[str, Any] | str | None) -> str:
    if metadata is None:
        return "{}"
    if isinstance(metadata, str):
        return json.dumps(json.loads(metadata or "{}"), sort_keys=True)
    return json.dumps(metadata, sort_keys=True)


def start_session(
    project: str,
    title: str = "",
    metadata: dict[str, Any] | str | None = None,
    db_path: Path = DEFAULT_DB,
) -> dict[str, Any]:
    with connect(db_path) as conn:
        migrate(conn)
        cur = conn.execute(
            "INSERT INTO sessions(project, title, metadata_json) VALUES (?, ?, ?)",
            (project, title, normalize_metadata(metadata)),
        )
        return {"id": int(cur.lastrowid), "project": project, "title": title}


def ensure_session(
    project: str,
    title: str = "",
    metadata: dict[str, Any] | str | None = None,
    reuse_active: bool = True,
    db_path: Path = DEFAULT_DB,
) -> dict[str, Any]:
    with connect(db_path) as conn:
        migrate(conn)
        if reuse_active:
            row = conn.execute(
                "SELECT * FROM sessions WHERE project = ? AND title = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
                (project, title),
            ).fetchone()
            if row is not None:
                return {"id": int(row["id"]), "project": row["project"], "title": row["title"], "created": False}
        cur = conn.execute(
            "INSERT INTO sessions(project, title, metadata_json) VALUES (?, ?, ?)",
            (project, title, normalize_metadata(metadata)),
        )
        return {"id": int(cur.lastrowid), "project": project, "title": title, "created": True}


def sync_turn_fts(conn: sqlite3.Connection, turn_id: int, content: str, role: str, phase: str) -> None:
    conn.execute("DELETE FROM turn_fts WHERE rowid = ?", (turn_id,))
    conn.execute(
        "INSERT INTO turn_fts(rowid, content, role, phase) VALUES (?, ?, ?, ?)",
        (turn_id, content, role, phase),
    )


def capture_turn(
    session_id: int,
    role: str,
    content: str,
    phase: str = "active",
    metadata: dict[str, Any] | str | None = None,
    db_path: Path = DEFAULT_DB,
) -> dict[str, Any]:
    with connect(db_path) as conn:
        migrate(conn)
        cur = conn.execute(
            "INSERT INTO turns(session_id, role, phase, content, token_estimate, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, phase, content, estimate_tokens(content), normalize_metadata(metadata)),
        )
        turn_id = int(cur.lastrowid)
        sync_turn_fts(conn, turn_id, content, role, phase)
        conn.execute(
            "UPDATE sessions SET status = ?, ended_at = CASE WHEN ? IN ('final', 'waiting_on_user') THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now') ELSE ended_at END WHERE id = ?",
            (phase, phase, session_id),
        )
        return {"id": turn_id, "session_id": session_id, "role": role, "phase": phase}


def insert_turn(
    conn: sqlite3.Connection,
    session_id: int,
    role: str,
    content: str,
    phase: str = "active",
    metadata: dict[str, Any] | str | None = None,
    created_at: str | None = None,
) -> int:
    if created_at:
        sql = (
            "INSERT INTO turns(session_id, role, phase, content, token_estimate, created_at, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        values = (session_id, role, phase, content, estimate_tokens(content), created_at, normalize_metadata(metadata))
    else:
        sql = (
            "INSERT INTO turns(session_id, role, phase, content, token_estimate, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        values = (session_id, role, phase, content, estimate_tokens(content), normalize_metadata(metadata))
    cur = conn.execute(sql, values)
    turn_id = int(cur.lastrowid)
    sync_turn_fts(conn, turn_id, content, role, phase)
    return turn_id


def import_transcript(
    path: Path,
    project: str,
    title: str = "",
    fmt: str = "auto",
    metadata: dict[str, Any] | str | None = None,
    mark_consolidated_after_import: bool = False,
    db_path: Path = DEFAULT_DB,
) -> dict[str, Any]:
    turns = importer.parse_transcript(path, fmt)
    if not turns:
        raise ValueError(f"No turns found in transcript: {path}")

    merged_metadata = json.loads(normalize_metadata(metadata))
    merged_metadata.update({"imported_from": str(path), "import_format": fmt})

    with connect(db_path) as conn:
        migrate(conn)
        cur = conn.execute(
            "INSERT INTO sessions(project, title, status, metadata_json) VALUES (?, ?, ?, ?)",
            (project, title or path.stem, "imported", normalize_metadata(merged_metadata)),
        )
        session_id = int(cur.lastrowid)
        turn_ids = [
            insert_turn(
                conn,
                session_id=session_id,
                role=turn["role"],
                phase=turn.get("phase") or "imported",
                content=turn["content"],
                created_at=turn.get("created_at"),
                metadata=turn.get("metadata") or {},
            )
            for turn in turns
        ]
        if mark_consolidated_after_import:
            conn.execute("UPDATE sessions SET last_consolidated_turn_id = ? WHERE id = ?", (turn_ids[-1], session_id))
        return {
            "session_id": session_id,
            "project": project,
            "title": title or path.stem,
            "turn_count": len(turn_ids),
            "first_turn_id": turn_ids[0],
            "last_turn_id": turn_ids[-1],
            "pending_consolidation": not mark_consolidated_after_import,
        }


def sync_engram_fts(conn: sqlite3.Connection, engram_id: int) -> None:
    row = conn.execute("SELECT title, summary, body FROM engrams WHERE id = ?", (engram_id,)).fetchone()
    if row is None:
        return
    tags = " ".join(
        r["tag"] for r in conn.execute("SELECT tag FROM engram_tags WHERE engram_id = ? ORDER BY tag", (engram_id,))
    )
    files = " ".join(
        r["path"] for r in conn.execute("SELECT path FROM engram_files WHERE engram_id = ? ORDER BY path", (engram_id,))
    )
    conn.execute("DELETE FROM engram_fts WHERE rowid = ?", (engram_id,))
    conn.execute(
        "INSERT INTO engram_fts(rowid, title, summary, body, tags_text, files_text) VALUES (?, ?, ?, ?, ?, ?)",
        (engram_id, row["title"], row["summary"], row["body"], tags, files),
    )


def remember(
    title: str,
    summary: str,
    body: str = "",
    kind: str = "note",
    continuity: str = "low",
    durable: str = "low",
    importance: int = 3,
    confidence: float = 0.8,
    supersedes_id: int | None = None,
    session_id: int | None = None,
    source_turn_start: int | None = None,
    source_turn_end: int | None = None,
    tags: list[str] | None = None,
    files: list[str] | None = None,
    metadata: dict[str, Any] | str | None = None,
    db_path: Path = DEFAULT_DB,
) -> dict[str, Any]:
    with connect(db_path) as conn:
        migrate(conn)
        cur = conn.execute(
            "INSERT INTO engrams(session_id, source_turn_start, source_turn_end, supersedes_id, kind, title, summary, body, continuity, durable, importance, confidence, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                source_turn_start,
                source_turn_end,
                supersedes_id,
                kind,
                title,
                summary,
                body,
                normalize_retention(continuity),
                normalize_retention(durable),
                importance,
                confidence,
                normalize_metadata(metadata),
            ),
        )
        engram_id = int(cur.lastrowid)
        if supersedes_id:
            conn.execute(
                "UPDATE engrams SET status = 'superseded', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
                (supersedes_id,),
            )
        for tag in tags or []:
            conn.execute("INSERT OR IGNORE INTO engram_tags(engram_id, tag) VALUES (?, ?)", (engram_id, tag.strip()))
        for file_path in files or []:
            conn.execute(
                "INSERT OR IGNORE INTO engram_files(engram_id, path) VALUES (?, ?)",
                (engram_id, file_path.strip()),
            )
        sync_engram_fts(conn, engram_id)
        row = conn.execute("SELECT * FROM engrams WHERE id = ?", (engram_id,)).fetchone()
        item = engram_dict(conn, row, include_body=True)
    indexed = vector_store.upsert_engram(item)
    if supersedes_id:
        vector_store.delete_engram(supersedes_id)
    return {"id": engram_id, "vector_indexed": indexed}


def normalize_retention(value: str) -> str:
    return "high" if value.lower() == "high" else "low"


def fts_query(query: str) -> str:
    terms = [
        term for term in re.findall(r"[A-Za-z0-9_./:-]+", query)
        if len(term.strip("._/:-")) > 2
    ]
    return " OR ".join(f'"{term}"' for term in terms[:16]) if terms else '""'


def engram_dict(conn: sqlite3.Connection, row: sqlite3.Row, include_body: bool = True) -> dict[str, Any]:
    data = {k: row[k] for k in row.keys() if k != "rank"}
    if not include_body:
        data.pop("body", None)
    data["tags"] = [
        r["tag"] for r in conn.execute("SELECT tag FROM engram_tags WHERE engram_id = ? ORDER BY tag", (row["id"],))
    ]
    data["files"] = [
        r["path"] for r in conn.execute("SELECT path FROM engram_files WHERE engram_id = ? ORDER BY path", (row["id"],))
    ]
    return data


def recall(
    query: str,
    limit: int = 8,
    include_body: bool = False,
    db_path: Path = DEFAULT_DB,
    mode: str = "hybrid",
) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        migrate(conn)
        scores: dict[int, float] = {}
        if mode in {"hybrid", "fts"}:
            rows = conn.execute(
                "SELECT e.id, bm25(engram_fts) AS rank FROM engram_fts JOIN engrams e ON e.id = engram_fts.rowid WHERE engram_fts MATCH ? AND e.status = 'active' ORDER BY rank, e.importance DESC, e.updated_at DESC LIMIT ?",
                (fts_query(query), limit * 2),
            ).fetchall()
            for row in rows:
                scores[int(row["id"])] = scores.get(int(row["id"]), 0.0) + 1.0 + min(abs(float(row["rank"])), 10.0) / 10.0
        if mode in {"hybrid", "vector"}:
            for engram_id, similarity in vector_store.search(query, limit * 2):
                scores[engram_id] = scores.get(engram_id, 0.0) + 1.0 + similarity

        if not scores:
            return []

        placeholders = ",".join("?" for _ in scores)
        rows = conn.execute(
            f"SELECT * FROM engrams WHERE id IN ({placeholders}) AND status = 'active'",
            tuple(scores),
        ).fetchall()
        ranked_rows = sorted(
            rows,
            key=lambda row: (
                scores[int(row["id"])] + retention_boost(row) + (float(row["importance"]) / 10.0),
                row["updated_at"],
            ),
            reverse=True,
        )[:limit]
        try:
            for row in ranked_rows:
                conn.execute(
                    "UPDATE engrams SET last_accessed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), access_count = access_count + 1 WHERE id = ?",
                    (row["id"],),
                )
        except sqlite3.OperationalError as exc:
            if "readonly" not in str(exc).lower():
                raise
        return [engram_dict(conn, row, include_body=include_body) for row in ranked_rows]


def retention_boost(row: sqlite3.Row) -> float:
    score = 0.0
    if row["continuity"] == "high":
        score += 0.3
    if row["durable"] == "high":
        score += 0.2
    return score


def show_engram(
    engram_id: int,
    include_transcript: bool = False,
    max_chars: int = 4000,
    db_path: Path = DEFAULT_DB,
) -> dict[str, Any]:
    with connect(db_path) as conn:
        migrate(conn)
        row = conn.execute("SELECT * FROM engrams WHERE id = ?", (engram_id,)).fetchone()
        if row is None:
            raise KeyError(f"No engram with id {engram_id}")
        item = engram_dict(conn, row, include_body=True)
        if include_transcript:
            item["transcript"] = transcript_span(row["source_turn_start"], row["source_turn_end"], max_chars, conn)
        return item


def transcript_span(
    start: int | None,
    end: int | None,
    max_chars: int = 4000,
    conn: sqlite3.Connection | None = None,
    db_path: Path = DEFAULT_DB,
) -> list[dict[str, Any]]:
    if not start or not end:
        return []
    owns_conn = conn is None
    conn = conn or connect(db_path)
    try:
        migrate(conn)
        turns = []
        for row in conn.execute("SELECT id, session_id, role, phase, content, created_at FROM turns WHERE id BETWEEN ? AND ? ORDER BY id", (start, end)):
            content = row["content"]
            if len(content) > max_chars:
                content = content[:max_chars] + "\n[truncated]"
            turns.append({**dict(row), "content": content})
        return turns
    finally:
        if owns_conn:
            conn.close()


def search_turns(query: str, limit: int = 5, max_chars: int = 1200, db_path: Path = DEFAULT_DB) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        migrate(conn)
        rows = conn.execute(
            "SELECT t.*, bm25(turn_fts) AS rank FROM turn_fts JOIN turns t ON t.id = turn_fts.rowid WHERE turn_fts MATCH ? ORDER BY rank, t.id DESC LIMIT ?",
            (fts_query(query), limit),
        ).fetchall()
        turns = []
        for row in rows:
            item = dict(row)
            if len(item["content"]) > max_chars:
                item["content"] = item["content"][:max_chars] + "\n[truncated]"
            item.pop("rank", None)
            turns.append(item)
        return turns


def pending(db_path: Path = DEFAULT_DB) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        migrate(conn)
        rows = conn.execute(
            "SELECT s.*, COALESCE(MAX(t.id), 0) AS latest_turn_id FROM sessions s LEFT JOIN turns t ON t.session_id = s.id GROUP BY s.id HAVING latest_turn_id > COALESCE(s.last_consolidated_turn_id, 0) ORDER BY s.id DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def mark_consolidated(session_id: int, db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    with connect(db_path) as conn:
        migrate(conn)
        latest = conn.execute(
            "SELECT COALESCE(MAX(id), 0) AS latest FROM turns WHERE session_id = ?",
            (session_id,),
        ).fetchone()["latest"]
        conn.execute("UPDATE sessions SET last_consolidated_turn_id = ? WHERE id = ?", (latest, session_id))
        return {"session_id": session_id, "last_consolidated_turn_id": latest}


def propose_memories(
    session_id: int,
    limit: int = 8,
    max_body_chars: int = 1600,
    db_path: Path = DEFAULT_DB,
) -> dict[str, Any]:
    with connect(db_path) as conn:
        migrate(conn)
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if session is None:
            raise KeyError(f"No session with id {session_id}")
        start_after = int(session["last_consolidated_turn_id"] or 0)
        rows = conn.execute(
            "SELECT id, role, phase, content FROM turns WHERE session_id = ? AND id > ? ORDER BY id",
            (session_id, start_after),
        ).fetchall()

    candidates = build_memory_candidates(session_id, rows, limit, max_body_chars)
    return {
        "session_id": session_id,
        "project": session["project"],
        "title": session["title"],
        "last_consolidated_turn_id": start_after,
        "turn_count": len(rows),
        "candidates": candidates,
    }


def build_memory_candidates(
    session_id: int,
    rows: list[sqlite3.Row],
    limit: int,
    max_body_chars: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for span in candidate_spans(rows):
        combined = "\n".join(f"{row['role']}: {row['content'].strip()}" for row in span).strip()
        if not combined:
            continue
        kind, tags, importance = classify_candidate(combined)
        if kind == "note" and len(combined) < 160:
            continue
        first = int(span[0]["id"])
        last = int(span[-1]["id"])
        title = candidate_title(kind, combined)
        body = combined[:max_body_chars].rstrip()
        if len(combined) > max_body_chars:
            body += "\n[truncated]"
        candidates.append(
            {
                "kind": kind,
                "title": title,
                "summary": candidate_summary(combined),
                "body": body,
                "continuity": "high" if kind in {"preference", "decision"} else "low",
                "durable": "high" if kind in {"preference", "decision", "gotcha"} else "low",
                "importance": importance,
                "confidence": 0.55,
                "session_id": session_id,
                "source_turn_start": first,
                "source_turn_end": last,
                "tags": tags,
                "files": sorted(set(re.findall(r"[\w./-]+\.\w+", combined)))[:8],
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def candidate_spans(rows: list[sqlite3.Row]) -> list[list[sqlite3.Row]]:
    spans: list[list[sqlite3.Row]] = []
    current: list[sqlite3.Row] = []
    for row in rows:
        if row["role"] == "user" and current:
            spans.append(current)
            current = [row]
        else:
            current.append(row)
    if current:
        spans.append(current)
    return spans


def classify_candidate(text: str) -> tuple[str, list[str], int]:
    lowered = text.lower()
    tags: set[str] = set()
    kind = "note"
    importance = 3

    if re.search(r"\b(prefer|preference|always|should|avoid|don't|do not|instead|style|expectation)\b", lowered):
        kind = "preference"
        importance = 4
    if re.search(r"\b(decided|decision|chose|chosen|settled|use|using|approach|architecture)\b", lowered):
        kind = "decision" if kind == "note" else kind
        importance = max(importance, 4)
    if re.search(r"\b(bug|error|failure|failed|fix|fixed|root cause|regression|gotcha)\b", lowered):
        kind = "gotcha"
        importance = 5
    if re.search(r"\b(todo|next|follow[- ]?up|later|remaining)\b", lowered):
        tags.add("follow-up")

    tag_terms = {
        "ui": r"\b(ui|frontend|layout|button|buttons|toolbar|icon|icons|tooltip|modal|card)\b",
        "api": r"\b(api|endpoint|fastapi|localhost|http|curl)\b",
        "mcp": r"\b(mcp|claude code|tool wrapper)\b",
        "database": r"\b(sqlite|database|db|schema|chroma|chromadb|vector|fts)\b",
        "testing": r"\b(test|tests|pytest|coverage|smoke)\b",
        "import": r"\b(import|transcript|historical|conversation)\b",
        "agent-behavior": r"\b(agent|claude|codex|memory|recall|consolidat)\b",
    }
    for tag, pattern in tag_terms.items():
        if re.search(pattern, lowered):
            tags.add(tag)
    tags.add(kind)
    return kind, sorted(tags), importance


def candidate_title(kind: str, text: str) -> str:
    summary = candidate_summary(text)
    summary = re.sub(r"^(user|assistant|system|developer|tool):\s*", "", summary, flags=re.IGNORECASE)
    return f"Candidate {kind}: {summary[:72]}".rstrip()


def candidate_summary(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= 180:
        return compact
    return compact[:177].rstrip() + "..."


def reindex_vectors(db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    indexed = 0
    skipped = 0
    with connect(db_path) as conn:
        migrate(conn)
        rows = conn.execute("SELECT * FROM engrams WHERE status = 'active' ORDER BY id").fetchall()
        for row in rows:
            item = engram_dict(conn, row, include_body=True)
            if vector_store.upsert_engram(item):
                indexed += 1
            else:
                skipped += 1
    return {"indexed": indexed, "skipped": skipped, "vector_available": vector_store.is_available()}


def save_checkpoint(
    project: str,
    summary: str,
    active_topics: list[str] | None = None,
    metadata: dict[str, Any] | str | None = None,
    db_path: Path = DEFAULT_DB,
) -> dict[str, Any]:
    with connect(db_path) as conn:
        migrate(conn)
        conn.execute("UPDATE checkpoints SET active = 0 WHERE project = ? AND active = 1", (project,))
        cur = conn.execute(
            "INSERT INTO checkpoints(project, summary, active_topics_json, metadata_json) VALUES (?, ?, ?, ?)",
            (project, summary, json.dumps(active_topics or [], sort_keys=True), normalize_metadata(metadata)),
        )
        return {"id": int(cur.lastrowid), "project": project}


def get_checkpoint(project: str, db_path: Path = DEFAULT_DB) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        migrate(conn)
        row = conn.execute(
            "SELECT * FROM checkpoints WHERE project = ? AND active = 1 ORDER BY id DESC LIMIT 1",
            (project,),
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["active_topics"] = json.loads(item.pop("active_topics_json") or "[]")
        return item

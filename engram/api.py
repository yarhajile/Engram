from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import store


def database_path() -> Path:
    return Path(os.environ.get("ENGRAM_DB", str(store.DEFAULT_DB)))


app = FastAPI(
    title="Engram",
    version="0.1.0",
    description="Local SQLite-backed episodic memory for coding agents.",
)


class StartSessionRequest(BaseModel):
    project: str = Field(default="Engram")
    title: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnsureSessionRequest(BaseModel):
    project: str = Field(default="Engram")
    title: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)
    reuse_active: bool = True


class CaptureTurnRequest(BaseModel):
    session_id: int
    role: str
    content: str
    phase: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RememberRequest(BaseModel):
    title: str
    summary: str
    body: str = ""
    kind: str = "note"
    continuity: str = "low"
    durable: str = "low"
    importance: int = Field(default=3, ge=1, le=5)
    confidence: float = Field(default=0.8, ge=0, le=1)
    supersedes_id: int | None = None
    session_id: int | None = None
    source_turn_start: int | None = None
    source_turn_end: int | None = None
    tags: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CheckpointRequest(BaseModel):
    project: str
    summary: str
    active_topics: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImportTranscriptRequest(BaseModel):
    path: str
    project: str
    title: str = ""
    format: str = "auto"
    metadata: dict[str, Any] = Field(default_factory=dict)
    mark_consolidated: bool = False


class ProposeMemoriesRequest(BaseModel):
    session_id: int
    limit: int = Field(default=8, ge=1, le=50)
    max_body_chars: int = Field(default=1600, ge=200, le=20000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "database": str(database_path())}


@app.post("/init")
def init() -> dict[str, str]:
    return store.init_db(database_path())


@app.post("/sessions")
def start_session(request: StartSessionRequest) -> dict[str, Any]:
    return store.start_session(
        project=request.project,
        title=request.title,
        metadata=request.metadata,
        db_path=database_path(),
    )


@app.post("/sessions/ensure")
def ensure_session(request: EnsureSessionRequest) -> dict[str, Any]:
    return store.ensure_session(
        project=request.project,
        title=request.title,
        metadata=request.metadata,
        reuse_active=request.reuse_active,
        db_path=database_path(),
    )


@app.post("/turns")
def capture_turn(request: CaptureTurnRequest) -> dict[str, Any]:
    return store.capture_turn(
        session_id=request.session_id,
        role=request.role,
        phase=request.phase,
        content=request.content,
        metadata=request.metadata,
        db_path=database_path(),
    )


@app.post("/engrams")
def remember(request: RememberRequest) -> dict[str, Any]:
    return store.remember(
        title=request.title,
        summary=request.summary,
        body=request.body,
        kind=request.kind,
        continuity=request.continuity,
        durable=request.durable,
        importance=request.importance,
        confidence=request.confidence,
        supersedes_id=request.supersedes_id,
        session_id=request.session_id,
        source_turn_start=request.source_turn_start,
        source_turn_end=request.source_turn_end,
        tags=request.tags,
        files=request.files,
        metadata=request.metadata,
        db_path=database_path(),
    )


@app.get("/recall")
def recall(query: str, limit: int = 8, include_body: bool = False, mode: str = "hybrid") -> dict[str, Any]:
    return {"query": query, "mode": mode, "engrams": store.recall(query, limit, include_body, database_path(), mode)}


@app.get("/engrams/{engram_id}")
def show_engram(engram_id: int, transcript: bool = False, max_chars: int = 4000) -> dict[str, Any]:
    try:
        return store.show_engram(engram_id, transcript, max_chars, database_path())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/turns/search")
def search_turns(query: str, limit: int = 5, max_chars: int = 1200) -> dict[str, Any]:
    return {"query": query, "turns": store.search_turns(query, limit, max_chars, database_path())}


@app.get("/consolidation/pending")
def pending() -> dict[str, Any]:
    return {"sessions": store.pending(database_path())}


@app.post("/consolidation/propose")
def propose_memories(request: ProposeMemoriesRequest) -> dict[str, Any]:
    try:
        return store.propose_memories(
            session_id=request.session_id,
            limit=request.limit,
            max_body_chars=request.max_body_chars,
            db_path=database_path(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/mark-consolidated")
def mark_consolidated(session_id: int) -> dict[str, Any]:
    return store.mark_consolidated(session_id, database_path())


@app.post("/vectors/reindex")
def reindex_vectors() -> dict[str, Any]:
    return store.reindex_vectors(database_path())


@app.post("/checkpoints")
def save_checkpoint(request: CheckpointRequest) -> dict[str, Any]:
    return store.save_checkpoint(
        project=request.project,
        summary=request.summary,
        active_topics=request.active_topics,
        metadata=request.metadata,
        db_path=database_path(),
    )


@app.get("/checkpoints/{project}")
def get_checkpoint(project: str) -> dict[str, Any] | None:
    return store.get_checkpoint(project, database_path())


@app.post("/imports/transcript")
def import_transcript(request: ImportTranscriptRequest) -> dict[str, Any]:
    try:
        return store.import_transcript(
            path=Path(request.path),
            project=request.project,
            title=request.title,
            fmt=request.format,
            metadata=request.metadata,
            mark_consolidated_after_import=request.mark_consolidated,
            db_path=database_path(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

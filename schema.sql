PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    last_consolidated_turn_id INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool', 'developer')),
    phase TEXT NOT NULL DEFAULT 'active',
    content TEXT NOT NULL,
    token_estimate INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_turns_session_id ON turns(session_id, id);
CREATE INDEX IF NOT EXISTS idx_turns_phase ON turns(phase);

CREATE TABLE IF NOT EXISTS engrams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    source_turn_start INTEGER REFERENCES turns(id) ON DELETE SET NULL,
    source_turn_end INTEGER REFERENCES turns(id) ON DELETE SET NULL,
    supersedes_id INTEGER REFERENCES engrams(id) ON DELETE SET NULL,
    kind TEXT NOT NULL DEFAULT 'note',
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    continuity TEXT NOT NULL DEFAULT 'low' CHECK (continuity IN ('high', 'low')),
    durable TEXT NOT NULL DEFAULT 'low' CHECK (durable IN ('high', 'low')),
    importance INTEGER NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
    confidence REAL NOT NULL DEFAULT 0.8 CHECK (confidence >= 0 AND confidence <= 1),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'retired')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_accessed_at TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS engram_tags (
    engram_id INTEGER NOT NULL REFERENCES engrams(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (engram_id, tag)
);

CREATE TABLE IF NOT EXISTS engram_files (
    engram_id INTEGER NOT NULL REFERENCES engrams(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    PRIMARY KEY (engram_id, path)
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    summary TEXT NOT NULL,
    active_topics_json TEXT NOT NULL DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_project_active ON checkpoints(project, active);

CREATE VIRTUAL TABLE IF NOT EXISTS engram_fts USING fts5(title, summary, body, tags_text, files_text);
CREATE VIRTUAL TABLE IF NOT EXISTS turn_fts USING fts5(content, role, phase);

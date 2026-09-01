# Engram Agent Memory Instructions

Engram is a SQLite-backed external memory layer for coding agents. It stores complete transcripts as append-only evidence and stores distilled memories as compact recall records.

## Core Rule

Use Engram to remember durable project knowledge without growing this instruction file forever.

- Raw transcript turns are evidence, not normal working context.
- Engrams are curated recall records: decisions, preferences, gotchas, architecture notes, file notes, and recurring behavioral expectations.
- SQLite is the source of truth; ChromaDB is an optional derived semantic index.
- Current files and user instructions beat old memory.
- Search distilled engrams first; inspect raw turns only when an engram points to them or the user asks for transcript-level detail.

## Start Of Work

Before substantial work, prefer the Engram MCP tool `recall_memory` if it is available. Query with the user's request using `mode="hybrid"` and `include_body=false` first.

When transcript capture is available, call `ensure_memory_session` near the start of work. Reuse the returned session id for later `capture_memory_turn`, `propose_memories`, and `mark_session_consolidated` calls.

If MCP is unavailable, prefer the localhost API if it is running:

```sh
curl 'http://127.0.0.1:8732/recall?query=<url-encoded-user-request>&limit=8&mode=hybrid'
```

If the service is not running, fall back to the CLI:

```sh
python3 -m engram --db .engram/engram.sqlite3 recall "<user request>" --limit 8
```

If the user mentions a feature, file, UI pattern, prior decision, person, project, or bug, run a second targeted recall with those words.

Load only the relevant summaries/bodies into context. Do not dump the whole database into the prompt.

## During Work

Capture transcript turns when the host environment makes them available. Prefer MCP:

```text
ensure_memory_session
capture_memory_turn
```

API fallback:

```sh
curl -X POST 'http://127.0.0.1:8732/sessions/ensure' -H 'Content-Type: application/json' -d '{"project": "Project Name", "title": "Task title"}'
curl -X POST 'http://127.0.0.1:8732/turns' -H 'Content-Type: application/json' -d '{"session_id": 1, "role": "user", "phase": "active", "content": "..."}'
curl -X POST 'http://127.0.0.1:8732/turns' -H 'Content-Type: application/json' -d '{"session_id": 1, "role": "assistant", "phase": "final", "content": "..."}'
```

CLI fallback:

```sh
python3 -m engram --db .engram/engram.sqlite3 capture-turn --session-id <id> --role user --phase active --content -
python3 -m engram --db .engram/engram.sqlite3 capture-turn --session-id <id> --role assistant --phase final --content -
```

Prefer append-only turn rows over a giant transcript blob. This allows targeted source spans, citation, redaction, and incremental consolidation.

## Consolidation Boundary

After an assistant final response, a waiting-on-user response, a user correction, a design/architecture decision, a bug fix, or a meaningful task phase, create or update engrams for durable knowledge. Good engrams are concise and future-useful.

Preferred MCP flow:

```text
propose_memories(session_id)
remember_memory(...)
mark_session_consolidated(session_id)
```

`propose_memories` suggests candidate source spans. It is not automatic approval. Review candidates and call `remember_memory` only for durable knowledge that should affect future sessions.

After `remember_memory`, the memory is written to SQLite and, when ChromaDB is available, immediately upserted into the semantic index. A manual `reindex_vector_memory` should only be needed after restoring/copying a database, deleting `.engram/chromadb`, installing ChromaDB for the first time, or repairing the vector index.

Capture:

- UI and design preferences.
- Decisions and their rationale.
- Bugs and root causes.
- Project-specific workflows.
- File/module ownership notes.
- User corrections that should change future behavior.
- Imported historical conversations that are relevant to active work.

Avoid saving:

- Secrets, credentials, private keys, and tokens.
- Large raw tool output as an engram body.
- Temporary theories that were later disproven, unless the lesson matters.
- Trivial chat filler.

When memory conflicts, current user instructions override recalled memory, current repository files override recalled memory, and newer specific memories override older general memories. If the conflict matters, mention it and verify before acting.

## Recall Pattern

1. Search engrams.
2. Read top summaries.
3. Load body for highly relevant items.
4. Use `show --transcript` only if the source span is necessary.
5. Verify remembered claims against current files before editing.

Use `mode=hybrid` by default. Use `mode=fts` for exact names/files/tags and `mode=vector` for fuzzy conceptual recall.

## Historical Import

If the user provides a prior transcript file, prefer the MCP tool `import_transcript_file`. Imported sessions are raw evidence and should remain pending consolidation unless the user explicitly asks to mark them consolidated.

After importing a long historical conversation, run targeted recall/search over the imported turns and create curated engrams for durable decisions, preferences, gotchas, rejected approaches, and project status.

## Style Preference Example

If asked to add controls such as buttons, recall prior UI/design engrams. A small mention like "button" should awaken memories about preferred style, icon usage, restraint, and avoiding unnecessary instruction-file bloat.

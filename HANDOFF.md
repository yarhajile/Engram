# Engram Handoff Snapshot

Date: 2026-09-01

## What Engram Is

Engram is a local memory layer for AI coding agents. It stores complete conversation transcripts as append-only evidence while keeping normal recall focused on compact, curated memory records called engrams.

The intended behavior is:

1. An agent receives a user request.
2. The agent queries Engram for relevant prior memories.
3. Engram returns compact summaries first.
4. The agent only drills into raw transcript turns when the memory source matters.
5. After meaningful task boundaries, the agent captures new turns and consolidates durable lessons into curated engrams.

This is meant to reduce repeated re-teaching across sessions without bloating `CLAUDE.md`.

## Current Architecture

- SQLite is the source of truth.
- SQLite FTS5 provides exact keyword recall over engrams and transcript turns.
- ChromaDB is optional and acts as a rebuildable semantic index for fuzzy recall.
- FastAPI exposes localhost HTTP endpoints.
- MCP exposes Claude-friendly tools over stdio.
- CLI remains available for setup, scripting, and maintenance.

Important files:

- `README.md`: user-facing docs.
- `CLAUDE.md`: instructions for agents using Engram.
- `schema.sql`: SQLite schema.
- `engram/store.py`: canonical persistence layer.
- `engram/importer.py`: historical transcript parser.
- `engram/api.py`: FastAPI service.
- `engram/cli.py`: command-line interface.
- `engram/mcp_server.py`: Claude Code MCP wrapper.
- `tests/`: unit, functional, API, CLI, and MCP coverage.

## Implemented Features

- Create and migrate the local database.
- Start memory sessions.
- Append raw transcript turns.
- Store curated engrams with tags, source spans, retention fields, and confidence.
- Recall via FTS, vector, or hybrid mode.
- Search raw transcript turns deliberately.
- Show a memory with optional transcript source span.
- Track pending consolidation.
- Mark sessions consolidated.
- Save and retrieve project checkpoints.
- Rebuild optional ChromaDB vector index.
- Import historical transcripts.
- Reuse active sessions with `ensure_session` / `ensure_memory_session`.
- Propose candidate memories from unconsolidated turns.
- Expose core operations through CLI, FastAPI, and MCP.

## Historical Transcript Import

The newest feature is retroactive import support for long prior conversations.

Supported input formats:

- `jsonl`: one JSON object per line with role/content fields.
- `json`: array of messages, or object with `messages`, `turns`, `conversation`, or `items`.
- `markdown`: role headings like `# User`, `## Assistant`, `### Claude`.
- `role-prefix`: blocks beginning with `User:`, `Assistant:`, `Claude:`, etc.

Imported sessions are marked with status `imported` and are pending consolidation by default. That is deliberate: raw transcript import is evidence capture, not memory curation.

CLI example:

```sh
cd /Users/elijah/Documents/ChatGPT/Engram
.venv/bin/python -m engram import-transcript /path/to/old-chat.md \
  --project "Work Project" \
  --title "Long architecture conversation" \
  --json
```

API example:

```sh
curl -X POST 'http://127.0.0.1:8732/imports/transcript' \
  -H 'Content-Type: application/json' \
  -d '{
    "path": "/path/to/old-chat.md",
    "project": "Work Project",
    "title": "Long architecture conversation"
  }'
```

MCP tool:

```text
import_transcript_file
```

After importing, run targeted searches over the imported turns and promote durable lessons into engrams.

Useful commands:

```sh
.venv/bin/python -m engram pending
.venv/bin/python -m engram propose-memories <session-id> --json
.venv/bin/python -m engram search-turns "button style icon tooltip"
.venv/bin/python -m engram remember --kind preference --title "..." --summary "..."
```

## Local Setup On Another Machine

From the unpacked project folder:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e '.[dev]'
python3 -m engram init
```

Run tests:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
```

For routine updates after new code is pushed, run:

```sh
scripts/update-local.sh
```

Useful options:

```sh
scripts/update-local.sh --no-pull
scripts/update-local.sh --no-tests
scripts/update-local.sh --reindex-vectors
scripts/update-local.sh --python=/path/to/python3
```

Start the API:

```sh
scripts/start-api.sh
```

Default API:

```text
http://127.0.0.1:8732
```

Check health:

```sh
curl 'http://127.0.0.1:8732/health'
```

## Claude Code MCP Setup

Install the package in the project venv first:

```sh
cd /path/to/Engram
.venv/bin/python -m pip install -e '.[dev]'
```

Then add the MCP server:

```sh
claude mcp add --transport stdio --scope user \
  --env ENGRAM_DB=/path/to/Engram/.engram/engram.sqlite3 \
  engram -- /path/to/Engram/.venv/bin/engram-mcp
```

In Claude Code, run:

```text
/mcp
```

Confirm the `engram` server is connected and exposes tools including:

- `recall_memory`
- `show_memory`
- `search_transcript`
- `import_transcript_file`
- `ensure_memory_session`
- `start_memory_session`
- `capture_memory_turn`
- `remember_memory`
- `pending_consolidation`
- `propose_memories`
- `mark_session_consolidated`
- `save_project_checkpoint`
- `get_project_checkpoint`
- `reindex_vector_memory`

## Suggested Testing Flow For Imported Work Conversations

1. Import one long transcript.
2. Confirm it appears in pending consolidation.
3. Search the transcript for a known phrase from that conversation.
4. Create one curated engram from a durable decision or preference in the transcript.
5. Recall using adjacent terms, not exact terms, to test whether the memory awakens naturally.
6. If ChromaDB is installed, reindex vectors and test `mode=vector` and `mode=hybrid`.
7. Test Claude MCP by asking Claude a question that should trigger the imported memory.

## Sticky Memory Loop

The preferred Claude behavior is:

```text
start work
  recall_memory(user request)
  ensure_memory_session(project, task title)

during work
  capture_memory_turn(...)

after final / waiting / correction / decision / bug fix
  propose_memories(session_id)
  remember_memory(...) for approved durable candidates
  mark_session_consolidated(session_id)
```

`remember_memory` writes to SQLite and immediately upserts the engram into ChromaDB when ChromaDB is available. Manual `reindex_vector_memory` is mainly for restore, repair, first Chroma install, or deleted `.engram/chromadb` cases.

Example:

```sh
.venv/bin/python -m engram import-transcript /path/to/work-chat.md \
  --project "Work Project" \
  --title "Historical project context" \
  --json

.venv/bin/python -m engram pending
.venv/bin/python -m engram search-turns "buttons icons toolbar"
.venv/bin/python -m engram recall "add a new button" --include-body
```

## Current Test Status

Latest local run:

```text
18 passed, 1 warning
```

The warning is a Starlette/FastAPI test client deprecation warning and does not currently affect behavior.

## Notes For Future Development

Recommended next improvements:

- Add redaction/review tools for imported transcripts before consolidation.
- Add assisted consolidation: propose candidate engrams from pending transcript spans.
- Add update/reconsolidation support for existing engrams.
- Add import adapters for specific exports if needed, such as Claude, ChatGPT, Cursor, or Codex transcript formats.
- Add source-span helpers so generated engrams can point back to exact imported turn ranges.
- Add a small local UI for reviewing pending imports and approving engrams.

Do not store secrets, credentials, private keys, or tokens as engrams. If historical transcripts may contain secrets, add redaction before importing or before creating curated engrams.

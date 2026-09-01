# Engram

Engram is a local memory service for AI coding agents.

It gives agents a durable project memory without pretending to create a literal infinite context window. The model still reasons over the context it has loaded right now, but Engram lets it retrieve the right prior decisions, preferences, transcript spans, and project-specific expectations on demand.

The goal is simple: stop re-teaching every new agent session the same project history.

## Why This Exists

Large `CLAUDE.md` files help, but they do not scale forever. Over time they become crowded with style preferences, old decisions, implementation gotchas, reminders, and corrections that only matter in certain situations.

Engram moves that long-tail knowledge into a searchable SQLite archive.

For example, if a future task says:

```text
Add a new button to the toolbar.
```

Engram can recall a prior memory like:

```text
When adding buttons or controls, prefer familiar icons, restrained styling,
tooltips for icon-only controls, and existing design-system patterns.
```

The agent gets the relevant memory only when the topic is awakened, instead of carrying every possible instruction in the active prompt all the time.

## Mental Model

```text
context window = current attention
SQLite database = long-term project archive
turns table = full transcript evidence
engrams table = distilled recall records
recall endpoint = associative memory lookup
consolidation = writing durable memories after a task boundary
```

Engram is not magic unlimited context. It is a practical retrieval layer for giving agents continuity across sessions.

## Architecture

Engram stores memory in layers:

```text
Hot memory:
  Compact curated engrams used for normal recall.

Warm memory:
  Longer engram bodies and source turn ranges.

Cold archive:
  Raw transcript turns stored as append-only evidence.
```

The key rule:

```text
Store raw history for audit.
Retrieve distilled meaning for cognition.
```

Raw transcripts are kept, but normal agent recall searches curated engrams first. The full transcript is only loaded when a memory points back to it or when the user asks for transcript-level detail.

## Retrieval Model

Engram uses a hybrid retrieval model:

```text
SQLite
  Canonical source of truth for sessions, turns, engrams, checkpoints, tags,
  files, status, retention fields, source spans, and audit history.

SQLite FTS5
  Exact keyword recall for names, files, modules, explicit tags, and phrases.

ChromaDB
  Optional semantic recall for fuzzy matches and related concepts.
```

SQLite remains authoritative. ChromaDB is a derived index that can be rebuilt from active engrams:

```sh
python3 -m engram reindex-vectors
```

Recall modes:

```text
hybrid
  Default. Merge FTS and vector results, then boost by importance and retention.

fts
  Exact keyword search only.

vector
  Semantic search only.
```

Example:

```sh
python3 -m engram recall "toolbar action control visual affordance" --mode vector --include-body
```

## Project Layout

```text
Engram/
  CLAUDE.md             Agent behavior instructions for using Engram
  README.md             This file
  pyproject.toml        Python package and API dependencies
  schema.sql            SQLite schema
  .engram/
    engram.sqlite3      Local memory database, ignored by git
  engram/
    api.py              FastAPI localhost service
    cli.py              CLI fallback and maintenance interface
    mcp_server.py       Claude Code MCP tool wrapper
    store.py            Shared SQLite memory layer
    vector_store.py     Optional ChromaDB semantic index
  scripts/
    start-api.sh        Starts the localhost API
```

## Installation

```sh
cd /Users/elijah/Documents/ChatGPT/Engram
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
python3 -m engram init
```

The default database path is:

```text
.engram/engram.sqlite3
```

## Running The Local API

Start the localhost service:

```sh
cd /Users/elijah/Documents/ChatGPT/Engram
scripts/start-api.sh
```

By default, Engram listens on:

```text
http://127.0.0.1:8732
```

You can override the host or port:

```sh
ENGRAM_PORT=9001 scripts/start-api.sh
```

## Claude Code MCP Integration

Engram includes a local stdio MCP server. This is the preferred Claude Code integration because it exposes memory operations as first-class tools instead of relying on ad hoc `curl` calls.

Install/update the package first:

```sh
cd /Users/elijah/Documents/ChatGPT/Engram
.venv/bin/python -m pip install -e '.[dev]'
```

Add Engram to Claude Code as a user-scoped MCP server:

```sh
claude mcp add --transport stdio --scope user \
  --env ENGRAM_DB=/Users/elijah/Documents/ChatGPT/Engram/.engram/engram.sqlite3 \
  engram -- /Users/elijah/Documents/ChatGPT/Engram/.venv/bin/engram-mcp
```

Then in Claude Code:

```text
/mcp
```

Confirm the `engram` server is connected and exposes tools. The most important tool is:

```text
recall_memory
```

Useful tools:

```text
recall_memory
show_memory
search_transcript
import_transcript_file
start_memory_session
capture_memory_turn
remember_memory
pending_consolidation
mark_session_consolidated
save_project_checkpoint
get_project_checkpoint
reindex_vector_memory
```

For project-scoped setup, copy [.mcp.json.example](./.mcp.json.example) to `.mcp.json` in the project where you want Claude Code to use Engram.

## API Endpoints

```text
GET  /health
POST /init
POST /sessions
POST /turns
POST /engrams
GET  /recall
GET  /engrams/{engram_id}
GET  /turns/search
GET  /consolidation/pending
POST /sessions/{session_id}/mark-consolidated
POST /vectors/reindex
POST /checkpoints
GET  /checkpoints/{project}
POST /imports/transcript
```

### Health

```sh
curl 'http://127.0.0.1:8732/health'
```

### Recall Memories

```sh
curl 'http://127.0.0.1:8732/recall?query=add%20a%20new%20button&include_body=true'
```

Normal recall returns curated engrams, not raw transcript dumps.

Use a specific recall mode when helpful:

```sh
curl 'http://127.0.0.1:8732/recall?query=toolbar%20visual%20control&mode=vector&include_body=true'
```

### Show A Memory And Source Transcript

```sh
curl 'http://127.0.0.1:8732/engrams/1?transcript=true'
```

Use this when the compact memory is relevant but not enough.

### Create A Session

```sh
curl -X POST 'http://127.0.0.1:8732/sessions' \
  -H 'Content-Type: application/json' \
  -d '{
    "project": "Example Project",
    "title": "Toolbar button discussion"
  }'
```

### Capture Transcript Turns

```sh
curl -X POST 'http://127.0.0.1:8732/turns' \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id": 1,
    "role": "user",
    "phase": "active",
    "content": "Add a new button to the toolbar."
  }'
```

```sh
curl -X POST 'http://127.0.0.1:8732/turns' \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id": 1,
    "role": "assistant",
    "phase": "final",
    "content": "Added the toolbar button using the existing icon button style."
  }'
```

### Create A Curated Memory

```sh
curl -X POST 'http://127.0.0.1:8732/engrams' \
  -H 'Content-Type: application/json' \
  -d '{
    "kind": "preference",
    "title": "Prefer icon-first toolbar controls",
    "summary": "When adding toolbar buttons, prefer familiar icons, compact controls, tooltips, and existing design-system patterns.",
    "body": "This should be recalled whenever future work mentions buttons, controls, toolbars, icons, or UI style.",
    "continuity": "low",
    "durable": "high",
    "importance": 5,
    "confidence": 0.95,
    "tags": ["ui", "buttons", "toolbar", "icons", "design"]
  }'
```

### Import Historical Transcripts

Engram can import old conversations as raw transcript turns. Imported sessions are marked pending consolidation by default so Claude, a future curator, or you can turn the useful parts into durable engrams later.

Supported formats:

```text
jsonl
  One JSON object per line, with role/content fields.

json
  An array of message objects, or an object with messages/turns/conversation/items.

markdown
  Role headings like # User and ## Assistant.

role-prefix
  Plain text blocks beginning with User:, Assistant:, Claude:, etc.

claude-code
  Native Claude Code session transcripts (~/.claude/projects/*/*.jsonl).
  Auto-detected. Only real user/assistant turns are kept: tool-result
  turns, sidechain (subagent) turns, meta turns, and non-conversation
  lines (mode, attachment, system, etc.) are dropped. Assistant turns
  keep thinking/text content and drop tool_use/tool_result blocks.
```

CLI:

```sh
python3 -m engram import-transcript /path/to/old-chat.md \
  --project "Work Project" \
  --title "Long architecture conversation"
```

API:

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

## CLI Fallback

The API is the preferred integration surface, but the CLI is useful for scripting and maintenance.

```sh
python3 -m engram init
python3 -m engram recall "add a new button" --include-body
python3 -m engram recall "toolbar visual control" --mode vector --include-body
python3 -m engram show 1 --transcript
python3 -m engram pending
python3 -m engram reindex-vectors
python3 -m engram import-transcript /path/to/old-chat.md --project "Work Project"
```

Start a session:

```sh
SESSION_ID=$(python3 -m engram start-session --project "Example Project" --title "Toolbar button discussion")
```

Capture a turn:

```sh
printf '%s\n' "Add a new button to the toolbar." |
  python3 -m engram capture-turn --session-id "$SESSION_ID" --role user --phase active --content -
```

Remember a durable lesson:

```sh
python3 -m engram remember \
  --kind preference \
  --durable high \
  --title "Prefer icon-first toolbar controls" \
  --summary "Toolbar buttons should use familiar icons, compact controls, and existing design-system patterns." \
  --tag ui --tag buttons --tag icons
```

## Testing

Install dev dependencies:

```sh
cd /Users/elijah/Documents/ChatGPT/Engram
.venv/bin/python -m pip install -e '.[dev]'
```

Run the fast test battery:

```sh
.venv/bin/python -B -m pytest -q -p no:cacheprovider
```

The default tests use temporary SQLite databases and mock the ChromaDB boundary. This keeps the suite fast, deterministic, and independent of embedding-model downloads. Real vector behavior can be checked manually with:

```sh
.venv/bin/python -B -m engram reindex-vectors
.venv/bin/python -B -m engram recall "toolbar action control visual affordance" --mode vector --include-body
```

## Consolidation Workflow

Transcript capture and memory consolidation are separate operations.

Capture is mechanical:

```text
Store the complete conversation turns as evidence.
```

Consolidation is judgment:

```text
Extract the durable facts, decisions, preferences, and gotchas that future
agents should actually recall.
```

Good consolidation boundaries include:

- after an assistant final response,
- after an assistant asks for user input,
- after a design decision,
- after a bug is fixed,
- after the user corrects an assumption,
- after a meaningful phase of work completes.

Check for unconsolidated sessions:

```sh
python3 -m engram pending
```

Mark a session consolidated:

```sh
python3 -m engram mark-consolidated 1
```

## Database Tables

```text
sessions
  Conversation or task-level containers.

turns
  Append-only raw transcript entries.

engrams
  Curated memory records used for normal recall.

engram_tags
  Tags attached to curated memories.

engram_files
  File paths connected to curated memories.

checkpoints
  Active project-state summaries.

engram_fts
  Full-text index for curated memory search.

turn_fts
  Full-text index for deliberate raw transcript search.
```

## Claude Integration

Claude Code's most native long-term integration path is MCP. Engram currently exposes a plain localhost REST API, which Claude can query with allowed shell or HTTP tooling.

The intended behavior for agents is:

1. At the start of substantial work, call `/recall` with the user request.
2. If the request mentions a specific feature, file, UI pattern, bug, or prior decision, run a second targeted recall.
3. Use retrieved memories as hints, not absolute truth.
4. Verify remembered claims against current project files.
5. After a final or waiting-on-user response, capture turns and consolidate durable lessons into new engrams.

The MCP adapter exposes Engram operations as first-class Claude tools while reusing the same `engram.store` module.

## Privacy And Security

Engram is local-first and currently has no authentication or encryption.

That is intentional for this prototype. Run it bound to localhost:

```text
127.0.0.1
```

Do not bind it to a public interface unless authentication, authorization, and encryption are added.

Do not store secrets, credentials, private keys, or tokens as engrams.

## Current Status

Implemented:

- SQLite schema.
- CLI interface.
- FastAPI localhost service.
- Full transcript turn storage.
- Curated memory storage.
- Continuity and durable retention fields.
- Superseded and retired memory states.
- Full-text search for engrams and raw turns.
- Optional ChromaDB semantic search.
- Hybrid recall over FTS and vectors.
- Project checkpoints.
- Source transcript drill-down from an engram.
- MCP adapter for Claude Code.
- Historical transcript import for JSONL, JSON, Markdown, role-prefixed text, and native Claude Code sessions.
- Seed memories for UI-control recall and FastAPI integration.

Planned:

- Better update/reconsolidation support for existing engrams.
- Redaction and review workflow for sensitive imported turns.

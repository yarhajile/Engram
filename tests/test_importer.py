from __future__ import annotations

import json

from engram import importer, store


def test_parse_jsonl_transcript(tmp_path):
    path = tmp_path / "chat.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "First question", "created_at": "2026-09-01T10:00:00Z"}),
                json.dumps({"role": "assistant", "content": "First answer"}),
            ]
        ),
        encoding="utf-8",
    )

    turns = importer.parse_transcript(path)

    assert [turn["role"] for turn in turns] == ["user", "assistant"]
    assert turns[0]["created_at"] == "2026-09-01T10:00:00Z"


def test_parse_json_transcript_from_messages_key(tmp_path):
    path = tmp_path / "chat.json"
    path.write_text(
        json.dumps(
            {
                "messages": [
                    {"author": "human", "text": "Use SQLite."},
                    {"author": "claude", "text": "SQLite is the source of truth."},
                ]
            }
        ),
        encoding="utf-8",
    )

    turns = importer.parse_transcript(path)

    assert [turn["role"] for turn in turns] == ["user", "assistant"]
    assert turns[1]["content"] == "SQLite is the source of truth."


def test_parse_markdown_role_headings(tmp_path):
    path = tmp_path / "chat.md"
    path.write_text(
        "# User\nAdd a button.\n\n## Assistant\nUse the existing icon style.\n",
        encoding="utf-8",
    )

    turns = importer.parse_transcript(path)

    assert [turn["role"] for turn in turns] == ["user", "assistant"]
    assert turns[0]["content"] == "Add a button."


def test_parse_role_prefix_text(tmp_path):
    path = tmp_path / "chat.txt"
    path.write_text(
        "User: What should Engram remember?\nAssistant: Durable project context.\n",
        encoding="utf-8",
    )

    turns = importer.parse_transcript(path)

    assert [turn["role"] for turn in turns] == ["user", "assistant"]
    assert turns[1]["content"] == "Durable project context."


def test_import_transcript_creates_pending_session_and_searchable_turns(tmp_path, db_path, no_vectors):
    path = tmp_path / "chat.md"
    path.write_text(
        "# User\nRemember that toolbar controls use icons.\n\n# Assistant\nStored as imported context.\n",
        encoding="utf-8",
    )

    result = store.import_transcript(path, project="Work", title="Toolbar memory", db_path=db_path)
    turns = store.search_turns("toolbar icons", db_path=db_path)
    pending = store.pending(db_path)

    assert result["turn_count"] == 2
    assert result["pending_consolidation"] is True
    assert turns[0]["session_id"] == result["session_id"]
    assert pending[0]["id"] == result["session_id"]

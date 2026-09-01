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


def claude_code_line(**overrides):
    line = {
        "type": "user",
        "isSidechain": False,
        "isMeta": False,
        "timestamp": "2026-08-27T16:02:00Z",
        "sessionId": "384568ba-7cc0-4a9c-a491-021d9a3611c6",
        "message": {"role": "user", "content": "placeholder"},
    }
    line.update(overrides)
    return json.dumps(line)


def test_parse_claude_code_extracts_real_user_and_assistant_turns(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(
        "\n".join(
            [
                claude_code_line(message={"role": "user", "content": "Fix the lat/long truncation bug."}),
                claude_code_line(
                    type="assistant",
                    message={"role": "assistant", "content": [{"type": "text", "text": "Looking at the view generator now."}]},
                ),
            ]
        ),
        encoding="utf-8",
    )

    turns = importer.parse_transcript(path, fmt="claude-code")

    assert [turn["role"] for turn in turns] == ["user", "assistant"]
    assert turns[0]["content"] == "Fix the lat/long truncation bug."
    assert turns[1]["content"] == "Looking at the view generator now."


def test_parse_claude_code_drops_tool_result_user_turns(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(
        "\n".join(
            [
                claude_code_line(message={"role": "user", "content": "Real question."}),
                claude_code_line(
                    message={
                        "role": "user",
                        "content": [{"type": "tool_result", "content": [{"type": "text", "text": "file contents..."}]}],
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    turns = importer.parse_transcript(path, fmt="claude-code")

    assert [turn["content"] for turn in turns] == ["Real question."]


def test_parse_claude_code_drops_meta_user_turns(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(
        "\n".join(
            [
                claude_code_line(message={"role": "user", "content": "Real question."}),
                claude_code_line(isMeta=True, message={"role": "user", "content": "## Context Usage\n..."}),
            ]
        ),
        encoding="utf-8",
    )

    turns = importer.parse_transcript(path, fmt="claude-code")

    assert [turn["content"] for turn in turns] == ["Real question."]


def test_parse_claude_code_joins_thinking_and_text_and_drops_tool_use(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(
        claude_code_line(
            type="assistant",
            message={
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "Let me check the schema first."},
                    {"type": "tool_use", "name": "Read", "input": {"path": "x.py"}},
                    {"type": "text", "text": "The schema looks fine."},
                ],
            },
        ),
        encoding="utf-8",
    )

    turns = importer.parse_transcript(path, fmt="claude-code")

    assert len(turns) == 1
    assert "Let me check the schema first." in turns[0]["content"]
    assert "The schema looks fine." in turns[0]["content"]
    assert "Read" not in turns[0]["content"]


def test_parse_claude_code_ignores_non_conversation_line_types(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"type": "mode", "mode": "normal", "sessionId": "x"}),
                json.dumps({"type": "attachment", "sessionId": "x"}),
                json.dumps({"type": "system", "subtype": "compact_boundary", "sessionId": "x"}),
                claude_code_line(message={"role": "user", "content": "Only real turn."}),
            ]
        ),
        encoding="utf-8",
    )

    turns = importer.parse_transcript(path, fmt="claude-code")

    assert [turn["content"] for turn in turns] == ["Only real turn."]


def test_parse_claude_code_drops_sidechain_turns(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(
        "\n".join(
            [
                claude_code_line(isSidechain=True, message={"role": "user", "content": "Subagent internal turn."}),
                claude_code_line(message={"role": "user", "content": "Main turn."}),
            ]
        ),
        encoding="utf-8",
    )

    turns = importer.parse_transcript(path, fmt="claude-code")

    assert [turn["content"] for turn in turns] == ["Main turn."]


def test_detect_format_auto_picks_claude_code_for_session_shaped_jsonl(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(claude_code_line(message={"role": "user", "content": "Auto detected."}), encoding="utf-8")

    turns = importer.parse_transcript(path)

    assert turns[0]["content"] == "Auto detected."


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

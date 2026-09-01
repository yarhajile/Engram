from __future__ import annotations

import json
import subprocess
import sys


def run_cli(db_path, *args: str, input_text: str | None = None):
    return subprocess.run(
        [sys.executable, "-B", "-m", "engram", "--db", str(db_path), *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    )


def test_cli_lifecycle_with_json_recall(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.sqlite3"
    monkeypatch.setenv("ENGRAM_DISABLE_CHROMA", "1")

    run_cli(db_path, "init")
    session_id = int(run_cli(db_path, "start-session", "--project", "CLI", "--title", "Lifecycle").stdout.strip())
    first_turn = int(
        run_cli(
            db_path,
            "capture-turn",
            "--session-id",
            str(session_id),
            "--role",
            "user",
            "--content",
            "-",
            input_text="The toolbar should use icon buttons.",
        ).stdout.strip()
    )
    memory_id = int(
        run_cli(
            db_path,
            "remember",
            "--title",
            "Toolbar icon buttons",
            "--summary",
            "Prefer icon buttons in toolbar UI.",
            "--durable",
            "high",
            "--source-turn-start",
            str(first_turn),
            "--source-turn-end",
            str(first_turn),
            "--tag",
            "buttons",
        ).stdout.strip()
    )

    recall = run_cli(db_path, "recall", "toolbar buttons", "--mode", "fts", "--json").stdout
    rows = json.loads(recall)

    assert rows[0]["id"] == memory_id
    assert rows[0]["durable"] == "high"


def test_cli_ensure_session_and_propose_memories(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.sqlite3"
    monkeypatch.setenv("ENGRAM_DISABLE_CHROMA", "1")

    first = json.loads(
        run_cli(
            db_path,
            "ensure-session",
            "--project",
            "CLI",
            "--title",
            "Sticky",
            "--json",
        ).stdout
    )
    second = json.loads(
        run_cli(
            db_path,
            "ensure-session",
            "--project",
            "CLI",
            "--title",
            "Sticky",
            "--json",
        ).stdout
    )
    run_cli(
        db_path,
        "capture-turn",
        "--session-id",
        str(first["id"]),
        "--role",
        "user",
        "--content",
        "We should remember API endpoint decisions after final answers.",
    )

    proposed = json.loads(run_cli(db_path, "propose-memories", str(first["id"]), "--json").stdout)

    assert first["created"] is True
    assert second["created"] is False
    assert second["id"] == first["id"]
    assert proposed["candidates"][0]["kind"] == "preference"
    assert "api" in proposed["candidates"][0]["tags"]

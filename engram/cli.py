#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from . import store


def read_text_arg(value: str | None) -> str:
    if value is None or value == "-":
        return sys.stdin.read()
    path = Path(value)
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    return value


def format_engram(item: dict[str, Any]) -> str:
    lines = [f"#{item['id']} [{item['kind']}] {item['title']}", f"Summary: {item['summary']}"]
    if item.get("tags"):
        lines.append("Tags: " + ", ".join(item["tags"]))
    if item.get("files"):
        lines.append("Files: " + ", ".join(item["files"]))
    if item.get("source_turn_start") or item.get("source_turn_end"):
        lines.append(f"Source turns: {item.get('source_turn_start') or '?'}-{item.get('source_turn_end') or '?'}")
    if item.get("body"):
        lines.append("Body:\n" + item["body"])
    return "\n".join(lines)


def init_db(args: argparse.Namespace) -> None:
    result = store.init_db(args.db)
    print(f"Initialized Engram database at {result['database']}")


def start_session(args: argparse.Namespace) -> None:
    result = store.start_session(args.project, args.title or "", args.metadata, args.db)
    print(result["id"])


def ensure_session(args: argparse.Namespace) -> None:
    result = store.ensure_session(
        args.project,
        args.title or "",
        args.metadata,
        reuse_active=not args.no_reuse,
        db_path=args.db,
    )
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(result["id"])


def capture_turn(args: argparse.Namespace) -> None:
    result = store.capture_turn(
        session_id=args.session_id,
        role=args.role,
        phase=args.phase,
        content=read_text_arg(args.content),
        metadata=args.metadata,
        db_path=args.db,
    )
    print(result["id"])


def remember(args: argparse.Namespace) -> None:
    result = store.remember(
        title=args.title,
        summary=args.summary,
        body=read_text_arg(args.body) if args.body else "",
        kind=args.kind,
        continuity=args.continuity,
        durable=args.durable,
        importance=args.importance,
        confidence=args.confidence,
        supersedes_id=args.supersedes_id,
        session_id=args.session_id,
        source_turn_start=args.source_turn_start,
        source_turn_end=args.source_turn_end,
        tags=args.tag or [],
        files=args.file or [],
        metadata=args.metadata,
        db_path=args.db,
    )
    print(result["id"])


def recall(args: argparse.Namespace) -> None:
    rows = store.recall(args.query, args.limit, args.include_body, args.db, args.mode)
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print("No matching engrams.")
        return
    for row in rows:
        print(format_engram(row))
        print("")


def show(args: argparse.Namespace) -> None:
    try:
        item = store.show_engram(args.id, args.transcript, args.max_chars, args.db)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc
    transcript = item.pop("transcript", [])
    print(format_engram(item))
    if args.transcript:
        if not transcript:
            print("\nNo source turn span recorded for this engram.")
            return
        print("\nTranscript span:")
        for turn in transcript:
            print(f"\n--- turn {turn['id']} {turn['role']} / {turn['phase']} ---\n{turn['content'].strip()}")


def search_turns(args: argparse.Namespace) -> None:
    rows = store.search_turns(args.query, args.limit, args.max_chars, args.db)
    for row in rows:
        print(f"--- turn {row['id']} session {row['session_id']} {row['role']} / {row['phase']} ---")
        print(row["content"].strip())
        print("")


def pending(args: argparse.Namespace) -> None:
    sessions = store.pending(args.db)
    if not sessions:
        print("No sessions pending consolidation.")
        return
    for session in sessions:
        print(
            f"session {session['id']}: {session['project']} / {session['title']} "
            f"turns>{session['last_consolidated_turn_id'] or 0}..{session['latest_turn_id']}"
        )


def propose_memories(args: argparse.Namespace) -> None:
    result = store.propose_memories(args.session_id, args.limit, args.max_body_chars, args.db)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    if not result["candidates"]:
        print("No memory candidates found.")
        return
    for candidate in result["candidates"]:
        print(f"[{candidate['kind']}] {candidate['title']}")
        print(f"Summary: {candidate['summary']}")
        print(f"Source turns: {candidate['source_turn_start']}-{candidate['source_turn_end']}")
        if candidate.get("tags"):
            print("Tags: " + ", ".join(candidate["tags"]))
        print("")


def mark_consolidated(args: argparse.Namespace) -> None:
    result = store.mark_consolidated(args.session_id, args.db)
    print(
        "Marked session "
        f"{result['session_id']} consolidated through turn {result['last_consolidated_turn_id']}."
    )


def reindex_vectors(args: argparse.Namespace) -> None:
    print(json.dumps(store.reindex_vectors(args.db), indent=2))


def save_checkpoint(args: argparse.Namespace) -> None:
    result = store.save_checkpoint(
        project=args.project,
        summary=read_text_arg(args.summary),
        active_topics=args.topic or [],
        metadata=args.metadata,
        db_path=args.db,
    )
    print(result["id"])


def get_checkpoint(args: argparse.Namespace) -> None:
    checkpoint = store.get_checkpoint(args.project, args.db)
    print(json.dumps(checkpoint, indent=2))


def import_transcript(args: argparse.Namespace) -> None:
    result = store.import_transcript(
        path=args.path,
        project=args.project,
        title=args.title or "",
        fmt=args.format,
        metadata=args.metadata,
        mark_consolidated_after_import=args.mark_consolidated,
        db_path=args.db,
    )
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(
        f"Imported {result['turn_count']} turns into session {result['session_id']} "
        f"({result['first_turn_id']}..{result['last_turn_id']})."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engram", description="SQLite-backed episodic memory for coding agents.")
    parser.add_argument("--db", type=Path, default=store.DEFAULT_DB, help="Path to Engram SQLite database.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Create or migrate the database.")
    p.set_defaults(func=init_db)

    p = sub.add_parser("start-session", help="Create a transcript session and print its id.")
    p.add_argument("--project", default=Path.cwd().name)
    p.add_argument("--title", default="")
    p.add_argument("--metadata", default="{}")
    p.set_defaults(func=start_session)

    p = sub.add_parser("ensure-session", help="Reuse an active session for a project/title or create one.")
    p.add_argument("--project", default=Path.cwd().name)
    p.add_argument("--title", default="")
    p.add_argument("--metadata", default="{}")
    p.add_argument("--no-reuse", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=ensure_session)

    p = sub.add_parser("capture-turn", help="Append a raw transcript turn. Use --content - to read stdin.")
    p.add_argument("--session-id", type=int, required=True)
    p.add_argument("--role", choices=["system", "user", "assistant", "tool", "developer"], required=True)
    p.add_argument("--phase", default="active")
    p.add_argument("--content", required=True)
    p.add_argument("--metadata", default="{}")
    p.set_defaults(func=capture_turn)

    p = sub.add_parser("remember", help="Create a distilled memory record.")
    p.add_argument("--title", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--body", default="")
    p.add_argument("--kind", default="note")
    p.add_argument("--continuity", choices=["high", "low"], default="low")
    p.add_argument("--durable", choices=["high", "low"], default="low")
    p.add_argument("--importance", type=int, default=3)
    p.add_argument("--confidence", type=float, default=0.8)
    p.add_argument("--supersedes-id", type=int)
    p.add_argument("--session-id", type=int)
    p.add_argument("--source-turn-start", type=int)
    p.add_argument("--source-turn-end", type=int)
    p.add_argument("--tag", action="append")
    p.add_argument("--file", action="append")
    p.add_argument("--metadata", default="{}")
    p.set_defaults(func=remember)

    p = sub.add_parser("recall", help="Search distilled memories first.")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--include-body", action="store_true")
    p.add_argument("--mode", choices=["hybrid", "fts", "vector"], default="hybrid")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=recall)

    p = sub.add_parser("show", help="Show one engram and optionally its source transcript span.")
    p.add_argument("id", type=int)
    p.add_argument("--transcript", action="store_true")
    p.add_argument("--max-chars", type=int, default=4000)
    p.set_defaults(func=show)

    p = sub.add_parser("search-turns", help="Search raw transcript turns deliberately.")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--max-chars", type=int, default=1200)
    p.set_defaults(func=search_turns)

    p = sub.add_parser("pending", help="List sessions with unconsolidated transcript turns.")
    p.set_defaults(func=pending)

    p = sub.add_parser("propose-memories", help="Suggest candidate engrams from unconsolidated session turns.")
    p.add_argument("session_id", type=int)
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--max-body-chars", type=int, default=1600)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=propose_memories)

    p = sub.add_parser("mark-consolidated", help="Mark all current turns in a session as consolidated.")
    p.add_argument("session_id", type=int)
    p.set_defaults(func=mark_consolidated)

    p = sub.add_parser("reindex-vectors", help="Rebuild the optional ChromaDB index from active engrams.")
    p.set_defaults(func=reindex_vectors)

    p = sub.add_parser("save-checkpoint", help="Save a project checkpoint summary.")
    p.add_argument("--project", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--topic", action="append")
    p.add_argument("--metadata", default="{}")
    p.set_defaults(func=save_checkpoint)

    p = sub.add_parser("checkpoint", help="Show the active checkpoint for a project.")
    p.add_argument("project")
    p.set_defaults(func=get_checkpoint)

    p = sub.add_parser("import-transcript", help="Import a historical conversation transcript.")
    p.add_argument("path", type=Path)
    p.add_argument("--project", required=True)
    p.add_argument("--title", default="")
    p.add_argument(
        "--format", choices=["auto", "jsonl", "json", "markdown", "role-prefix", "claude-code"], default="auto"
    )
    p.add_argument("--metadata", default="{}")
    p.add_argument("--mark-consolidated", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=import_transcript)
    return parser


def main(argv: Iterable[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

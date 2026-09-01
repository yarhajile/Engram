from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SUPPORTED_ROLES = {"system", "user", "assistant", "tool", "developer"}
ROLE_ALIASES = {
    "ai": "assistant",
    "assistant": "assistant",
    "claude": "assistant",
    "codex": "assistant",
    "developer": "developer",
    "human": "user",
    "system": "system",
    "tool": "tool",
    "user": "user",
}


def parse_transcript(path: Path, fmt: str = "auto") -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    selected = detect_format(path, text) if fmt == "auto" else fmt
    if selected == "jsonl":
        return parse_jsonl(text)
    if selected == "json":
        return parse_json(text)
    if selected == "markdown":
        return parse_markdown(text)
    if selected == "role-prefix":
        return parse_role_prefix(text)
    if selected == "claude-code":
        return parse_claude_code(text)
    raise ValueError(f"Unsupported transcript format: {fmt}")


def detect_format(path: Path, text: str) -> str:
    suffix = path.suffix.lower()
    stripped = text.lstrip()
    if suffix == ".jsonl":
        return "claude-code" if looks_like_claude_code(stripped) else "jsonl"
    if suffix == ".json" or stripped.startswith("{") or stripped.startswith("["):
        return "json"
    if re.search(r"(?im)^#{1,6}\s*(user|human|assistant|claude|ai|system|tool|developer)\b", text):
        return "markdown"
    return "role-prefix"


def looks_like_claude_code(stripped_text: str) -> bool:
    first_line = stripped_text.splitlines()[0] if stripped_text else ""
    try:
        item = json.loads(first_line)
    except json.JSONDecodeError:
        return False
    return isinstance(item, dict) and "sessionId" in item and "type" in item


def parse_claude_code(text: str) -> list[dict[str, Any]]:
    turns = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or obj.get("type") not in ("user", "assistant"):
            continue
        if obj.get("isSidechain") or obj.get("isMeta"):
            continue
        message = obj.get("message")
        if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
            continue
        content = extract_claude_code_content(message["role"], message.get("content"))
        if not content.strip():
            continue
        turn = {"role": message["role"], "content": content, "phase": "imported", "metadata": {}}
        created_at = obj.get("timestamp")
        if created_at:
            turn["created_at"] = str(created_at)
        turns.append(turn)
    return compact_turns(turns)


def extract_claude_code_content(role: str, content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    if role == "user":
        if any(isinstance(block, dict) and block.get("type") == "tool_result" for block in content):
            return ""
        blocks = [block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"]
    else:
        blocks = [
            block.get("text") or block.get("thinking") or ""
            for block in content
            if isinstance(block, dict) and block.get("type") in ("text", "thinking")
        ]
    return "\n\n".join(part for part in blocks if part)


def parse_jsonl(text: str) -> list[dict[str, Any]]:
    turns = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL on line {line_number}: {exc}") from exc
        turns.append(normalize_turn(item, line_number=line_number))
    return compact_turns(turns)


def parse_json(text: str) -> list[dict[str, Any]]:
    data = json.loads(text)
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        candidates = extract_json_candidates(data)
    else:
        raise ValueError("JSON transcript must be an array or object containing messages.")
    return compact_turns([normalize_turn(item) for item in candidates])


def extract_json_candidates(data: dict[str, Any]) -> list[Any]:
    for key in ("messages", "turns", "conversation", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    mapping = data.get("mapping")
    if isinstance(mapping, dict):
        messages = []
        for node in mapping.values():
            message = node.get("message") if isinstance(node, dict) else None
            if message:
                messages.append(message)
        return messages
    raise ValueError("Could not find messages, turns, conversation, items, or mapping in JSON transcript.")


def normalize_turn(item: Any, line_number: int | None = None) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"Transcript item must be an object{line_suffix(line_number)}.")

    role = normalize_role(item.get("role") or item.get("author") or item.get("speaker"))
    content = normalize_content(item.get("content") or item.get("text") or item.get("message"))
    if not role or role not in SUPPORTED_ROLES:
        raise ValueError(f"Missing or unsupported role{line_suffix(line_number)}.")
    if not content.strip():
        raise ValueError(f"Missing content{line_suffix(line_number)}.")

    turn = {
        "role": role,
        "content": content,
        "phase": item.get("phase") or "imported",
        "metadata": item.get("metadata") or {},
    }
    created_at = item.get("created_at") or item.get("timestamp") or item.get("created")
    if created_at:
        turn["created_at"] = str(created_at)
    return turn


def line_suffix(line_number: int | None) -> str:
    return f" on line {line_number}" if line_number is not None else ""


def normalize_role(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("role") or value.get("name")
    return ROLE_ALIASES.get(str(value or "").strip().lower(), "")


def normalize_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        parts = value.get("parts")
        if isinstance(parts, list):
            return "\n".join(str(part) for part in parts if part)
    return ""


def parse_markdown(text: str) -> list[dict[str, Any]]:
    heading = re.compile(r"(?im)^#{1,6}\s*(user|human|assistant|claude|ai|system|tool|developer)\b.*$")
    matches = list(heading.finditer(text))
    if not matches:
        return parse_role_prefix(text)

    turns = []
    for index, match in enumerate(matches):
        role = normalize_role(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            turns.append({"role": role, "phase": "imported", "content": content, "metadata": {}})
    return compact_turns(turns)


def parse_role_prefix(text: str) -> list[dict[str, Any]]:
    prefix = re.compile(r"(?im)^(user|human|assistant|claude|ai|system|tool|developer)\s*:\s*")
    matches = list(prefix.finditer(text))
    if not matches:
        stripped = text.strip()
        if not stripped:
            return []
        return [{"role": "user", "phase": "imported", "content": stripped, "metadata": {"import_note": "unstructured"}}]

    turns = []
    for index, match in enumerate(matches):
        role = normalize_role(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            turns.append({"role": role, "phase": "imported", "content": content, "metadata": {}})
    return compact_turns(turns)


def compact_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for turn in turns:
        if compacted and can_merge(compacted[-1], turn):
            compacted[-1]["content"] = compacted[-1]["content"].rstrip() + "\n\n" + turn["content"].lstrip()
            continue
        compacted.append(turn)
    return compacted


def can_merge(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get("role") == right.get("role")
        and left.get("phase") == right.get("phase")
        and not left.get("created_at")
        and not right.get("created_at")
    )

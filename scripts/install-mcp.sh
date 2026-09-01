#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

NAME="engram"
SCOPE="user"
REMOVE_EXISTING=1
PRINT_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --name=*)
      NAME="${arg#--name=}"
      ;;
    --scope=*)
      SCOPE="${arg#--scope=}"
      ;;
    --no-remove)
      REMOVE_EXISTING=0
      ;;
    --print)
      PRINT_ONLY=1
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/install-mcp.sh [options]

Install this Engram checkout as a Claude Code MCP stdio server.

Options:
  --name=NAME    MCP server name. Defaults to engram.
  --scope=SCOPE  Claude MCP config scope. Defaults to user.
  --no-remove    Do not remove an existing server with the same name first.
  --print        Print the add-json command without running it.

Environment:
  ENGRAM_DB      Optional SQLite db path. Defaults to <repo>/.engram/engram.sqlite3.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Run scripts/install-mcp.sh --help for usage." >&2
      exit 2
      ;;
  esac
done

ROOT="$(pwd -P)"
COMMAND="$ROOT/.venv/bin/engram-mcp"
DB_PATH="${ENGRAM_DB:-$ROOT/.engram/engram.sqlite3}"

if [ ! -x "$COMMAND" ]; then
  echo "Missing MCP executable: $COMMAND" >&2
  echo "Run scripts/update-local.sh --no-pull first." >&2
  exit 1
fi

CONFIG_JSON="$(ENGRAM_MCP_COMMAND="$COMMAND" ENGRAM_MCP_DB="$DB_PATH" "$ROOT/.venv/bin/python" -c '
import json
import os

config = {
    "type": "stdio",
    "command": os.environ["ENGRAM_MCP_COMMAND"],
    "args": [],
    "env": {"ENGRAM_DB": os.environ["ENGRAM_MCP_DB"]},
}
print(json.dumps(config))
')"

if [ "$PRINT_ONLY" -eq 1 ]; then
  printf "claude mcp add-json --scope %q %q %q\n" "$SCOPE" "$NAME" "$CONFIG_JSON"
  exit 0
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "Missing claude CLI on PATH." >&2
  echo "Install Claude Code, then rerun this script." >&2
  exit 1
fi

if [ "$REMOVE_EXISTING" -eq 1 ]; then
  claude mcp remove "$NAME" --scope "$SCOPE" >/dev/null 2>&1 || true
fi

claude mcp add-json --scope "$SCOPE" "$NAME" "$CONFIG_JSON"

echo "Installed MCP server '$NAME' at scope '$SCOPE'."
echo "Run /mcp inside Claude Code and confirm the Engram tools are listed."

#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

WITH_PULL=1
WITH_TESTS=1
WITH_VECTORS=0
PYTHON_BIN="${PYTHON_BIN:-python3}"

for arg in "$@"; do
  case "$arg" in
    --no-pull)
      WITH_PULL=0
      ;;
    --no-tests)
      WITH_TESTS=0
      ;;
    --reindex-vectors)
      WITH_VECTORS=1
      ;;
    --python=*)
      PYTHON_BIN="${arg#--python=}"
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/update-local.sh [options]

Pull, install, migrate, and test a local Engram checkout.

Options:
  --no-pull          Skip git pull.
  --no-tests         Skip pytest.
  --reindex-vectors  Rebuild ChromaDB vectors after install/migration.
  --python=PATH      Python executable to use when creating .venv.

Environment:
  ENGRAM_DB          Optional SQLite db path. Defaults to .engram/engram.sqlite3.
  PYTHON_BIN         Python executable used when creating .venv.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Run scripts/update-local.sh --help for usage." >&2
      exit 2
      ;;
  esac
done

echo "==> Engram local update"
echo "    root: $(pwd)"

if [ "$WITH_PULL" -eq 1 ]; then
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if [ -n "$(git status --porcelain)" ]; then
      echo "Refusing to pull with uncommitted local changes." >&2
      echo "Commit, stash, or rerun with --no-pull." >&2
      exit 1
    fi
    echo "==> Pulling latest code"
    git pull --ff-only
  else
    echo "==> Not a git checkout; skipping pull"
  fi
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "==> Creating virtual environment"
  "$PYTHON_BIN" -m venv .venv
fi

echo "==> Upgrading pip tooling"
.venv/bin/python -m pip install --upgrade pip setuptools wheel

echo "==> Installing Engram with dev dependencies"
.venv/bin/python -m pip install -e '.[dev]'

echo "==> Migrating database"
.venv/bin/python -m engram init

if [ "$WITH_TESTS" -eq 1 ]; then
  echo "==> Running tests"
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
fi

if [ "$WITH_VECTORS" -eq 1 ]; then
  echo "==> Reindexing vectors"
  .venv/bin/python -B -m engram reindex-vectors
fi

cat <<EOF
==> Done

Useful checks:
  .venv/bin/python -m engram --help
  .venv/bin/python -m engram pending
  scripts/start-api.sh

Claude MCP command for this checkout:
  claude mcp add --transport stdio --scope user \\
    --env ENGRAM_DB=$(pwd)/.engram/engram.sqlite3 \\
    engram -- $(pwd)/.venv/bin/engram-mcp
EOF

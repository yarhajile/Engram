from __future__ import annotations

from pathlib import Path

import pytest

from engram import vector_store


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "engram.sqlite3"


@pytest.fixture
def no_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vector_store, "upsert_engram", lambda *args, **kwargs: False)
    monkeypatch.setattr(vector_store, "delete_engram", lambda *args, **kwargs: False)
    monkeypatch.setattr(vector_store, "search", lambda *args, **kwargs: [])
    monkeypatch.setattr(vector_store, "is_available", lambda: False)

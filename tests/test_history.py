"""Comprehensive tests for core/history.py."""

from pathlib import Path
from unittest.mock import patch

import pytest

from constants import OP_TYPE_COPY, OP_TYPE_RENAME
from core.history import RenameHistory, get_history_db_path
from models.operation_record import OperationRecord


@pytest.fixture
def history(tmp_path):
    """Create a RenameHistory with a temp DB path."""
    db_path = tmp_path / "test_history.db"
    with patch("core.history.get_history_db_path", return_value=db_path):
        h = RenameHistory()
    return h


@pytest.fixture
def sample_record(tmp_path):
    """Create a sample OperationRecord."""
    return OperationRecord(
        operation_type=OP_TYPE_RENAME,
        files_affected=[
            (Path("/dest/new1.mov"), Path("/src/old1.mov")),
            (Path("/dest/new2.mov"), Path("/src/old2.mov")),
        ],
    )


class TestGetHistoryDbPath:
    def test_returns_path(self):
        result = get_history_db_path()
        assert result.name == "history.db"


class TestRenameHistory:
    def test_log_and_get_recent(self, history, sample_record):
        history.log_operation(sample_record)
        recent = history.get_recent(10)
        assert len(recent) == 2
        assert recent[0]["operation_type"] == OP_TYPE_RENAME

    def test_search(self, history, sample_record):
        history.log_operation(sample_record)
        results = history.search("old1")
        assert len(results) >= 1
        assert "old1" in results[0]["old_path"]

    def test_search_no_match(self, history, sample_record):
        history.log_operation(sample_record)
        results = history.search("nonexistent_xyz")
        assert len(results) == 0

    def test_search_new_path(self, history, sample_record):
        history.log_operation(sample_record)
        results = history.search("new2")
        assert len(results) >= 1

    def test_get_recent_limit(self, history, sample_record):
        history.log_operation(sample_record)
        recent = history.get_recent(1)
        assert len(recent) == 1

    def test_clear(self, history, sample_record):
        history.log_operation(sample_record)
        history.clear()
        recent = history.get_recent(100)
        assert len(recent) == 0

    def test_empty_db(self, history):
        recent = history.get_recent(10)
        assert recent == []

    def test_search_empty_db(self, history):
        results = history.search("anything")
        assert results == []

    def test_multiple_operations(self, history):
        record1 = OperationRecord(
            operation_type=OP_TYPE_RENAME,
            files_affected=[(Path("/a/new.mov"), Path("/a/old.mov"))],
        )
        record2 = OperationRecord(
            operation_type=OP_TYPE_COPY,
            files_affected=[(Path("/b/copy.mov"), Path("/b/orig.mov"))],
        )
        history.log_operation(record1)
        history.log_operation(record2)
        recent = history.get_recent(100)
        assert len(recent) == 2
        types = {r["operation_type"] for r in recent}
        assert OP_TYPE_RENAME in types
        assert OP_TYPE_COPY in types

    def test_timestamp_stored(self, history, sample_record):
        history.log_operation(sample_record)
        recent = history.get_recent(1)
        assert recent[0]["timestamp"] is not None
        assert len(recent[0]["timestamp"]) > 0

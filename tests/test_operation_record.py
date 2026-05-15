"""Comprehensive tests for models/operation_record.py."""

from datetime import datetime
from pathlib import Path

from constants import OP_TYPE_COPY, OP_TYPE_EXTRACT, OP_TYPE_ORGANIZE, OP_TYPE_RENAME
from models.operation_record import OperationRecord


class TestOperationRecordInit:
    def test_basic_init(self):
        record = OperationRecord(
            operation_type=OP_TYPE_RENAME,
            files_affected=[(Path("/new"), Path("/old"))],
        )
        assert record.operation_type == OP_TYPE_RENAME
        assert len(record.files_affected) == 1
        assert isinstance(record.timestamp, datetime)

    def test_default_metadata(self):
        record = OperationRecord(OP_TYPE_RENAME, [])
        assert record.metadata == {}

    def test_custom_metadata(self):
        meta = {"source_dir": "/tmp"}
        record = OperationRecord(OP_TYPE_RENAME, [], metadata=meta)
        assert record.metadata == meta


class TestUndo:
    def test_undo_rename(self, tmp_path):
        old = tmp_path / "old.txt"
        new = tmp_path / "new.txt"
        old.write_text("content")
        old.rename(new)
        record = OperationRecord(
            operation_type=OP_TYPE_RENAME,
            files_affected=[(new, old)],
        )
        success, errors, msgs = record.undo()
        assert success == 1
        assert errors == 0
        assert old.exists()
        assert not new.exists()

    def test_undo_copy(self, tmp_path):
        original = tmp_path / "original.txt"
        original.write_text("data")
        copied = tmp_path / "copy.txt"
        copied.write_text("data")
        record = OperationRecord(
            operation_type=OP_TYPE_COPY,
            files_affected=[(copied, original)],
        )
        success, errors, msgs = record.undo()
        assert success == 1
        assert errors == 0
        assert not copied.exists()
        assert original.exists()

    def test_undo_rename_file_missing(self, tmp_path):
        record = OperationRecord(
            operation_type=OP_TYPE_RENAME,
            files_affected=[(tmp_path / "gone.txt", tmp_path / "old.txt")],
        )
        success, errors, msgs = record.undo()
        assert success == 0
        assert errors == 1
        assert "no longer exists" in msgs[0]

    def test_undo_copy_file_missing(self, tmp_path):
        record = OperationRecord(
            operation_type=OP_TYPE_COPY,
            files_affected=[(tmp_path / "gone.txt", tmp_path / "orig.txt")],
        )
        success, errors, msgs = record.undo()
        assert success == 0
        assert errors == 1

    def test_undo_rename_original_occupied(self, tmp_path):
        old = tmp_path / "old.txt"
        new = tmp_path / "new.txt"
        new.write_text("new content")
        old.write_text("different file now")
        record = OperationRecord(
            operation_type=OP_TYPE_RENAME,
            files_affected=[(new, old)],
        )
        success, errors, msgs = record.undo()
        assert errors == 1
        assert "occupied" in msgs[0]

    def test_undo_multiple_files(self, tmp_path):
        pairs = []
        for i in range(3):
            old = tmp_path / f"old_{i}.txt"
            new = tmp_path / f"new_{i}.txt"
            old.write_text(f"content_{i}")
            old.rename(new)
            pairs.append((new, old))
        record = OperationRecord(OP_TYPE_RENAME, pairs)
        success, errors, msgs = record.undo()
        assert success == 3
        assert errors == 0

    def test_undo_processes_in_reverse(self, tmp_path):
        """Undo should process in reverse order to handle dependencies."""
        a_old = tmp_path / "a.txt"
        a_new = tmp_path / "a_renamed.txt"
        a_old.write_text("a")
        a_old.rename(a_new)
        record = OperationRecord(OP_TYPE_RENAME, [(a_new, a_old)])
        success, errors, msgs = record.undo()
        assert success == 1


class TestSerialization:
    def test_to_dict(self):
        record = OperationRecord(
            operation_type=OP_TYPE_RENAME,
            files_affected=[(Path("/new/file.txt"), Path("/old/file.txt"))],
            metadata={"key": "value"},
        )
        d = record.to_dict()
        assert d["operation_type"] == OP_TYPE_RENAME
        assert len(d["files_affected"]) == 1
        assert d["files_affected"][0] == (str(Path("/new/file.txt")), str(Path("/old/file.txt")))
        assert d["metadata"] == {"key": "value"}
        assert "timestamp" in d

    def test_from_dict(self):
        d = {
            "operation_type": OP_TYPE_COPY,
            "files_affected": [("/new/a.txt", "/old/a.txt")],
            "metadata": {"test": True},
            "timestamp": "2025-05-15T10:30:00",
        }
        record = OperationRecord.from_dict(d)
        assert record.operation_type == OP_TYPE_COPY
        assert len(record.files_affected) == 1
        assert isinstance(record.files_affected[0][0], Path)
        assert record.metadata == {"test": True}
        assert record.timestamp.year == 2025

    def test_roundtrip(self):
        original = OperationRecord(
            operation_type=OP_TYPE_ORGANIZE,
            files_affected=[
                (Path("/a/new.mov"), Path("/a/old.mov")),
                (Path("/b/new.txt"), Path("/b/old.txt")),
            ],
            metadata={"root": "/project"},
        )
        d = original.to_dict()
        restored = OperationRecord.from_dict(d)
        assert restored.operation_type == original.operation_type
        assert len(restored.files_affected) == len(original.files_affected)
        assert str(restored.files_affected[0][0]) == str(original.files_affected[0][0])


class TestGetSummary:
    def test_rename_summary(self):
        record = OperationRecord(OP_TYPE_RENAME, [(Path("a"), Path("b"))])
        s = record.get_summary()
        assert "Renamed" in s
        assert "1 file(s)" in s

    def test_copy_summary(self):
        record = OperationRecord(OP_TYPE_COPY, [(Path("a"), Path("b")), (Path("c"), Path("d"))])
        s = record.get_summary()
        assert "Copied" in s
        assert "2 file(s)" in s

    def test_organize_summary(self):
        record = OperationRecord(OP_TYPE_ORGANIZE, [])
        s = record.get_summary()
        assert "Organized" in s

    def test_extract_summary(self):
        record = OperationRecord(OP_TYPE_EXTRACT, [])
        s = record.get_summary()
        assert "Extracted" in s

    def test_unknown_type_summary(self):
        record = OperationRecord("unknown_op", [(Path("a"), Path("b"))])
        s = record.get_summary()
        assert "Operation" in s

    def test_summary_includes_timestamp(self):
        record = OperationRecord(OP_TYPE_RENAME, [])
        s = record.get_summary()
        assert str(record.timestamp.year) in s

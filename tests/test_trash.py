"""Comprehensive tests for core/trash.py."""

import datetime

import pytest

from core.trash import TRASH_DIR_NAME, StudioTrash, TrashItem


@pytest.fixture
def trash(tmp_path):
    return StudioTrash(tmp_path)


@pytest.fixture
def sample_file(tmp_path):
    f = tmp_path / "test_file.mov"
    f.write_bytes(b"x" * 1000)
    return f


class TestStudioTrashInit:
    def test_creates_trash_dir(self, tmp_path):
        StudioTrash(tmp_path)
        assert (tmp_path / TRASH_DIR_NAME).is_dir()

    def test_trash_dir_name(self):
        assert TRASH_DIR_NAME == ".pearls_trash"


class TestSendToTrash:
    def test_basic_trash(self, trash, sample_file):
        assert trash.send_to_trash(sample_file) is True
        assert not sample_file.exists()

    def test_file_in_trash_dir(self, trash, sample_file):
        trash.send_to_trash(sample_file)
        items = list(trash.trash_dir.iterdir())
        # Should have the trashed file + .meta.json
        file_items = [i for i in items if not i.name.startswith(".")]
        assert len(file_items) == 1

    def test_metadata_recorded(self, trash, sample_file):
        original_path = str(sample_file)
        trash.send_to_trash(sample_file)
        items = trash.list_trash()
        assert len(items) == 1
        assert items[0].original_path == original_path
        assert items[0].size_bytes == 1000

    def test_nonexistent_file(self, trash, tmp_path):
        result = trash.send_to_trash(tmp_path / "nope.txt")
        assert result is False

    def test_multiple_files(self, trash, tmp_path):
        f1 = tmp_path / "a.mov"
        f2 = tmp_path / "b.mov"
        f1.write_bytes(b"a" * 100)
        f2.write_bytes(b"b" * 200)
        trash.send_to_trash(f1)
        trash.send_to_trash(f2)
        items = trash.list_trash()
        assert len(items) == 2


class TestListTrash:
    def test_empty(self, trash):
        assert trash.list_trash() == []

    def test_returns_trash_items(self, trash, sample_file):
        trash.send_to_trash(sample_file)
        items = trash.list_trash()
        assert all(isinstance(i, TrashItem) for i in items)

    def test_item_fields(self, trash, sample_file):
        trash.send_to_trash(sample_file)
        item = trash.list_trash()[0]
        assert item.trash_name is not None
        assert item.deleted_at is not None
        assert item.size_bytes == 1000


class TestRestore:
    def test_basic_restore(self, trash, sample_file):
        original = str(sample_file)
        trash.send_to_trash(sample_file)
        item = trash.list_trash()[0]
        restored_path = trash.restore(item)
        assert restored_path is not None
        assert restored_path.exists()
        assert str(restored_path) == original

    def test_restore_when_original_occupied(self, trash, sample_file, tmp_path):
        trash.send_to_trash(sample_file)
        # Create new file at original location
        sample_file.write_bytes(b"new content")
        item = trash.list_trash()[0]
        restored = trash.restore(item)
        assert restored is not None
        assert restored.exists()
        assert "_restored" in restored.name
        # Original should still be intact
        assert sample_file.exists()

    def test_restore_removes_from_trash_list(self, trash, sample_file):
        trash.send_to_trash(sample_file)
        item = trash.list_trash()[0]
        trash.restore(item)
        assert len(trash.list_trash()) == 0

    def test_restore_creates_parent_dirs(self, trash, tmp_path):
        sub = tmp_path / "deep" / "path"
        sub.mkdir(parents=True)
        f = sub / "file.txt"
        f.write_text("data")
        trash.send_to_trash(f)
        # Remove the parent dirs
        sub.rmdir()
        (tmp_path / "deep").rmdir()
        item = trash.list_trash()[0]
        restored = trash.restore(item)
        assert restored is not None
        assert restored.exists()


class TestPurge:
    def test_basic_purge(self, trash, sample_file):
        trash.send_to_trash(sample_file)
        item = trash.list_trash()[0]
        assert trash.purge(item) is True
        assert len(trash.list_trash()) == 0

    def test_purge_file_gone(self, trash, sample_file):
        trash.send_to_trash(sample_file)
        item = trash.list_trash()[0]
        # Verify file in trash dir is deleted
        trash.purge(item)
        trash_files = [p for p in trash.trash_dir.iterdir() if not p.name.startswith(".")]
        assert len(trash_files) == 0


class TestAutoPurge:
    def test_purges_old_items(self, trash, sample_file):
        trash.send_to_trash(sample_file)
        # Manually backdate the metadata
        records = trash._load()
        old_date = (datetime.datetime.now() - datetime.timedelta(days=60)).isoformat()
        records[0]["deleted_at"] = old_date
        trash._save(records)
        trash.auto_purge(days=30)
        assert len(trash.list_trash()) == 0

    def test_keeps_recent_items(self, trash, sample_file):
        trash.send_to_trash(sample_file)
        trash.auto_purge(days=30)
        assert len(trash.list_trash()) == 1


class TestTotalSize:
    def test_empty(self, trash):
        assert trash.total_size() == 0

    def test_sums_sizes(self, trash, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"x" * 100)
        f2.write_bytes(b"y" * 200)
        trash.send_to_trash(f1)
        trash.send_to_trash(f2)
        assert trash.total_size() == 300

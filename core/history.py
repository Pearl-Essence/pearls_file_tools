"""Persistent rename history backed by SQLite."""

import sqlite3
from pathlib import Path
from typing import List, Dict
from config import get_data_dir
from models.operation_record import OperationRecord


def get_history_db_path() -> Path:
    return get_data_dir() / 'history.db'


class RenameHistory:
    """Append-only SQLite log of all rename operations."""

    def __init__(self):
        self.db_path = get_history_db_path()
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS renames (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp      TEXT NOT NULL,
                    old_path       TEXT NOT NULL,
                    new_path       TEXT NOT NULL,
                    operation_type TEXT NOT NULL
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON renames (timestamp)')
            conn.commit()

    def log_operation(self, record: OperationRecord):
        """Persist every (old→new) pair from an OperationRecord."""
        ts = record.timestamp.isoformat(timespec='seconds')
        # files_affected is stored as (new_path, old_path) in RenameWorker
        rows = [
            (ts, str(old_path), str(new_path), record.operation_type)
            for new_path, old_path in record.files_affected
        ]
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.executemany(
                    'INSERT INTO renames (timestamp, old_path, new_path, operation_type) '
                    'VALUES (?, ?, ?, ?)',
                    rows
                )
                conn.commit()
        except Exception as e:
            print(f"History log error: {e}")

    def search(self, query: str, limit: int = 500) -> List[Dict]:
        """Full-text search across old_path and new_path columns."""
        pattern = f"%{query}%"
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    'SELECT id, timestamp, old_path, new_path, operation_type '
                    'FROM renames '
                    'WHERE old_path LIKE ? OR new_path LIKE ? '
                    'ORDER BY id DESC LIMIT ?',
                    (pattern, pattern, limit)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_recent(self, limit: int = 500) -> List[Dict]:
        """Return the most recent rename records."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    'SELECT id, timestamp, old_path, new_path, operation_type '
                    'FROM renames ORDER BY id DESC LIMIT ?',
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def clear(self):
        """Delete all history records."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('DELETE FROM renames')
                conn.commit()
        except Exception as e:
            print(f"History clear error: {e}")

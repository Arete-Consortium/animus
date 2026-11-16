"""SQLite FTS5 memory backend — zero-infra full-text search."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class SQLiteMemoryBackend:
    """SQLite FTS5-backed memory store. WAL mode, async via to_thread."""

    VALID_TYPES = ("episodic", "semantic", "procedural")

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);

            CREATE TABLE IF NOT EXISTS user_preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            -- FTS5 virtual table for full-text search
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content,
                content=memories,
                content_rowid=rowid
            );

            -- Triggers to keep FTS index in sync
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content)
                    VALUES('delete', old.rowid, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content)
                    VALUES('delete', old.rowid, old.content);
                INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def store(self, memory_type: str, content: str, metadata: dict) -> str:
        """Store a memory entry, return its ID."""
        return await asyncio.to_thread(self._store_sync, memory_type, content, metadata)

    async def search(self, query: str, memory_type: str = "all", limit: int = 5) -> list[dict]:
        """Search memories via FTS5, ranked by BM25 relevance."""
        return await asyncio.to_thread(self._search_sync, query, memory_type, limit)

    async def get_by_id(self, memory_id: str) -> dict | None:
        """Fetch a single memory by ID. Returns None if not found."""
        return await asyncio.to_thread(self._get_by_id_sync, memory_id)

    async def find_exact(self, memory_type: str, content: str) -> dict | None:
        """Find an exact type/content duplicate without relying on FTS tokenization."""
        return await asyncio.to_thread(self._find_exact_sync, memory_type, content)

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        return await asyncio.to_thread(self._delete_sync, memory_id)

    async def get_stats(self) -> dict:
        """Return memory statistics (counts per type, storage size, preferences)."""
        return await asyncio.to_thread(self._get_stats_sync)

    async def store_preference(self, key: str, value: str) -> None:
        """Store or update a user preference."""
        await asyncio.to_thread(self._store_preference_sync, key, value)

    async def get_preference(self, key: str) -> str | None:
        """Retrieve a user preference by key."""
        return await asyncio.to_thread(self._get_preference_sync, key)

    async def get_all_preferences(self) -> dict[str, str]:
        """Retrieve all user preferences."""
        return await asyncio.to_thread(self._get_all_preferences_sync)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Synchronous implementations
    # ------------------------------------------------------------------

    def _store_sync(self, memory_type: str, content: str, metadata: dict) -> str:
        if memory_type not in self.VALID_TYPES:
            msg = f"Invalid memory type: {memory_type}. Must be one of {self.VALID_TYPES}"
            raise ValueError(msg)

        memory_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO memories (id, type, content, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (memory_id, memory_type, content, json.dumps(metadata), now, now),
        )
        self._conn.commit()
        return memory_id

    def _search_sync(self, query: str, memory_type: str, limit: int) -> list[dict]:
        cur = self._conn.cursor()

        if not query.strip():
            # Empty query: return recent memories
            if memory_type != "all":
                cur.execute(
                    "SELECT id, type, content, metadata, created_at, updated_at "
                    "FROM memories WHERE type = ? ORDER BY updated_at DESC LIMIT ?",
                    (memory_type, limit),
                )
            else:
                cur.execute(
                    "SELECT id, type, content, metadata, created_at, updated_at "
                    "FROM memories ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                )
        else:
            # FTS5 search with BM25 ranking
            escaped = query.replace('"', '""')
            fts_query = f'"{escaped}"'

            if memory_type != "all":
                cur.execute(
                    "SELECT m.id, m.type, m.content, m.metadata, m.created_at, m.updated_at "
                    "FROM memories m "
                    "JOIN memories_fts f ON m.rowid = f.rowid "
                    "WHERE memories_fts MATCH ? AND m.type = ? "
                    "ORDER BY bm25(memories_fts) "
                    "LIMIT ?",
                    (fts_query, memory_type, limit),
                )
            else:
                cur.execute(
                    "SELECT m.id, m.type, m.content, m.metadata, m.created_at, m.updated_at "
                    "FROM memories m "
                    "JOIN memories_fts f ON m.rowid = f.rowid "
                    "WHERE memories_fts MATCH ? "
                    "ORDER BY bm25(memories_fts) "
                    "LIMIT ?",
                    (fts_query, limit),
                )

        return [self._row_to_dict(row) for row in cur.fetchall()]

    def _get_by_id_sync(self, memory_id: str) -> dict | None:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id, type, content, metadata, created_at, updated_at FROM memories WHERE id = ?",
            (memory_id,),
        )
        row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    def _find_exact_sync(self, memory_type: str, content: str) -> dict | None:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id, type, content, metadata, created_at, updated_at "
            "FROM memories WHERE type = ? AND content = ? ORDER BY updated_at LIMIT 1",
            (memory_type, content),
        )
        row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    def _delete_sync(self, memory_id: str) -> bool:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def _get_stats_sync(self) -> dict:
        cur = self._conn.cursor()

        # Counts per type
        type_counts: dict[str, int] = {}
        for memory_type in self.VALID_TYPES:
            cur.execute("SELECT COUNT(*) FROM memories WHERE type = ?", (memory_type,))
            type_counts[memory_type] = cur.fetchone()[0]

        # Total count
        cur.execute("SELECT COUNT(*) FROM memories")
        total = cur.fetchone()[0]

        # Preference count
        cur.execute("SELECT COUNT(*) FROM user_preferences")
        pref_count = cur.fetchone()[0]

        # All preferences
        user_preferences = self._get_all_preferences_sync()

        # Database file size
        try:
            db_size = Path(self._db_path).stat().st_size
        except OSError:
            db_size = 0

        return {
            "total_memories": total,
            "by_type": type_counts,
            "preference_count": pref_count,
            "user_preferences": user_preferences,
            "db_size_bytes": db_size,
        }

    def _store_preference_sync(self, key: str, value: str) -> None:
        now = datetime.now(UTC).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO user_preferences (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
        self._conn.commit()

    def _get_preference_sync(self, key: str) -> str | None:
        cur = self._conn.cursor()
        cur.execute("SELECT value FROM user_preferences WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else None

    def _get_all_preferences_sync(self) -> dict[str, str]:
        cur = self._conn.cursor()
        cur.execute("SELECT key, value FROM user_preferences ORDER BY key")
        return {row[0]: row[1] for row in cur.fetchall()}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "type": row["type"],
            "content": row["content"],
            "metadata": json.loads(row["metadata"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

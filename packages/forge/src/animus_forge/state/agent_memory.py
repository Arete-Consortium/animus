"""Agent memory store with SQLite persistence."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from .backends import DatabaseBackend, SQLiteBackend
from .memory_models import MemoryEntry

logger = logging.getLogger(__name__)


class AgentMemory:
    """Persistent memory store for agents.

    Provides long-term storage and retrieval of agent context,
    learned facts, and conversation history.
    """

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS agent_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            workflow_id TEXT,
            memory_type TEXT NOT NULL DEFAULT 'conversation',
            content TEXT NOT NULL,
            metadata TEXT,
            importance REAL DEFAULT 0.5,
            embedding TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_memories_agent
        ON agent_memories(agent_id, memory_type);

        CREATE INDEX IF NOT EXISTS idx_memories_workflow
        ON agent_memories(workflow_id);

        CREATE INDEX IF NOT EXISTS idx_memories_importance
        ON agent_memories(importance DESC);

        CREATE INDEX IF NOT EXISTS idx_memories_accessed
        ON agent_memories(accessed_at DESC);
    """

    def __init__(self, backend: DatabaseBackend | None = None, db_path: str = "gorgon-memory.db"):
        """Initialize agent memory.

        Args:
            backend: Database backend to use
            db_path: Path to SQLite database (if no backend provided)
        """
        self.backend = backend or SQLiteBackend(db_path=db_path)
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema."""
        self.backend.executescript(self.SCHEMA)

    def store(
        self,
        agent_id: str,
        content: str,
        memory_type: str = "conversation",
        workflow_id: str | None = None,
        metadata: dict | None = None,
        importance: float = 0.5,
    ) -> int:
        """Store a memory entry.

        Args:
            agent_id: Agent identifier
            content: Memory content
            memory_type: Type of memory (conversation, fact, preference, learned)
            workflow_id: Optional workflow context
            metadata: Optional metadata dict
            importance: Importance score (0.0 to 1.0)

        Returns:
            Memory entry ID
        """
        with self.backend.transaction():
            cursor = self.backend.execute(
                """
                INSERT INTO agent_memories
                (agent_id, workflow_id, memory_type, content, metadata, importance)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    workflow_id,
                    memory_type,
                    content,
                    json.dumps(metadata) if metadata else None,
                    importance,
                ),
            )
            return cursor.lastrowid

    def recall(
        self,
        agent_id: str,
        memory_type: str | None = None,
        workflow_id: str | None = None,
        limit: int = 10,
        min_importance: float = 0.0,
        since: datetime | None = None,
    ) -> list[MemoryEntry]:
        """Recall memories for an agent.

        Args:
            agent_id: Agent identifier
            memory_type: Optional filter by memory type
            workflow_id: Optional filter by workflow
            limit: Maximum entries to return
            min_importance: Minimum importance threshold
            since: Only memories created after this time

        Returns:
            List of memory entries
        """
        conditions = ["agent_id = ?"]
        params: list[Any] = [agent_id]

        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type)

        if workflow_id:
            conditions.append("workflow_id = ?")
            params.append(workflow_id)

        if min_importance > 0:
            conditions.append("importance >= ?")
            params.append(min_importance)

        if since:
            conditions.append("created_at >= ?")
            params.append(since.isoformat())

        where_clause = " AND ".join(conditions)
        params.append(limit)

        rows = self.backend.fetchall(
            f"""
            SELECT * FROM agent_memories
            WHERE {where_clause}
            ORDER BY importance DESC, accessed_at DESC
            LIMIT ?
            """,
            tuple(params),
        )

        # Update access timestamps
        if rows:
            ids = [row["id"] for row in rows]
            placeholders = ",".join("?" * len(ids))
            with self.backend.transaction():
                self.backend.execute(
                    f"""
                    UPDATE agent_memories
                    SET accessed_at = CURRENT_TIMESTAMP, access_count = access_count + 1
                    WHERE id IN ({placeholders})
                    """,
                    tuple(ids),
                )

        return [MemoryEntry.from_dict(row) for row in rows]

    def recall_recent(
        self,
        agent_id: str,
        hours: int = 24,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        """Recall recent memories within time window.

        Args:
            agent_id: Agent identifier
            hours: Number of hours to look back
            limit: Maximum entries to return

        Returns:
            List of recent memory entries
        """
        since = datetime.now(UTC) - timedelta(hours=hours)
        return self.recall(agent_id, since=since, limit=limit)

    def recall_context(
        self,
        agent_id: str,
        workflow_id: str | None = None,
        include_facts: bool = True,
        include_preferences: bool = True,
        max_entries: int = 50,
    ) -> dict[str, list[MemoryEntry]]:
        """Recall contextual memories for a workflow.

        Args:
            agent_id: Agent identifier
            workflow_id: Current workflow context
            include_facts: Include learned facts
            include_preferences: Include user preferences
            max_entries: Maximum total entries

        Returns:
            Dictionary of memories by type
        """
        result: dict[str, list[MemoryEntry]] = {}
        remaining = max_entries

        # Get workflow-specific memories first
        if workflow_id:
            workflow_memories = self.recall(
                agent_id,
                workflow_id=workflow_id,
                limit=min(20, remaining),
            )
            if workflow_memories:
                result["workflow"] = workflow_memories
                remaining -= len(workflow_memories)

        # Get high-importance facts
        if include_facts and remaining > 0:
            facts = self.recall(
                agent_id,
                memory_type="fact",
                min_importance=0.7,
                limit=min(15, remaining),
            )
            if facts:
                result["facts"] = facts
                remaining -= len(facts)

        # Get preferences
        if include_preferences and remaining > 0:
            preferences = self.recall(
                agent_id,
                memory_type="preference",
                limit=min(10, remaining),
            )
            if preferences:
                result["preferences"] = preferences
                remaining -= len(preferences)

        # Get recent conversation context
        if remaining > 0:
            recent = self.recall_recent(
                agent_id,
                hours=4,
                limit=remaining,
            )
            if recent:
                # Filter out memory types that were explicitly excluded
                excluded_types: set[str] = set()
                if not include_facts:
                    excluded_types.add("fact")
                if not include_preferences:
                    excluded_types.add("preference")
                if excluded_types:
                    recent = [m for m in recent if m.memory_type not in excluded_types]
                if recent:
                    result["recent"] = recent

        return result

    def forget(
        self,
        agent_id: str,
        memory_id: int | None = None,
        memory_type: str | None = None,
        older_than: datetime | None = None,
        below_importance: float | None = None,
    ) -> int:
        """Remove memories.

        Args:
            agent_id: Agent identifier
            memory_id: Specific memory to remove
            memory_type: Remove all of this type
            older_than: Remove memories older than this
            below_importance: Remove memories below this importance

        Returns:
            Number of memories removed
        """
        conditions = ["agent_id = ?"]
        params: list[Any] = [agent_id]

        if memory_id:
            conditions.append("id = ?")
            params.append(memory_id)

        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type)

        if older_than:
            conditions.append("created_at < ?")
            params.append(older_than.isoformat())

        if below_importance is not None:
            conditions.append("importance < ?")
            params.append(below_importance)

        where_clause = " AND ".join(conditions)

        with self.backend.transaction():
            cursor = self.backend.execute(
                f"DELETE FROM agent_memories WHERE {where_clause}",
                tuple(params),
            )
            return cursor.rowcount

    def consolidate(
        self,
        agent_id: str,
        keep_recent_hours: int = 168,  # 1 week
        min_access_count: int = 2,
    ) -> int:
        """Consolidate old, rarely-accessed memories.

        Removes old memories that haven't been accessed frequently,
        keeping important and frequently-used ones.

        Args:
            agent_id: Agent identifier
            keep_recent_hours: Keep all memories newer than this
            min_access_count: Minimum accesses to keep old memories

        Returns:
            Number of memories removed
        """
        cutoff = datetime.now(UTC) - timedelta(hours=keep_recent_hours)

        with self.backend.transaction():
            cursor = self.backend.execute(
                """
                DELETE FROM agent_memories
                WHERE agent_id = ?
                AND created_at < ?
                AND access_count < ?
                AND importance < 0.8
                AND memory_type NOT IN ('fact', 'preference')
                """,
                (agent_id, cutoff.isoformat(), min_access_count),
            )
            return cursor.rowcount

    def update_importance(
        self,
        memory_id: int,
        importance: float,
    ) -> bool:
        """Update memory importance score.

        Args:
            memory_id: Memory entry ID
            importance: New importance score (0.0 to 1.0)

        Returns:
            True if updated
        """
        with self.backend.transaction():
            cursor = self.backend.execute(
                "UPDATE agent_memories SET importance = ? WHERE id = ?",
                (importance, memory_id),
            )
            return cursor.rowcount > 0

    def get_stats(self, agent_id: str) -> dict:
        """Get memory statistics for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Dictionary with memory stats
        """
        total = self.backend.fetchone(
            "SELECT COUNT(*) as count FROM agent_memories WHERE agent_id = ?",
            (agent_id,),
        )

        by_type = self.backend.fetchall(
            """
            SELECT memory_type, COUNT(*) as count
            FROM agent_memories
            WHERE agent_id = ?
            GROUP BY memory_type
            """,
            (agent_id,),
        )

        avg_importance = self.backend.fetchone(
            "SELECT AVG(importance) as avg FROM agent_memories WHERE agent_id = ?",
            (agent_id,),
        )

        return {
            "total_memories": total["count"] if total else 0,
            "by_type": {row["memory_type"]: row["count"] for row in by_type},
            "average_importance": round(avg_importance["avg"] or 0, 2) if avg_importance else 0,
        }

    def format_context(self, memories: dict[str, list[MemoryEntry]]) -> str:
        """Format memories as context string for agent prompts.

        Args:
            memories: Dictionary of memories by category

        Returns:
            Formatted context string
        """
        parts = []

        if "facts" in memories:
            facts_text = "\n".join(f"- {m.content}" for m in memories["facts"])
            parts.append(f"Known Facts:\n{facts_text}")

        if "preferences" in memories:
            prefs_text = "\n".join(f"- {m.content}" for m in memories["preferences"])
            parts.append(f"User Preferences:\n{prefs_text}")

        if "workflow" in memories:
            workflow_text = "\n".join(f"- {m.content}" for m in memories["workflow"][:5])
            parts.append(f"Current Workflow Context:\n{workflow_text}")

        if "recent" in memories:
            recent_text = "\n".join(f"- {m.content}" for m in memories["recent"][:5])
            parts.append(f"Recent Context:\n{recent_text}")

        return "\n\n".join(parts)

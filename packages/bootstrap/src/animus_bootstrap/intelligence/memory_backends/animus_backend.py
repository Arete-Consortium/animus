"""Animus Core memory backend — delegates to the core exocortex memory layer."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AnimusMemoryBackend:
    """Backend that delegates to animus core's MemoryLayer.

    Wraps the synchronous Core API with ``asyncio.to_thread`` so it
    can be used from Bootstrap's async intelligence layer.

    Args:
        data_dir: Directory where Core persists memory data.
    """

    VALID_TYPES = ("episodic", "semantic", "procedural")

    # Maps Bootstrap type strings -> Core MemoryType enum members.
    # Populated lazily in __init__ after the import succeeds.
    _TYPE_MAP: dict[str, Any] = {}

    def __init__(self, data_dir: Path | str) -> None:
        try:
            from animus.memory import MemoryLayer, MemoryType
        except ImportError:
            msg = "animus-core is not installed. Install it with: pip install animus-core"
            raise RuntimeError(msg) from None

        self._type_map: dict[str, Any] = {
            "episodic": MemoryType.EPISODIC,
            "semantic": MemoryType.SEMANTIC,
            "procedural": MemoryType.PROCEDURAL,
        }
        self._memory_type_cls = MemoryType

        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        # Core 2.3 removed the ambiguous ``auto`` backend.  Bootstrap selects
        # this adapter only when the operator explicitly chooses the Animus
        # backend, so use Core's local store here; durable storage needs a
        # separately configured database and migration gate.
        self._core = MemoryLayer(data_dir=self._data_dir, backend="local")
        logger.info("AnimusMemoryBackend initialized at %s", self._data_dir)

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def store(self, memory_type: str, content: str, metadata: dict) -> str:
        """Store a memory entry, return its ID.

        Args:
            memory_type: One of "episodic", "semantic", "procedural".
            content: The text content to remember.
            metadata: Arbitrary metadata dict.

        Returns:
            The ID of the newly created memory.

        Raises:
            ValueError: If *memory_type* is not recognised.
        """
        return await asyncio.to_thread(self._store_sync, memory_type, content, metadata)

    async def search(
        self,
        query: str,
        memory_type: str = "all",
        limit: int = 5,
    ) -> list[dict]:
        """Search memories via the core memory layer.

        Args:
            query: Free-text search query.
            memory_type: Filter by type, or "all" for everything.
            limit: Maximum number of results.

        Returns:
            List of memory dicts with standard keys.
        """
        return await asyncio.to_thread(self._search_sync, query, memory_type, limit)

    async def get_by_id(self, memory_id: str) -> dict | None:
        """Fetch a single memory by ID. Returns None if not found."""
        return await asyncio.to_thread(self._get_by_id_sync, memory_id)

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID.

        Args:
            memory_id: The UUID of the memory to delete.

        Returns:
            ``True`` if the memory was found and deleted.
        """
        return await asyncio.to_thread(self._delete_sync, memory_id)

    async def get_stats(self) -> dict:
        """Return backend statistics.

        Returns:
            Dict with total count, per-type counts, and backend info.
        """
        return await asyncio.to_thread(self._get_stats_sync)

    def close(self) -> None:
        """Close the backend and release resources."""
        logger.info("AnimusMemoryBackend closed")

    # ------------------------------------------------------------------
    # Synchronous implementations
    # ------------------------------------------------------------------

    def _resolve_type(self, memory_type: str) -> Any:
        """Convert a Bootstrap type string to a Core MemoryType enum.

        Raises:
            ValueError: If the type string is not recognised.
        """
        core_type = self._type_map.get(memory_type)
        if core_type is None:
            msg = f"Invalid memory type: {memory_type!r}. Must be one of {self.VALID_TYPES}"
            raise ValueError(msg)
        return core_type

    def _store_sync(self, memory_type: str, content: str, metadata: dict) -> str:
        core_type = self._resolve_type(memory_type)

        # Extract optional fields from metadata so they flow through
        # to Core's richer Memory model.
        tags = metadata.pop("tags", None)
        source = metadata.pop("source", "stated")
        confidence = metadata.pop("confidence", 1.0)
        subtype = metadata.pop("subtype", None)

        memory = self._core.remember(
            content=content,
            memory_type=core_type,
            metadata=metadata,
            tags=tags,
            source=source,
            confidence=confidence,
            subtype=subtype,
        )
        return memory.id

    def _search_sync(self, query: str, memory_type: str, limit: int) -> list[dict]:
        core_type = self._resolve_type(memory_type) if memory_type != "all" else None
        memories = self._core.recall(
            query=query,
            memory_type=core_type,
            limit=limit,
        )
        return [self._memory_to_dict(m) for m in memories]

    def _get_by_id_sync(self, memory_id: str) -> dict | None:
        try:
            memory = self._core.store.get(memory_id)
        except (AttributeError, KeyError, ValueError):
            return None
        if memory is None:
            return None
        return self._memory_to_dict(memory)

    def _delete_sync(self, memory_id: str) -> bool:
        return self._core.store.delete(memory_id)

    def _get_stats_sync(self) -> dict:
        type_counts: dict[str, int] = {}
        total = 0
        for type_str, core_type in self._type_map.items():
            count = len(self._core.store.list_all(memory_type=core_type))
            type_counts[type_str] = count
            total += count

        return {
            "total_memories": total,
            "by_type": type_counts,
            "backend": "animus-core",
            "data_dir": str(self._data_dir),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _memory_to_dict(memory: Any) -> dict:
        """Convert a Core Memory object to the Bootstrap dict format."""
        d = memory.to_dict()
        # Normalise key names to match Bootstrap's expected schema.
        return {
            "id": d["id"],
            "type": d["memory_type"],
            "content": d["content"],
            "metadata": d.get("metadata", {}),
            "created_at": d["created_at"],
            "updated_at": d["updated_at"],
        }

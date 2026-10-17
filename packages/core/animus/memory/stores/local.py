"""JSON-file-backed memory store used by the default supported Core backend."""

from __future__ import annotations

import json
from pathlib import Path

from animus.logging import get_logger
from animus.memory.stores.base import MemoryStore
from animus.memory.types import Memory, MemoryType, Sensitivity

logger = get_logger("memory")


class LocalMemoryStore(MemoryStore):
    """
    Simple local file-based memory store.

    Uses substring matching for search.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.memories_file = data_dir / "memories.json"
        self._memories: dict[str, Memory] = {}
        self._load()
        logger.debug(f"LocalMemoryStore initialized at {data_dir}")

    def _load(self):
        """Load memories from disk."""
        if self.memories_file.exists():
            with open(self.memories_file) as f:
                data = json.load(f)
                self._memories = {k: Memory.from_dict(v) for k, v in data.items()}
            logger.info(f"Loaded {len(self._memories)} memories from disk")

    def _save(self):
        """Save memories to disk atomically.

        Writes to a temporary file then renames for crash safety.
        Uses compact JSON (no indent) for faster serialization.
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = self.memories_file.with_suffix(".tmp")
        with open(tmp_file, "w") as f:
            json.dump({k: v.to_dict() for k, v in self._memories.items()}, f)
        tmp_file.replace(self.memories_file)

    def store(self, memory: Memory) -> None:
        self._memories[memory.id] = memory
        self._save()
        logger.debug(f"Stored memory {memory.id[:8]}")

    def update(self, memory: Memory) -> bool:
        if memory.id in self._memories:
            self._memories[memory.id] = memory
            self._save()
            logger.debug(f"Updated memory {memory.id[:8]}")
            return True
        return False

    def retrieve(self, memory_id: str) -> Memory | None:
        return self._memories.get(memory_id)

    def search(
        self,
        query: str,
        memory_type: MemoryType | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 10,
        allowed_tiers: set[Sensitivity] | None = None,
    ) -> list[Memory]:
        """Substring search with filters.

        ``allowed_tiers`` restricts results to memories whose sensitivity is
        in the set. ``None`` skips the filter (backward-compat).
        """
        results = []
        query_lower = query.lower()

        for memory in self._memories.values():
            # Apply filters
            if memory_type and memory.memory_type != memory_type:
                continue
            if tags and not all(t in memory.tags for t in tags):
                continue
            if source and memory.source != source:
                continue
            if memory.confidence < min_confidence:
                continue
            if allowed_tiers is not None and memory.sensitivity not in allowed_tiers:
                continue
            # Content match
            if query_lower in memory.content.lower():
                results.append(memory)
            if len(results) >= limit:
                break

        logger.debug("Search found %d results", len(results))
        return results

    def delete(self, memory_id: str) -> bool:
        if memory_id in self._memories:
            del self._memories[memory_id]
            self._save()
            logger.debug(f"Deleted memory {memory_id[:8]}")
            return True
        return False

    def list_all(self, memory_type: MemoryType | None = None) -> list[Memory]:
        if memory_type:
            return [m for m in self._memories.values() if m.memory_type == memory_type]
        return list(self._memories.values())

    def get_all_tags(self) -> dict[str, int]:
        """Get all tags with counts."""
        tag_counts: dict[str, int] = {}
        for memory in self._memories.values():
            for tag in memory.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return tag_counts

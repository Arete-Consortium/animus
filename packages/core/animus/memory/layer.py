"""MemoryLayer — the public façade over a pluggable MemoryStore backend."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from animus.logging import get_logger
from animus.memory.redaction import redact
from animus.memory.tier import TierManager
from animus.memory.types import (
    Conversation,
    Memory,
    MemoryTier,
    MemoryType,
    Procedure,
    SemanticFact,
    Sensitivity,
)

if TYPE_CHECKING:
    from animus.entities import EntityMemory
    from animus.protocols.memory import MemoryProvider

logger = get_logger("memory")


class MemoryLayer:
    """
    Main memory layer interface.

    Coordinates between different memory types and storage backends.
    """

    def __init__(
        self,
        data_dir: Path,
        backend: str = "chroma",
        entity_memory: EntityMemory | None = None,
        auto_discover_entities: bool = False,
    ):
        self.data_dir = data_dir
        self.backend_type = backend
        self.entity_memory = entity_memory
        self.auto_discover_entities = auto_discover_entities

        # Resolve store classes via the package namespace so test mocks like
        # `patch("animus.memory.ChromaMemoryStore")` hit the name MemoryLayer
        # actually reads (the classic "patch where it's looked up" rule).
        import animus.memory as _memory

        self.store: MemoryProvider
        if backend == "chroma":
            try:
                self.store = _memory.ChromaMemoryStore(data_dir)
            except ImportError as exc:
                raise RuntimeError(
                    "The configured Chroma memory backend is unavailable. "
                    "Install animus-core[chroma] for an existing Chroma deployment, "
                    "or explicitly configure a different backend for a new installation. "
                    "Existing memories have not been migrated; no fallback store was opened."
                ) from exc
        elif backend == "durable":
            if _memory.DurableMemoryStore is None:
                raise RuntimeError(
                    "DurableMemoryStore requires sqlalchemy. Install: pip install animus[postgres]"
                )
            # Durable store reads database_url from ANIMUS_DATABASE_URL env var
            # or ObjectStoreConfig; data_dir is ignored.
            self.store = _memory.DurableMemoryStore()
            self.store.create_tables()
        else:
            self.store = _memory.LocalMemoryStore(data_dir)

        self.tier_manager = TierManager(self)
        logger.info(f"MemoryLayer initialized with {type(self.store).__name__}")

    def remember(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        metadata: dict | None = None,
        tags: list[str] | None = None,
        source: str = "stated",
        confidence: float = 1.0,
        subtype: str | None = None,
        provenance: str = "direct",
        sensitivity: Sensitivity = Sensitivity.PUBLIC,
        tier: MemoryTier = MemoryTier.WARM,
    ) -> Memory:
        """
        Store a new memory.

        Args:
            content: The content to remember
            memory_type: Type of memory
            metadata: Optional additional data
            tags: Optional list of tags
            source: How the memory was acquired (stated/inferred/learned)
            confidence: Confidence level 0.0-1.0
            subtype: Optional subtype (e.g., "fact", "preference")
            provenance: Origin of the memory (direct/sync/consolidation/import/mcp)
            sensitivity: Disclosure tier (PUBLIC/PERSONAL/CONFIDENTIAL/SECRET).
                Defaults to PUBLIC; callers handling private material should
                set this explicitly. Read-side filtering happens via
                ``recall(allowed_tiers=...)``.
            tier: Temperature tier (HOT/WARM/COLD). Defaults to WARM.

        Returns:
            The created Memory object
        """
        now = datetime.now()
        normalized_tags = [t.lower().strip() for t in (tags or []) if t.strip()]

        redacted_content, hits = redact(content)
        combined_metadata = dict(metadata or {})
        if hits:
            combined_metadata["_redaction_count"] = len(hits)
            combined_metadata["_redaction_types"] = ",".join(sorted({h.type for h in hits}))
            logger.info(
                "redacted %d secret(s) from memory ingest: %s",
                len(hits),
                combined_metadata["_redaction_types"],
            )

        memory = Memory(
            id=str(uuid.uuid4()),
            content=redacted_content,
            memory_type=memory_type,
            created_at=now,
            updated_at=now,
            metadata=combined_metadata,
            tags=normalized_tags,
            source=source,
            confidence=confidence,
            subtype=subtype,
            provenance=provenance,
            sensitivity=sensitivity,
            tier=tier,
        )

        self.store.store(memory)
        # SEC-08: do not emit any content text in logs; use safe metadata only.
        logger.info(
            "Remembered %s memory (id=%s, redactions=%d)",
            memory_type.value,
            memory.id,
            combined_metadata.get("_redaction_count", 0),
        )

        # Link entities mentioned in the content to this memory
        if self.entity_memory:
            try:
                self.entity_memory.extract_and_link(
                    content,
                    memory_id=memory.id,
                    auto_discover=self.auto_discover_entities,
                )
            except Exception as e:
                logger.debug(f"Entity linking during remember failed: {e}")

        return memory

    def remember_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        category: str = "fact",
        confidence: float = 1.0,
        source: str = "stated",
        tags: list[str] | None = None,
    ) -> Memory:
        """
        Store a structured semantic fact.

        Args:
            subject: The subject of the fact
            predicate: The relationship/verb
            obj: The object of the fact
            category: fact | preference | entity | relationship
            confidence: Confidence level
            source: How acquired
            tags: Optional tags

        Returns:
            The created Memory object
        """
        fact = SemanticFact(
            subject=subject,
            predicate=predicate,
            obj=obj,
            category=category,
            confidence=confidence,
            source=source,
        )

        return self.remember(
            content=fact.to_content(),
            memory_type=MemoryType.SEMANTIC,
            metadata=fact.to_metadata(),
            tags=tags,
            source=source,
            confidence=confidence,
            subtype=category,
        )

    def remember_procedure(
        self,
        name: str,
        trigger: str,
        steps: list[str],
        tags: list[str] | None = None,
    ) -> Memory:
        """
        Store a procedural memory (workflow/pattern).

        Args:
            name: Name of the procedure
            trigger: What triggers this procedure
            steps: List of steps to execute
            tags: Optional tags

        Returns:
            The created Memory object
        """
        procedure = Procedure(name=name, trigger=trigger, steps=steps)

        return self.remember(
            content=procedure.to_content(),
            memory_type=MemoryType.PROCEDURAL,
            metadata=procedure.to_metadata(),
            tags=tags,
            source="stated",
            confidence=1.0,
            subtype="workflow",
        )

    def recall(
        self,
        query: str,
        memory_type: MemoryType | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 10,
        allowed_tiers: set[Sensitivity] | None = None,
        tier: MemoryTier | None = None,
    ) -> list[Memory]:
        """
        Retrieve relevant memories with optional filters.

        Args:
            query: What to search for
            memory_type: Optional filter by type
            tags: Optional filter by tags (all must match)
            source: Optional filter by source
            min_confidence: Minimum confidence threshold
            limit: Maximum results
            allowed_tiers: Disclosure tiers permitted for this caller. When
                provided, results are filtered to memories whose
                ``sensitivity`` is in the set.

                Security contract: ``None`` (the default) returns ALL tiers
                and is correct ONLY for in-process, local-owner reads (CLI,
                learning loop, the owner's own API) where the caller already
                has full access to the underlying store. Any surface that can
                egress data (MCP tools, automation, anything a non-owner can
                reach) MUST pass an explicit tier set and must never rely on
                this default. Egress callers should use
                :meth:`recall_for_egress`, which pins ``{Sensitivity.PUBLIC}``
                in one place so a new egress site cannot accidentally widen the
                scope.
            tier: Optional temperature tier filter (HOT/WARM/COLD).

        Returns:
            List of relevant memories
        """
        results = self.store.search(
            query,
            memory_type,
            tags,
            source,
            min_confidence,
            limit,
            allowed_tiers=allowed_tiers,
        )

        # D2 — temperature-based filtering and ranking
        if tier is not None:
            results = [m for m in results if m.tier == tier]
        for mem in results:
            self.tier_manager.on_access(mem)
        results = self.tier_manager.rerank_for_tier(results)

        return results[:limit]

    def search(
        self,
        query: str,
        memory_type: MemoryType | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 10,
        allowed_tiers: set[Sensitivity] | None = None,
        tier: MemoryTier | None = None,
    ) -> list[Memory]:
        """Alias for :meth:`recall` — backward compatibility for citizen callers.

        Citizens and legacy code call ``memory.search(...)``; ``MemoryLayer``
        exposes ``recall(...)`` as the canonical name. This alias bridges the
        gap so existing callers don't need to be rewritten.
        """
        return self.recall(
            query,
            memory_type=memory_type,
            tags=tags,
            source=source,
            min_confidence=min_confidence,
            limit=limit,
            allowed_tiers=allowed_tiers,
            tier=tier,
        )

    def recall_by_tags(
        self,
        tags: list[str],
        limit: int = 10,
        allowed_tiers: set[Sensitivity] | None = None,
    ) -> list[Memory]:
        """Retrieve memories that have all specified tags.

        ``allowed_tiers`` (Stage 2.B) restricts results to memories whose
        ``sensitivity`` is in the set. ``None`` skips the filter
        (backward-compat for pre-Stage-2.B callers).
        """
        all_memories = self.store.list_all()
        matching = [m for m in all_memories if all(t in m.tags for t in tags)]
        if allowed_tiers is not None:
            matching = [m for m in matching if m.sensitivity in allowed_tiers]
        return matching[:limit]

    # ------------------------------------------------------------------
    # Egress-safe reads. These pin the disclosure scope to PUBLIC in ONE
    # place so any surface that can leave the box (MCP tools, automation)
    # cannot fat-finger a wider tier set at a new call site. Egress code
    # must call these rather than passing ``allowed_tiers`` by hand.
    # ------------------------------------------------------------------

    #: The only disclosure scope permitted to cross an egress boundary.
    EGRESS_SCOPE: ClassVar[set[Sensitivity]] = {Sensitivity.PUBLIC}

    def recall_for_egress(
        self,
        query: str,
        memory_type: MemoryType | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> list[Memory]:
        """Egress-safe :meth:`recall` pinned to ``{Sensitivity.PUBLIC}``."""
        return self.recall(
            query,
            memory_type=memory_type,
            tags=tags,
            source=source,
            min_confidence=min_confidence,
            limit=limit,
            allowed_tiers=set(self.EGRESS_SCOPE),
        )

    def recall_by_tags_for_egress(
        self,
        tags: list[str],
        limit: int = 10,
    ) -> list[Memory]:
        """Egress-safe :meth:`recall_by_tags` pinned to ``{Sensitivity.PUBLIC}``."""
        return self.recall_by_tags(
            tags,
            limit=limit,
            allowed_tiers=set(self.EGRESS_SCOPE),
        )

    def get_memory(self, memory_id: str) -> Memory | None:
        """Get a specific memory by ID or partial ID.

        Records an access for tier-tracking purposes.
        """
        # Try exact match first
        memory = self.store.retrieve(memory_id)
        if memory:
            self.tier_manager.on_access(memory)
            return memory
        # Try partial match
        for mem in self.store.list_all():
            if mem.id.startswith(memory_id):
                self.tier_manager.on_access(mem)
                return mem
        return None

    def promote_memory(self, memory_id: str) -> bool:
        """Explicitly promote a memory to the next tier (max HOT).

        Does not trigger access tracking — this is an administrative
        operation, not a recall.
        """
        memory = self.store.retrieve(memory_id)
        if not memory:
            # Try partial match
            for mem in self.store.list_all():
                if mem.id.startswith(memory_id):
                    memory = mem
                    break
        if not memory:
            return False
        if memory.tier == MemoryTier.COLD:
            memory.tier = MemoryTier.WARM
        elif memory.tier == MemoryTier.WARM:
            memory.tier = MemoryTier.HOT
        else:
            return True  # Already HOT
        return self.update_memory(memory)

    def demote_memory(self, memory_id: str) -> bool:
        """Explicitly demote a memory to the previous tier (min COLD).

        Does not trigger access tracking — this is an administrative
        operation, not a recall.
        """
        memory = self.store.retrieve(memory_id)
        if not memory:
            for mem in self.store.list_all():
                if mem.id.startswith(memory_id):
                    memory = mem
                    break
        if not memory:
            return False
        if memory.tier == MemoryTier.HOT:
            memory.tier = MemoryTier.WARM
        elif memory.tier == MemoryTier.WARM:
            memory.tier = MemoryTier.COLD
        else:
            return True  # Already COLD
        return self.update_memory(memory)

    def run_tier_review(self) -> tuple[int, int]:
        """Run the periodic tier review (demote stale, enforce HOT cap).

        Returns:
            (demoted_count, promoted_count)
        """
        return self.tier_manager.review()

    def update_memory(self, memory: Memory) -> bool:
        """Update an existing memory."""
        memory.updated_at = datetime.now()
        return self.store.update(memory)

    def add_tag(self, memory_id: str, tag: str) -> bool:
        """Add a tag to a memory."""
        memory = self.get_memory(memory_id)
        if memory:
            memory.add_tag(tag)
            return self.update_memory(memory)
        return False

    def remove_tag(self, memory_id: str, tag: str) -> bool:
        """Remove a tag from a memory."""
        memory = self.get_memory(memory_id)
        if memory:
            if memory.remove_tag(tag):
                return self.update_memory(memory)
        return False

    def get_all_tags(self) -> dict[str, int]:
        """Get all tags with their usage counts."""
        return self.store.get_all_tags()

    def update_with_version(
        self,
        memory_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        change_summary: str | None = None,
        provenance: str = "direct",
    ) -> Memory | None:
        """Create a new versioned memory that supersedes an existing one.

        Instead of mutating in place, this creates a NEW memory with
        ``parent_id`` pointing to the old one and an incremented ``version``.

        Args:
            memory_id: ID (or prefix) of the memory to update.
            content: New content (uses parent content if None).
            tags: New tags (uses parent tags if None).
            metadata: New metadata (uses parent metadata if None).
            change_summary: Human-readable description of the delta.
            provenance: Origin of the change.

        Returns:
            The newly created Memory, or None if the parent was not found.
        """
        parent = self.get_memory(memory_id)
        if not parent:
            return None

        new_content = content if content is not None else parent.content
        new_tags = tags if tags is not None else list(parent.tags)
        new_metadata = metadata if metadata is not None else dict(parent.metadata)

        # Auto-generate change_summary when not provided
        if change_summary is None:
            parts: list[str] = []
            if content is not None and content != parent.content:
                parts.append("content updated")
            if tags is not None and set(tags) != set(parent.tags):
                parts.append("tags changed")
            if metadata is not None and metadata != parent.metadata:
                parts.append("metadata changed")
            change_summary = "; ".join(parts) if parts else "no-op version bump"

        now = datetime.now()
        normalized_tags = [t.lower().strip() for t in new_tags if t.strip()]

        new_memory = Memory(
            id=str(uuid.uuid4()),
            content=new_content,
            memory_type=parent.memory_type,
            created_at=now,
            updated_at=now,
            metadata=new_metadata,
            tags=normalized_tags,
            source=parent.source,
            confidence=parent.confidence,
            subtype=parent.subtype,
            version=parent.version + 1,
            parent_id=parent.id,
            change_summary=change_summary,
            provenance=provenance,
        )

        self.store.store(new_memory)
        logger.info(
            f"Created version {new_memory.version} of memory {parent.id[:8]} -> {new_memory.id[:8]}"
        )
        return new_memory

    def get_version_history(self, memory_id: str, limit: int = 10) -> list[Memory]:
        """Walk the parent_id chain and return version history (newest first).

        Args:
            memory_id: ID (or prefix) of any memory in the chain.
            limit: Maximum number of versions to return.

        Returns:
            List of Memory objects ordered newest-first.
        """
        history: list[Memory] = []
        current = self.get_memory(memory_id)
        while current and len(history) < limit:
            history.append(current)
            if current.parent_id:
                current = self.get_memory(current.parent_id)
            else:
                break
        return history

    def snapshot(self, label: str) -> dict:
        """Export all memories to a timestamped snapshot file.

        Args:
            label: Human-readable label for the snapshot.

        Returns:
            Metadata dict with label, timestamp, memory_count, and path.
        """
        now = datetime.now()
        timestamp = now.strftime("%Y%m%dT%H%M%S")
        all_memories = self.store.list_all()

        snapshot_data = {
            "label": label,
            "timestamp": now.isoformat(),
            "memory_count": len(all_memories),
            "memories": [m.to_dict() for m in all_memories],
        }

        snapshots_dir = self.data_dir / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshots_dir / f"{label}_{timestamp}.json"
        snapshot_path.write_text(json.dumps(snapshot_data, indent=2))

        logger.info(f"Snapshot '{label}' saved: {len(all_memories)} memories -> {snapshot_path}")
        return {
            "label": label,
            "timestamp": now.isoformat(),
            "memory_count": len(all_memories),
            "path": str(snapshot_path),
        }

    def restore_snapshot(self, snapshot_path: str) -> int:
        """Restore memories from a snapshot file.

        Clears the current collection and imports all memories from the
        snapshot.

        Args:
            snapshot_path: Path to the snapshot JSON file.

        Returns:
            Number of memories restored.
        """
        path = Path(snapshot_path)
        if not path.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

        snapshot_data = json.loads(path.read_text())
        memories_data = snapshot_data.get("memories", [])

        # Clear current collection
        for mem in self.store.list_all():
            self.store.delete(mem.id)

        # Import all memories from snapshot
        count = 0
        for item in memories_data:
            memory = Memory.from_dict(item)
            self.store.store(memory)
            count += 1

        logger.info(f"Restored snapshot '{snapshot_data.get('label', '?')}': {count} memories")
        return count

    def forget(self, memory_id: str) -> bool:
        """Delete a specific memory and clean up entity references."""
        # Try partial match
        memory = self.get_memory(memory_id)
        if memory:
            deleted = self.store.delete(memory.id)
            if deleted and self.entity_memory:
                try:
                    self.entity_memory.remove_interactions_for_memory(memory.id)
                except Exception as e:
                    logger.debug(f"Entity cleanup during forget failed: {e}")
            return deleted
        return False

    def save_conversation(self, conversation: Conversation) -> Memory:
        """Save a conversation as an episodic memory.

        Entity linking is handled by remember() automatically.
        """
        conversation.ended_at = datetime.now()
        content = conversation.to_memory_content()

        return self.remember(
            content=content,
            memory_type=MemoryType.EPISODIC,
            metadata={
                "conversation_id": conversation.id,
                "message_count": len(conversation.messages),
                "duration_seconds": (
                    conversation.ended_at - conversation.started_at
                ).total_seconds(),
            },
            subtype="conversation",
        )

    # Export/Import functionality

    def export_memories(self, format: str = "json") -> str:
        """
        Export all memories to string format.

        Args:
            format: "json" or "jsonl"

        Returns:
            Exported data as string
        """
        memories = self.store.list_all()
        data = [m.to_dict() for m in memories]

        if format == "jsonl":
            return "\n".join(json.dumps(m) for m in data)
        else:
            return json.dumps(data, indent=2)

    def import_memories(self, data: str, format: str = "json") -> int:
        """
        Import memories from string data.

        Args:
            data: The data to import
            format: "json" or "jsonl"

        Returns:
            Number of memories imported
        """
        if format == "jsonl":
            items = [json.loads(line) for line in data.strip().split("\n") if line.strip()]
        else:
            items = json.loads(data)

        count = 0
        for item in items:
            memory = Memory.from_dict(item)
            self.store.store(memory)
            count += 1

            # Link entities mentioned in the imported memory
            if self.entity_memory:
                try:
                    self.entity_memory.extract_and_link(
                        memory.content,
                        memory_id=memory.id,
                        auto_discover=self.auto_discover_entities,
                    )
                except Exception as e:
                    logger.debug(f"Entity linking during import failed: {e}")

        logger.info(f"Imported {count} memories")
        return count

    def backup(self, backup_path: Path) -> None:
        """
        Create a full backup of the data directory.

        Args:
            backup_path: Path for the backup archive
        """
        backup_path = Path(backup_path)
        if backup_path.suffix != ".zip":
            backup_path = backup_path.with_suffix(".zip")

        shutil.make_archive(str(backup_path.with_suffix("")), "zip", self.data_dir)
        logger.info(f"Created backup at {backup_path}")

    def get_statistics(self) -> dict:
        """Get memory statistics."""
        all_memories = self.store.list_all()
        tags = self.get_all_tags()

        by_type = {}
        by_source = {}
        by_subtype = {}
        total_confidence = 0.0

        for mem in all_memories:
            by_type[mem.memory_type.value] = by_type.get(mem.memory_type.value, 0) + 1
            by_source[mem.source] = by_source.get(mem.source, 0) + 1
            if mem.subtype:
                by_subtype[mem.subtype] = by_subtype.get(mem.subtype, 0) + 1
            total_confidence += mem.confidence

        # Version statistics
        total_versions = sum(m.version for m in all_memories)
        memories_with_history = sum(1 for m in all_memories if m.parent_id is not None)
        by_provenance: dict[str, int] = {}
        by_tier: dict[str, int] = {}
        for mem in all_memories:
            by_provenance[mem.provenance] = by_provenance.get(mem.provenance, 0) + 1
            by_tier[mem.tier.value] = by_tier.get(mem.tier.value, 0) + 1

        return {
            "total": len(all_memories),
            "by_type": by_type,
            "by_source": by_source,
            "by_subtype": by_subtype,
            "by_tier": by_tier,
            "avg_confidence": total_confidence / len(all_memories) if all_memories else 0,
            "unique_tags": len(tags),
            "top_tags": sorted(tags.items(), key=lambda x: x[1], reverse=True)[:10],
            "total_versions": total_versions,
            "memories_with_history": memories_with_history,
            "by_provenance": by_provenance,
        }

    def consolidate(self, max_age_days: int = 90, min_group_size: int = 3) -> int:
        """
        Consolidate memories by grouping related older memories into summaries.

        Groups episodic memories that share tags and are older than max_age_days,
        then replaces each group with a single summary memory.

        Args:
            max_age_days: Only consolidate memories older than this many days
            min_group_size: Minimum group size required to trigger consolidation

        Returns:
            Number of memories consolidated (removed)
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=max_age_days)
        all_memories = self.store.list_all(memory_type=MemoryType.EPISODIC)

        # Filter to old memories
        old_memories = [m for m in all_memories if m.created_at < cutoff]
        if not old_memories:
            logger.info("No memories old enough to consolidate")
            return 0

        # Group by primary tag (first tag, or "untagged")
        groups: dict[str, list[Memory]] = {}
        for mem in old_memories:
            group_key = mem.tags[0] if mem.tags else "untagged"
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(mem)

        consolidated_count = 0
        for group_key, memories in groups.items():
            if len(memories) < min_group_size:
                continue

            # Sort by date
            memories.sort(key=lambda m: m.created_at)
            date_range = (
                f"{memories[0].created_at.strftime('%Y-%m-%d')} to "
                f"{memories[-1].created_at.strftime('%Y-%m-%d')}"
            )

            # Build summary from content snippets
            snippets = [m.content[:150] for m in memories]
            summary_content = (
                f"Consolidated summary ({date_range}, {len(memories)} items, "
                f"tag: {group_key}):\n- " + "\n- ".join(snippets)
            )

            # Collect all tags from the group
            all_tags: set[str] = set()
            for mem in memories:
                all_tags.update(mem.tags)
            all_tags.add("consolidated")

            # Create summary memory
            self.remember(
                content=summary_content,
                memory_type=MemoryType.EPISODIC,
                tags=list(all_tags),
                source="learned",
                confidence=0.9,
                subtype="consolidated",
                provenance="consolidation",
            )

            # Remove originals and clean up entity references
            for mem in memories:
                self.store.delete(mem.id)
                if self.entity_memory:
                    try:
                        self.entity_memory.remove_interactions_for_memory(mem.id)
                    except Exception as e:
                        logger.debug(f"Entity cleanup during consolidation failed: {e}")
                consolidated_count += 1

        logger.info(f"Consolidated {consolidated_count} memories into summaries")
        return consolidated_count

    def export_memories_csv(self) -> str:
        """
        Export all memories to CSV format.

        Returns:
            CSV string with headers
        """
        import csv
        import io

        memories = self.store.list_all()
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(
            [
                "id",
                "content",
                "memory_type",
                "created_at",
                "updated_at",
                "tags",
                "source",
                "confidence",
                "subtype",
            ]
        )

        for mem in memories:
            writer.writerow(
                [
                    mem.id,
                    mem.content,
                    mem.memory_type.value,
                    mem.created_at.isoformat(),
                    mem.updated_at.isoformat(),
                    ";".join(mem.tags),
                    mem.source,
                    mem.confidence,
                    mem.subtype or "",
                ]
            )

        return output.getvalue()

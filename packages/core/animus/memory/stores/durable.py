"""PostgreSQL-backed durable memory store using the bitemporal DurableObjectStore.

This adapter implements the :class:`MemoryStore` interface using
:class:`~animus.durability.postgres_store.DurableObjectStore` as the
backend. It provides:

- Ledgered writes: every store/update/delete produces an immutable event
- Bitemporal queries: retrieve memories as-of a point in time
- Outbox integration: async consumers can react to memory changes
- Schema validation: optional contract validation on write

Retrieval trade-offs:

- **No vector search**: ``search`` uses substring matching (like
  :class:`LocalMemoryStore`), not semantic similarity.
- **No BM25 hybrid**: Keyword ranking is basic.
- **Durability wins**: Every mutation is ledgered, versioned, and recoverable.

Best used when auditability and durability matter more than semantic retrieval.
Semantic/vector retrieval, if required, must be provided by an independently
managed service rather than the retired Core Chroma adapter.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from animus.durability.postgres_store import (
    ConcurrencyError,
    DurableObjectStore,
    EpistemicStatus,
    LedgerValidationError,
    LifecycleStatus,
    ObjectRecord,
    ObjectType,
    SecurityClass,
)
from animus.durability.postgres_store import (
    StorageTier as ObjectStorageTier,
)
from animus.logging import get_logger
from animus.memory.stores.base import MemoryStore
from animus.memory.types import Memory, MemoryTier, MemoryType, Sensitivity

logger = get_logger("memory.durable")


# ------------------------------------------------------------------
# Mapping helpers
# ------------------------------------------------------------------


def _memory_to_record(memory: Memory) -> ObjectRecord:
    """Convert a :class:`Memory` to an :class:`ObjectRecord`.

    The original ``memory.id`` (a UUID) is preserved in ``payload["memory_id"]``
    so round-trip retrieval works. The ``object_id`` is a schema-compliant slug.
    """
    # Schema-compliant object_id: prefix + hex portion of UUID (no hyphens)
    hex_id = memory.id.replace("-", "")
    object_id = f"mem-{hex_id[:24]}"

    # Map MemoryType to cognitive_role enum values
    cognitive_map = {
        MemoryType.SEMANTIC.value: "knowledge",
        MemoryType.EPISODIC.value: "memory",
        MemoryType.PROCEDURAL.value: "intelligence",
        MemoryType.ACTIVE.value: "none",
    }

    return ObjectRecord(
        object_id=object_id,
        schema_id="memory_candidate",
        schema_version="1.0.0",
        artifact_type=ObjectType.MEMORY.value,
        cognitive_role=cognitive_map.get(memory.memory_type.value, "knowledge"),
        workflow_status="active",
        epistemic_status=EpistemicStatus.SUPPORTED.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
        storage_tier=_tier_to_storage(memory.tier),
        presentation="canonical",
        security_class=_sensitivity_to_security(memory.sensitivity),
        payload={
            "memory_id": memory.id,  # Original UUID preserved for round-trip
            "content": memory.content,
            "memory_type": memory.memory_type.value,
            "source": memory.source,
            "confidence": memory.confidence,
            "subtype": memory.subtype,
            "version": memory.version,
            "parent_id": memory.parent_id,
            "change_summary": memory.change_summary,
            "provenance": memory.provenance,
            "access_count": memory.access_count,
            "metadata": memory.metadata,
        },
        tags=memory.tags,
        created_by=memory.source,
        trace_id=memory.parent_id,
    )


def _record_to_memory(record: ObjectRecord) -> Memory:
    """Convert an :class:`ObjectRecord` back to a :class:`Memory`."""
    payload = record.payload
    content = payload.get("content", "")
    # Restore original UUID if available, otherwise fall back to object_id
    mem_id = payload.get("memory_id", record.object_id)
    return Memory(
        id=mem_id,
        content=content,
        memory_type=MemoryType(payload.get("memory_type", "semantic")),
        created_at=getattr(record, "valid_from", None) or datetime.now(timezone.utc),
        updated_at=getattr(record, "recorded_at", None) or datetime.now(timezone.utc),
        metadata=payload.get("metadata", {}),
        tags=record.tags or [],
        source=payload.get("source", "stated"),
        confidence=payload.get("confidence", 1.0),
        subtype=payload.get("subtype"),
        version=payload.get("version", 1),
        parent_id=payload.get("parent_id"),
        change_summary=payload.get("change_summary"),
        provenance=payload.get("provenance", "direct"),
        sensitivity=_security_to_sensitivity(record.security_class),
        tier=_storage_to_tier(record.storage_tier),
        access_count=payload.get("access_count", 0),
        last_accessed=None,  # Could be tracked via ledger access events
    )


def _tier_to_storage(tier: MemoryTier) -> str:
    """Map MemoryTier to ObjectStorageTier."""
    mapping = {
        MemoryTier.HOT: ObjectStorageTier.HOT.value,
        MemoryTier.WARM: ObjectStorageTier.WARM.value,
        MemoryTier.COLD: ObjectStorageTier.COLD.value,
    }
    return mapping.get(tier, ObjectStorageTier.WARM.value)


def _storage_to_tier(storage: str) -> MemoryTier:
    """Map ObjectStorageTier string back to MemoryTier."""
    mapping = {
        ObjectStorageTier.HOT.value: MemoryTier.HOT,
        ObjectStorageTier.WARM.value: MemoryTier.WARM,
        ObjectStorageTier.COLD.value: MemoryTier.COLD,
    }
    return mapping.get(storage, MemoryTier.WARM)


def _sensitivity_to_security(sensitivity: Sensitivity) -> str:
    """Map Sensitivity to SecurityClass.

    animus_types.Sensitivity uses: PUBLIC, PERSONAL, CONFIDENTIAL, SECRET.
    SecurityClass uses: public, internal, confidential, restricted.
    """
    mapping = {
        Sensitivity.PUBLIC: SecurityClass.PUBLIC.value,
        Sensitivity.PERSONAL: SecurityClass.INTERNAL.value,
        Sensitivity.CONFIDENTIAL: SecurityClass.CONFIDENTIAL.value,
        Sensitivity.SECRET: SecurityClass.RESTRICTED.value,
    }
    return mapping.get(sensitivity, SecurityClass.INTERNAL.value)


def _memory_id_to_object_id(memory_id: str) -> str:
    """Convert a Memory.id (UUID) to a schema-compliant object_id."""
    hex_id = memory_id.replace("-", "")
    return f"mem-{hex_id[:24]}"


def _security_to_sensitivity(security: str) -> Sensitivity:
    """Map SecurityClass string back to Sensitivity."""
    mapping = {
        SecurityClass.PUBLIC.value: Sensitivity.PUBLIC,
        SecurityClass.INTERNAL.value: Sensitivity.PERSONAL,
        SecurityClass.CONFIDENTIAL.value: Sensitivity.CONFIDENTIAL,
        SecurityClass.RESTRICTED.value: Sensitivity.SECRET,
    }
    return mapping.get(security, Sensitivity.PERSONAL)


class DurableMemoryStore(MemoryStore):
    """PostgreSQL-backed memory store with ledgered writes.

    Usage::

        store = DurableMemoryStore(database_url="postgresql://...")
        store.create_tables()  # One-time setup
        memory = Memory.create(content="hello", tags=["test"])
        store.store(memory)

    Every mutation produces an immutable ledger event.  Deleted memories
    remain in versioned history and the ledger.
    """

    def __init__(
        self,
        database_url: str | None = None,
        owner_id: str = "owner-default",
        workspace_id: str = "ws-default",
    ):
        self._backend = DurableObjectStore(
            database_url=database_url,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )
        logger.info("DurableMemoryStore initialized")

    def create_tables(self) -> None:
        """Create bitemporal tables. Call once during setup."""
        self._backend.create_tables()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def store(self, memory: Memory) -> None:
        """Store a memory with ledgered write."""
        record = _memory_to_record(memory)
        try:
            obj_id, event_id = self._backend.store(record)
            logger.debug(f"Stored memory {obj_id[:8]} with event {event_id[:8]}")
        except LedgerValidationError as e:
            logger.error(f"Memory failed schema validation: {e}")
            raise

    def update(self, memory: Memory) -> bool:
        """Update a memory, ledgering the change."""
        object_id = _memory_id_to_object_id(memory.id)
        existing = self._backend.retrieve(object_id)
        if not existing:
            return False

        record = _memory_to_record(memory)
        try:
            success, event_id = self._backend.update(record, expected_version=existing.version)
            if success:
                logger.debug(f"Updated memory {memory.id[:8]} with event {event_id[:8]}")
            return success
        except ConcurrencyError:
            logger.warning(f"Concurrent update detected for memory {memory.id[:8]}")
            raise

    def retrieve(self, memory_id: str) -> Memory | None:
        """Retrieve the current (non-superseded) memory."""
        object_id = _memory_id_to_object_id(memory_id)
        record = self._backend.retrieve(object_id)
        if not record:
            return None
        return _record_to_memory(record)

    def delete(self, memory_id: str) -> bool:
        """Soft-delete a memory (mark superseded + ledger event)."""
        object_id = _memory_id_to_object_id(memory_id)
        ok, event_id = self._backend.delete(object_id, principal="animus")
        if ok:
            logger.debug(f"Deleted memory {memory_id[:8]} with event {event_id[:8]}")
        return ok

    # ------------------------------------------------------------------
    # Search — substring-based (no vector search in PostgreSQL backend)
    # ------------------------------------------------------------------

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

        .. note::

           This backend does **not** support semantic/vector search.
           Results are ranked by substring match position only.
           Semantic/vector retrieval requires a separately selected and managed
           retrieval service; the supported Core stores do not provide it.
        """
        records = self._backend.list_current(artifact_type=ObjectType.MEMORY.value)
        query_lower = query.lower()
        results: list[Memory] = []

        for record in records:
            memory = _record_to_memory(record)

            # Filters
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

            # Substring match
            if query_lower in memory.content.lower():
                results.append(memory)
                if len(results) >= limit:
                    break

        logger.debug("Search found %d durable results", len(results))
        return results

    def list_all(self, memory_type: MemoryType | None = None) -> list[Memory]:
        """List all current (non-superseded) memories."""
        records = self._backend.list_current(artifact_type=ObjectType.MEMORY.value)
        memories = [_record_to_memory(r) for r in records]
        if memory_type:
            return [m for m in memories if m.memory_type == memory_type]
        return memories

    def get_all_tags(self) -> dict[str, int]:
        """Get all tags with counts."""
        tag_counts: dict[str, int] = {}
        for memory in self.list_all():
            for tag in memory.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return tag_counts

    # ------------------------------------------------------------------
    # DurableObjectStore extras (not in MemoryStore base, but useful)
    # ------------------------------------------------------------------

    def get_ledger_events(self, memory_id: str) -> list[dict[str, Any]]:
        """Retrieve the audit trail for a memory."""
        object_id = _memory_id_to_object_id(memory_id)
        return self._backend.get_ledger_events(object_id)

    def as_of_valid_time(self, memory_id: str, vt: datetime) -> Memory | None:
        """Retrieve the memory as it existed at *vt* (valid time)."""
        object_id = _memory_id_to_object_id(memory_id)
        record = self._backend.as_of_valid_time(object_id, vt)
        if not record:
            return None
        return _record_to_memory(record)

    def as_of_transaction_time(self, memory_id: str, tt: datetime) -> Memory | None:
        """Retrieve the memory as known at *tt* (transaction time)."""
        object_id = _memory_id_to_object_id(memory_id)
        record = self._backend.as_of_transaction_time(object_id, tt)
        if not record:
            return None
        return _record_to_memory(record)

    def verify_integrity(self, event_id: str) -> bool:
        """Verify the integrity hash of a ledger event."""
        return self._backend.verify_integrity(event_id)

    def claim_outbox_entries(self, worker_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Claim unprocessed outbox entries for async workers."""
        return self._backend.claim_outbox_entries(worker_id, limit)

    def acknowledge_outbox_entry(self, entry_id: str, error: str | None = None) -> bool:
        """Mark an outbox entry as processed or failed."""
        return self._backend.acknowledge_outbox_entry(entry_id, error)

"""PostgreSQL-backed memory store with bitemporal event ledger.

Wires the kernel memory layer into the durable core model.
Every mutation produces an event in the ``event_ledger`` table.

Requires ``sqlalchemy`` and a running PostgreSQL instance.
Connection string is read from the ``ANIMUS_DATABASE_URL`` environment
variable.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from typing import Any

from animus_kernel.logger import get_logger
from animus_kernel.memory.stores.base import MemoryStore
from animus_kernel.memory.types import Memory, MemoryType, Sensitivity

logger = get_logger("memory.durable")

# SQLAlchemy is an optional dependency — import gracefully so the module
# can be parsed even when sqlalchemy is not installed.
try:
    from sqlalchemy import (
        JSON,
        Column,
        DateTime,
        Integer,
        String,
        and_,
        create_engine,
        func,
        select,
    )
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session, declarative_base, sessionmaker

    _HAS_SQLALCHEMY = True
except ImportError:  # pragma: no cover
    _HAS_SQLALCHEMY = False

Base = declarative_base() if _HAS_SQLALCHEMY else object  # type: ignore[misc,assignment]

if _HAS_SQLALCHEMY:

    class _ObjectRegistryRow(Base):  # type: ignore[valid-type,misc]
        """ORM mapping for the ``object_registry`` table."""

        __tablename__ = "object_registry"

        id = Column(Integer, primary_key=True, autoincrement=True)
        object_id = Column(String(128), nullable=False)
        object_version = Column(Integer, nullable=False, default=1)
        schema_id = Column(String(256), nullable=False)
        schema_version = Column(String(32), nullable=False)
        owner_id = Column(String(128), nullable=False)
        workspace_id = Column(String(128), nullable=False)
        subject_domain = Column(String(32), nullable=False)
        artifact_type = Column(String(64), nullable=False)
        cognitive_role = Column(String(32), nullable=False)
        workflow_status = Column(String(32), nullable=False)
        epistemic_status = Column(String(32), nullable=False)
        lifecycle_status = Column(String(32), nullable=False)
        storage_tier = Column(String(16), nullable=False)
        presentation = Column(String(32), nullable=False)
        security_class = Column(String(32), nullable=False)
        valid_from = Column(DateTime(timezone=True), nullable=True)
        valid_to = Column(DateTime(timezone=True), nullable=True)
        recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
        superseded_at = Column(DateTime(timezone=True), nullable=True)
        created_by = Column(String(256), nullable=False)
        trace_id = Column(String(256), nullable=True)
        content_sha256 = Column(String(64), nullable=False)
        payload = Column(JSON, nullable=False)

    class _EventLedgerRow(Base):  # type: ignore[valid-type,misc]
        """ORM mapping for the ``event_ledger`` table."""

        __tablename__ = "event_ledger"

        id = Column(Integer, primary_key=True, autoincrement=True)
        event_kind = Column(String(128), nullable=False)
        occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
        actor_refs = Column(JSON, nullable=False, server_default="[]")
        object_refs = Column(JSON, nullable=False, server_default="[]")
        event_data = Column(JSON, nullable=False, server_default="{}")
        idempotency_key = Column(String(256), nullable=True)
        valid_from = Column(DateTime(timezone=True), nullable=True)
        valid_to = Column(DateTime(timezone=True), nullable=True)
        recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _sha256(payload: dict[str, Any]) -> str:
    """Stable SHA-256 of a JSON payload."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now_utc() -> datetime:
    return datetime.now(datetime.now().astimezone().tzinfo)


class DurableMemoryStore(MemoryStore):
    """PostgreSQL-backed memory store with bitemporal event logging.

    Args:
        database_url: SQLAlchemy connection string. Defaults to
            ``ANIMUS_DATABASE_URL`` env var. Must be provided if env var
            is not set.
        owner_id: Identifier for the owner of all stored objects.
        workspace_id: Workspace scope for multi-tenant separation.
    """

    def __init__(
        self,
        database_url: str | None = None,
        owner_id: str = "animus-owner",
        workspace_id: str = "default",
    ):
        if not _HAS_SQLALCHEMY:
            raise RuntimeError(
                "sqlalchemy is required for DurableMemoryStore. "
                "Install it: pip install sqlalchemy psycopg2-binary"
            )

        self.database_url = database_url or os.getenv("ANIMUS_DATABASE_URL")
        if not self.database_url:
            raise RuntimeError(
                "DurableMemoryStore requires a database_url argument or "
                "ANIMUS_DATABASE_URL environment variable."
            )

        self.owner_id = owner_id
        self.workspace_id = workspace_id
        self._engine: Engine = create_engine(self.database_url, echo=False)
        self._session_factory = sessionmaker(bind=self._engine)
        logger.info(f"DurableMemoryStore connected to {self._engine.url.host}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _identity_conditions(self) -> list[Any]:
        """Restrict this adapter to the memory format and configured tenant it writes."""
        return [
            _ObjectRegistryRow.schema_id == "memory-v1",
            _ObjectRegistryRow.artifact_type == "memory",
            _ObjectRegistryRow.subject_domain == "user",
            _ObjectRegistryRow.owner_id == self.owner_id,
            _ObjectRegistryRow.workspace_id == self.workspace_id,
        ]

    def _current_memories(self) -> Any:
        """Filter in SQL before loading or decoding any shared-registry payload."""
        return select(_ObjectRegistryRow).where(
            *self._identity_conditions(),
            _ObjectRegistryRow.superseded_at.is_(None),
        )

    def _memory_to_payload(self, memory: Memory) -> dict[str, Any]:
        """Serialize a Memory into the JSON payload stored in object_registry."""
        return {
            "id": memory.id,
            "content": memory.content,
            "memory_type": memory.memory_type.value,
            "created_at": memory.created_at.isoformat(),
            "updated_at": memory.updated_at.isoformat(),
            "metadata": memory.metadata,
            "tags": memory.tags,
            "source": memory.source,
            "confidence": memory.confidence,
            "subtype": memory.subtype,
            "version": memory.version,
            "parent_id": memory.parent_id,
            "change_summary": memory.change_summary,
            "provenance": memory.provenance,
            "sensitivity": memory.sensitivity.value,
            "tier": memory.tier.value,
            "access_count": memory.access_count,
            "last_accessed": memory.last_accessed.isoformat() if memory.last_accessed else None,
        }

    def _payload_to_memory(self, payload: dict[str, Any]) -> Memory:
        """Reconstruct a Memory from a JSON payload."""
        return Memory.from_dict(payload)

    def _write_event(
        self,
        session: Session,
        event_kind: str,
        object_refs: list[str],
        event_data: dict[str, Any],
        actor_refs: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        """Append an event to the ledger.

        Does *not* commit the session so that callers can keep registry
        mutations and their events in a single atomic transaction.
        """
        row = _EventLedgerRow(
            event_kind=event_kind,
            actor_refs=json.dumps(actor_refs or []),
            object_refs=json.dumps(object_refs),
            event_data=json.dumps(event_data),
            idempotency_key=idempotency_key,
            valid_from=_now_utc(),
        )
        session.add(row)

    def _upsert_registry_row(self, session: Session, memory: Memory) -> _ObjectRegistryRow:
        """Create or update an object_registry row for a Memory.

        Does *not* commit the session — callers must commit explicitly so
        registry writes can be kept atomic with their corresponding event.
        """
        payload = self._memory_to_payload(memory)
        sha = _sha256(payload)

        # Object IDs are global across the shared registry, including history.
        # Inspect only identity metadata: a foreign ID must never be adopted or
        # superseded, even on older schemas without the unique-current index.
        foreign_id = session.execute(
            select(_ObjectRegistryRow.id)
            .where(
                _ObjectRegistryRow.object_id == memory.id,
                and_(*self._identity_conditions()).is_not(True),
            )
            .limit(1)
        ).scalar_one_or_none()
        if foreign_id is not None:
            raise PermissionError("Object identity belongs to another registry scope.")

        # Look for the *current* (non-superseded) row by object_id.
        # Without the superseded_at filter a concurrent update could race or
        # we could accidentally re-supersede an already-historical version.
        existing = session.execute(
            self._current_memories().where(
                _ObjectRegistryRow.object_id == memory.id,
            )
        ).scalar_one_or_none()

        if existing:
            # Mark old version as superseded
            existing.superseded_at = _now_utc()
            existing.valid_to = _now_utc()

        # Insert new version
        row = _ObjectRegistryRow(
            object_id=memory.id,
            object_version=memory.version,
            schema_id="memory-v1",
            schema_version="1.0.0",
            owner_id=self.owner_id,
            workspace_id=self.workspace_id,
            subject_domain="user",
            artifact_type="memory",
            cognitive_role="episodic" if memory.memory_type == MemoryType.EPISODIC else "semantic",
            workflow_status="active",
            epistemic_status="confirmed",
            lifecycle_status="current",
            storage_tier=memory.tier.value,
            presentation="json",
            security_class=memory.sensitivity.value,
            valid_from=_now_utc(),
            created_by="animus-kernel",
            trace_id=memory.parent_id,
            content_sha256=sha,
            payload=payload,
        )
        session.add(row)
        return row

    # ------------------------------------------------------------------
    # MemoryStore API
    # ------------------------------------------------------------------

    def store(self, memory: Memory) -> None:
        with self._session_factory() as session:
            self._upsert_registry_row(session, memory)
            self._write_event(
                session,
                event_kind="memory.stored",
                object_refs=[memory.id],
                event_data={"memory_type": memory.memory_type.value, "tier": memory.tier.value},
                actor_refs=["animus-kernel"],
                idempotency_key=f"store-{memory.id}",
            )
            session.commit()
        logger.debug(f"Stored memory {memory.id[:8]} in durable core")

    def update(self, memory: Memory) -> bool:
        with self._session_factory() as session:
            existing = session.execute(
                self._current_memories().where(
                    _ObjectRegistryRow.object_id == memory.id,
                )
            ).scalar_one_or_none()

            if not existing:
                return False

            memory.version = existing.object_version + 1
            self._upsert_registry_row(session, memory)
            self._write_event(
                session,
                event_kind="memory.updated",
                object_refs=[memory.id],
                event_data={"new_version": memory.version, "tier": memory.tier.value},
                actor_refs=["animus-kernel"],
                idempotency_key=f"update-{memory.id}-v{memory.version}",
            )
            session.commit()
        logger.debug(f"Updated memory {memory.id[:8]} in durable core")
        return True

    def retrieve(self, memory_id: str) -> Memory | None:
        with self._session_factory() as session:
            row = session.execute(
                self._current_memories().where(
                    _ObjectRegistryRow.object_id == memory_id,
                )
            ).scalar_one_or_none()

            if not row:
                return None

            # Record access in ledger (fire-and-forget style — separate transaction)
            self._write_event(
                session,
                event_kind="memory.accessed",
                object_refs=[memory_id],
                event_data={},
                actor_refs=["animus-kernel"],
                idempotency_key=None,
            )
            session.commit()

            return self._payload_to_memory(row.payload)

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
        with self._session_factory() as session:
            stmt = self._current_memories()

            results = session.execute(stmt.limit(limit * 3)).scalars().all()

            # Post-filter in Python (tags, source, confidence are inside payload)
            memories = []
            for row in results:
                mem = self._payload_to_memory(row.payload)
                if memory_type is not None and mem.memory_type != memory_type:
                    continue
                if tags and not all(t in mem.tags for t in tags):
                    continue
                if source and mem.source != source:
                    continue
                if mem.confidence < min_confidence:
                    continue
                if allowed_tiers is not None and mem.sensitivity not in allowed_tiers:
                    continue
                if query.lower() in mem.content.lower():
                    memories.append(mem)
                if len(memories) >= limit:
                    break

            return memories

    def delete(self, memory_id: str) -> bool:
        with self._session_factory() as session:
            row = session.execute(
                self._current_memories().where(
                    _ObjectRegistryRow.object_id == memory_id,
                )
            ).scalar_one_or_none()

            if not row:
                return False

            row.superseded_at = _now_utc()
            row.valid_to = _now_utc()
            row.lifecycle_status = "deleted"

            self._write_event(
                session,
                event_kind="memory.deleted",
                object_refs=[memory_id],
                event_data={},
                actor_refs=["animus-kernel"],
                idempotency_key=f"delete-{memory_id}",
            )
            session.commit()
        logger.debug(f"Deleted memory {memory_id[:8]} from durable core")
        return True

    def list_all(self, memory_type: MemoryType | None = None) -> list[Memory]:
        with self._session_factory() as session:
            stmt = self._current_memories()
            rows = session.execute(stmt).scalars().all()
            memories = [self._payload_to_memory(r.payload) for r in rows]
            if memory_type:
                memories = [m for m in memories if m.memory_type == memory_type]
            return memories

    def get_all_tags(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for mem in self.list_all():
            for tag in mem.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return counts

"""PostgreSQL-backed durable object store with bitemporal event ledger.

Optional dependency gated by ``sqlalchemy`` availability. When unavailable,
:class:`DurableObjectStore` raises :exc:`RuntimeError` on instantiation with a
helpful install message.

Kernel-native durability layer (v2.3, 2026-07-06).

Usage::

    store = DurableObjectStore(database_url=os.getenv("ANIMUS_DATABASE_URL"))
    store.create_tables()  # Run once during setup
    obj_id, event_id = store.store(ObjectRecord(
        object_id="mem-001",
        schema_id="memory_candidate",
        payload={"content": "hello"},
    ))
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, cast

from animus_types import ValidationError as _ContractValidationError

from animus.durability.schema import SchemaCompatibilityError, inspect_schema
from animus.durability.scope import ObjectScope
from animus.logging import get_logger

logger = get_logger("durability.postgres_store")

try:
    from animus_contracts import (
        validate as _validate_contract,  # boundary-ok: optional contract validation
    )

    _HAS_CONTRACTS = True
except ImportError:  # pragma: no cover
    _HAS_CONTRACTS = False

try:
    from sqlalchemy import (
        JSON,
        BigInteger,
        Column,
        DateTime,
        Index,
        Integer,
        String,
        create_engine,
        func,
        select,
    )
    from sqlalchemy import (
        update as sql_update,
    )
    from sqlalchemy.engine import CursorResult, Engine
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session, aliased, declarative_base, sessionmaker

    _HAS_SQLALCHEMY = True
except ImportError:  # pragma: no cover
    _HAS_SQLALCHEMY = False
    # Provide placeholders so type-checking passes even without sqlalchemy
    Engine = Any  # type: ignore[misc,assignment]
    Session = Any  # type: ignore[misc,assignment]
    declarative_base = object  # type: ignore[misc,assignment]
    sessionmaker = object  # type: ignore[misc,assignment]


# ------------------------------------------------------------------
# Domain enums (bitemporal registry types, not kernel memory types)
# ------------------------------------------------------------------


class ObjectType(str, Enum):
    MEMORY = "memory"
    SOURCE = "source"
    CLAIM = "claim"
    FORECAST = "forecast"
    DECISION = "decision"
    ACTION = "action"
    AGENT_CONTRACT = "agent_contract"


class StorageTier(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class SecurityClass(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class EpistemicStatus(str, Enum):
    UNVERIFIED = "unverified"
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    REFUTED = "refuted"


class LifecycleStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    DELETED = "deleted"


class EventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    SUPERSEDED = "superseded"
    APPROVED = "approved"
    REJECTED = "rejected"
    DELETED = "deleted"
    RESTORED = "restored"
    EXPORTED = "exported"
    IMPORTED = "imported"


# ------------------------------------------------------------------
# Domain dataclass
# ------------------------------------------------------------------


@dataclass
class ObjectRecord:
    """A canonical object record in the bitemporal registry."""

    object_id: str
    schema_id: str
    schema_version: str = "1.0.0"
    owner_id: str = "owner-default"
    workspace_id: str = "ws-default"
    subject_domain: str = "self"
    artifact_type: str = ObjectType.MEMORY.value
    cognitive_role: str = "memory"
    workflow_status: str = "active"
    epistemic_status: str = EpistemicStatus.SUPPORTED.value
    lifecycle_status: str = LifecycleStatus.ACTIVE.value
    storage_tier: str = StorageTier.WARM.value
    presentation: str = "canonical"
    security_class: str = SecurityClass.INTERNAL.value
    payload: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created_by: str = "animus"
    trace_id: str | None = None
    version: int = 1
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    recorded_at: datetime | None = None
    superseded_at: datetime | None = None


# ------------------------------------------------------------------
# SQLAlchemy models
# ------------------------------------------------------------------

if _HAS_SQLALCHEMY:
    Base = declarative_base()

    class _ObjectRegistryRow(Base):  # type: ignore[valid-type,misc]
        """Canonical object registry with bitemporal state.

        *valid_time* — when the object was true in the real world.
        *transaction_time* — when the system recorded the fact.
        """

        __tablename__ = "object_registry"

        id = Column(
            BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
        )
        object_id = Column(String(128), nullable=False, index=True)
        object_version = Column(Integer, nullable=False, default=1)
        schema_id = Column(String(256), nullable=False)
        schema_version = Column(String(32), nullable=False)
        owner_id = Column(String(128), nullable=False)
        workspace_id = Column(String(128), nullable=False, index=True)
        subject_domain = Column(String(32), nullable=False)
        artifact_type = Column(String(64), nullable=False)
        cognitive_role = Column(String(32), nullable=False)
        workflow_status = Column(String(32), nullable=False)
        epistemic_status = Column(String(32), nullable=False)
        lifecycle_status = Column(String(32), nullable=False)
        storage_tier = Column(String(16), nullable=False)
        presentation = Column(String(32), nullable=False)
        security_class = Column(String(32), nullable=False)

        # Bitemporal — valid time (real-world truth interval)
        valid_from = Column(DateTime(timezone=True), nullable=True)
        valid_to = Column(DateTime(timezone=True), nullable=True)

        # Bitemporal — transaction time (system record interval)
        recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
        superseded_at = Column(DateTime(timezone=True), nullable=True)

        created_by = Column(String(256), nullable=False)
        trace_id = Column(String(256), nullable=True)
        content_sha256 = Column(String(64), nullable=False)
        payload = Column(JSON, nullable=False)
        tags = Column(JSON, nullable=False, server_default="[]")

    Index(
        "idx_object_id_version",
        _ObjectRegistryRow.object_id,
        _ObjectRegistryRow.object_version,
        unique=True,
    )
    Index(
        "idx_object_current",
        _ObjectRegistryRow.object_id,
        unique=True,
        sqlite_where=_ObjectRegistryRow.superseded_at.is_(None),
        postgresql_where=_ObjectRegistryRow.superseded_at.is_(None),
    )

    class _LedgerEventRow(Base):  # type: ignore[valid-type,misc]
        """Immutable append-only event ledger."""

        __tablename__ = "event_ledger"

        id = Column(
            BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
        )
        event_kind = Column(String(128), nullable=False)
        occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
        actor_refs = Column(JSON, nullable=False, server_default="[]")
        object_refs = Column(JSON, nullable=False, server_default="[]")
        event_data = Column(JSON, nullable=False, server_default="{}")
        idempotency_key = Column(String(256), nullable=True, unique=True)
        valid_from = Column(DateTime(timezone=True), nullable=True)
        valid_to = Column(DateTime(timezone=True), nullable=True)
        recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    class _OutboxEntryRow(Base):  # type: ignore[valid-type,misc]
        """Transactional outbox entry for async consumers."""

        __tablename__ = "outbox_entries"

        id = Column(
            BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
        )
        entry_id = Column(String(128), nullable=False, unique=True)
        topic = Column(String(128), nullable=False)
        payload = Column(JSON, nullable=False)
        headers = Column(JSON, nullable=False, server_default="{}")
        created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
        claimed_at = Column(DateTime(timezone=True), nullable=True)
        claimed_by = Column(String(128), nullable=True)
        retry_count = Column(Integer, nullable=False, default=0)
        processed_at = Column(DateTime(timezone=True), nullable=True)
        error_message = Column(String(512), nullable=True)
else:
    Base = object  # type: ignore[misc,assignment]


# ------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------


class ConcurrencyError(RuntimeError):
    """Raised when optimistic concurrency check fails."""


class LedgerValidationError(Exception):
    """Raised when a ledger event fails validation."""


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive timestamps even for timezone-aware columns."""
    if value is None:
        return None
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _generate_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def _row_to_record(row: Any) -> ObjectRecord:
    """Convert an _ObjectRegistryRow to an ObjectRecord."""
    return ObjectRecord(
        object_id=row.object_id,
        schema_id=row.schema_id,
        schema_version=row.schema_version,
        owner_id=row.owner_id,
        workspace_id=row.workspace_id,
        subject_domain=row.subject_domain,
        artifact_type=row.artifact_type,
        cognitive_role=row.cognitive_role,
        workflow_status=row.workflow_status,
        epistemic_status=row.epistemic_status,
        lifecycle_status=row.lifecycle_status,
        storage_tier=row.storage_tier,
        presentation=row.presentation,
        security_class=row.security_class,
        payload=row.payload,
        tags=row.tags or [],
        created_by=row.created_by,
        trace_id=row.trace_id,
        version=row.object_version,
        valid_from=_utc(row.valid_from),
        valid_to=_utc(row.valid_to),
        recorded_at=_utc(row.recorded_at),
        superseded_at=_utc(row.superseded_at),
    )


# ------------------------------------------------------------------
# Store
# ------------------------------------------------------------------


class DurableObjectStore:
    """PostgreSQL-backed durable object store.

    This is the **canonical authority** in the bitemporal architecture.
    All consequential state transitions flow through here.

    Requires ``sqlalchemy`` and a running PostgreSQL instance.
    Connection string is read from ``database_url`` parameter or
    ``ANIMUS_DATABASE_URL`` environment variable.
    """

    def __init__(
        self,
        database_url: str | None = None,
        owner_id: str = "owner-default",
        workspace_id: str = "ws-default",
        *,
        scope: ObjectScope | None = None,
    ):
        if not _HAS_SQLALCHEMY:
            raise RuntimeError(
                "DurableObjectStore requires sqlalchemy. Install: pip install animus[postgres]"
            )

        self.database_url = database_url or os.getenv("ANIMUS_DATABASE_URL")
        if not self.database_url:
            raise RuntimeError("DurableObjectStore requires database_url or ANIMUS_DATABASE_URL.")

        if scope is not None and not _HAS_CONTRACTS:
            raise RuntimeError(
                "Scoped stores require animus-contracts; install the contracts package."
            )
        self._scope = scope
        self._schema_checked = False
        self.owner_id = owner_id
        self.workspace_id = workspace_id
        self._engine: Engine = create_engine(self.database_url, echo=False, hide_parameters=True)
        self._session_factory = sessionmaker(bind=self._engine)
        logger.debug("DurableObjectStore initialized")

    @property
    def scope(self) -> ObjectScope | None:
        """Immutable query scope; None is a trusted internal, unscoped store."""
        return self._scope

    def preflight(self) -> None:
        """Reject incompatible schemas without printing connection details."""
        report = inspect_schema(self._engine, Base.metadata)
        if not report.compatible:
            raise SchemaCompatibilityError("; ".join(report.problems))
        self._schema_checked = True

    def create_tables(self) -> None:
        """Initialize an empty database only; existing databases need migrations."""
        from sqlalchemy import inspect

        tables = set(inspect(self._engine).get_table_names())
        if tables.intersection(Base.metadata.tables):
            self.preflight()
            return
        Base.metadata.create_all(self._engine)
        self.preflight()

    def _scope_conditions(self, row: Any, *, historical: bool = False) -> list[Any]:
        if self.scope is None:
            return []
        scope = self.scope
        return [
            row.owner_id == scope.owner_id,
            row.workspace_id == scope.workspace_id,
            row.subject_domain == scope.subject_domain,
            row.security_class == scope.security_class,
            row.schema_id == scope.schema_id,
            row.artifact_type.in_(scope.artifact_types),
            row.lifecycle_status.in_(("active", "superseded") if historical else ("active",)),
        ]

    def _objects(self, *, historical: bool = False) -> Any:
        if self.scope is not None and not self._schema_checked:
            self.preflight()
        stmt = select(_ObjectRegistryRow).where(
            *self._scope_conditions(_ObjectRegistryRow, historical=historical)
        )
        if self.scope is not None and historical:
            # A now-private/deleted object must not leak through its old public versions.
            current = aliased(_ObjectRegistryRow)
            stmt = stmt.where(
                select(current.id)
                .where(
                    current.object_id == _ObjectRegistryRow.object_id,
                    current.superseded_at.is_(None),
                    *self._scope_conditions(current),
                )
                .exists()
            )
        return stmt

    def _guard_write(self, record: ObjectRecord) -> None:
        if self.scope is not None:
            if not self.scope.permits(record):
                raise PermissionError("Record is outside this store's write scope.")
            if not self._schema_checked:
                self.preflight()

    def _compute_integrity_hash(self, record: ObjectRecord) -> str:
        payload = {
            "object_id": record.object_id,
            "version": record.version,
            "schema_id": record.schema_id,
            "schema_version": record.schema_version,
            "owner_id": record.owner_id,
            "workspace_id": record.workspace_id,
            "artifact_type": record.artifact_type,
            "payload": record.payload,
            "tags": record.tags,
        }
        return _sha256(payload)

    def _write_ledger_event(
        self,
        session: Session,
        event_type: str,
        record: ObjectRecord,
        parent_event_id: str | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Append an immutable event to the ledger. Returns event_id."""
        event_id = _generate_id("evt")
        payload = {
            "artifact_type": record.artifact_type,
            "schema_id": record.schema_id,
            "tags": record.tags,
        }
        if metadata is not None:
            payload["metadata"] = metadata
        now = _now_utc()
        integrity = _sha256(
            {
                "event_id": event_id,
                "event_type": event_type,
                "object_id": record.object_id,
                "version": record.version,
                "payload": payload,
            }
        )

        event = {
            "event_id": event_id,
            "event_type": event_type,
            "object_id": record.object_id,
            "object_version": record.version,
            "principal": record.created_by,
            "workspace_id": record.workspace_id,
            "payload": payload,
            "integrity_hash": integrity,
            "tx_time": now.isoformat(),
            "parent_event_id": parent_event_id,
        }
        row = _LedgerEventRow(
            event_kind=f"object.{event_type}",
            occurred_at=now,
            recorded_at=now,
            actor_refs=[record.created_by],
            object_refs=[record.object_id],
            event_data=event,
            idempotency_key=event_id,
            valid_from=record.valid_from,
        )
        session.add(row)
        session.flush()
        return event_id

    def _enqueue_outbox(
        self,
        session: Session,
        topic: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> str:
        """Enqueue an outbox entry for async processing. Returns entry_id."""
        entry_id = _generate_id("obx")
        headers_dict = headers or {}

        row = _OutboxEntryRow(
            entry_id=entry_id,
            topic=topic,
            payload=payload,
            headers=headers_dict,
        )
        session.add(row)
        session.flush()
        return entry_id

    # ------------------------------------------------------------------
    # CRUD + ledger
    # ------------------------------------------------------------------

    @staticmethod
    def _new_row(record: ObjectRecord, integrity: str, now: datetime) -> Any:
        values = {
            key: getattr(record, key)
            for key in (
                "object_id",
                "schema_id",
                "schema_version",
                "owner_id",
                "workspace_id",
                "subject_domain",
                "artifact_type",
                "cognitive_role",
                "workflow_status",
                "epistemic_status",
                "lifecycle_status",
                "storage_tier",
                "presentation",
                "security_class",
                "created_by",
                "trace_id",
                "payload",
                "tags",
                "valid_from",
                "valid_to",
            )
        }
        values["valid_from"] = _utc(record.valid_from)
        values["valid_to"] = _utc(record.valid_to)
        return _ObjectRegistryRow(
            **values, object_version=record.version, recorded_at=now, content_sha256=integrity
        )

    def store(self, record: ObjectRecord) -> tuple[str, str]:
        """Create once, atomically with event/outbox; duplicate identity is an error."""
        self._guard_write(record)
        candidate = replace(
            record,
            version=1,
            valid_from=record.valid_from if self.scope else (record.valid_from or _now_utc()),
        )
        now = _now_utc()
        integrity = self._compute_integrity_hash(candidate)
        self._validate_object_version(candidate, integrity, candidate.valid_from, now)
        try:
            with self._session_factory.begin() as session:
                session.add(self._new_row(candidate, integrity, now))
                session.flush()
                event_id = self._write_ledger_event(session, EventType.CREATED.value, candidate)
                self._enqueue_outbox(
                    session,
                    "object.created",
                    {
                        "object_id": candidate.object_id,
                        "version": 1,
                        "event_id": event_id,
                    },
                )
        except IntegrityError:
            raise ConcurrencyError(
                "Object identity already exists or violates registry constraints."
            ) from None
        record.version = 1
        return record.object_id, event_id

    def update(self, record: ObjectRecord, expected_version: int | None = None) -> tuple[bool, str]:
        """Atomically replace the current version. Scoped writers must supply a version."""
        self._guard_write(record)
        if self.scope is not None and expected_version is None:
            raise ValueError("Scoped updates require expected_version.")
        try:
            with self._session_factory.begin() as session:
                current = session.execute(
                    self._objects().where(
                        _ObjectRegistryRow.object_id == record.object_id,
                        _ObjectRegistryRow.superseded_at.is_(None),
                    )
                ).scalar_one_or_none()
                if current is None:
                    return False, ""
                if expected_version is not None and current.object_version != expected_version:
                    raise ConcurrencyError("Expected version does not match the current object.")
                candidate = replace(
                    record,
                    version=current.object_version + 1,
                    valid_from=record.valid_from
                    if self.scope
                    else (record.valid_from or _now_utc()),
                )
                now = _now_utc()
                integrity = self._compute_integrity_hash(candidate)
                self._validate_object_version(candidate, integrity, candidate.valid_from, now)
                # Compare-and-swap in SQL, not just a Python check of a prior read.
                changed = session.execute(
                    sql_update(_ObjectRegistryRow)
                    .where(
                        _ObjectRegistryRow.id == current.id,
                        _ObjectRegistryRow.object_version == current.object_version,
                        _ObjectRegistryRow.superseded_at.is_(None),
                        *self._scope_conditions(_ObjectRegistryRow),
                    )
                    .values(
                        superseded_at=now,
                        lifecycle_status=LifecycleStatus.SUPERSEDED.value,
                        **({"valid_to": now} if self.scope is None else {}),
                    ),
                    execution_options={"synchronize_session": False},
                )
                if cast(CursorResult, changed).rowcount != 1:
                    raise ConcurrencyError("Object changed during update; reload and retry.")
                session.add(self._new_row(candidate, integrity, now))
                session.flush()
                event_id = self._write_ledger_event(session, EventType.UPDATED.value, candidate)
                self._enqueue_outbox(
                    session,
                    "object.updated",
                    {
                        "object_id": record.object_id,
                        "version": candidate.version,
                        "event_id": event_id,
                    },
                )
        except IntegrityError:
            raise ConcurrencyError("Concurrent update violates registry constraints.") from None
        record.version = candidate.version
        return True, event_id

    def _validate_object_version(
        self,
        record: ObjectRecord,
        integrity_hash: str,
        valid_from: datetime | None = None,
        recorded_at: datetime | None = None,
    ) -> None:
        """Validate an object record against ``object_version.schema.json``.

        Raises :exc:`LedgerValidationError` on mismatch (fail-closed).
        Skips validation when ``animus_contracts`` is not installed.
        """
        for value in (record.valid_from, record.valid_to):
            if value is not None and (not isinstance(value, datetime) or value.utcoffset() is None):
                raise LedgerValidationError(
                    "Effective timestamps must be timezone-aware datetimes."
                )
        if record.valid_from is not None and record.valid_to is not None:
            if record.valid_to <= record.valid_from:
                raise LedgerValidationError("valid_to must be later than valid_from.")
        if not _HAS_CONTRACTS:
            if self.scope is not None:
                raise LedgerValidationError("Scoped writes require contract validation.")
            return

        now_iso = (recorded_at or _now_utc()).isoformat()
        valid_from_iso = valid_from.isoformat() if valid_from else None

        version_dict = {
            "object_id": record.object_id,
            "object_version": record.version,
            "schema_id": record.schema_id,
            "schema_version": record.schema_version,
            "owner_id": record.owner_id,
            "workspace_id": record.workspace_id,
            "subject_domain": record.subject_domain,
            "artifact_type": record.artifact_type,
            "cognitive_role": record.cognitive_role,
            "workflow_status": record.workflow_status,
            "epistemic_status": record.epistemic_status,
            "lifecycle_status": record.lifecycle_status,
            "storage_tier": record.storage_tier,
            "presentation": record.presentation,
            "security_class": record.security_class,
            "valid_from": valid_from_iso,
            "valid_to": record.valid_to.isoformat() if record.valid_to else None,
            "recorded_at": now_iso,
            "created_by": record.created_by,
            "content_sha256": integrity_hash,
            "payload": record.payload,
            "tags": record.tags or [],
        }

        try:
            _validate_contract(version_dict, "object_version")
        except _ContractValidationError as exc:
            raise LedgerValidationError(
                f"Object version failed schema validation: {exc.errors}"
            ) from exc

    def retrieve(self, object_id: str) -> ObjectRecord | None:
        """Retrieve the current (non-superseded) version of an object."""
        with self._session_factory() as session:
            row = session.execute(
                self._objects().where(
                    _ObjectRegistryRow.object_id == object_id,
                    _ObjectRegistryRow.superseded_at.is_(None),
                )
            ).scalar_one_or_none()

            if not row:
                return None
            return _row_to_record(row)

    def retrieve_version(self, object_id: str, version: int) -> ObjectRecord | None:
        """Retrieve a specific historical version of an object."""
        with self._session_factory() as session:
            row = session.execute(
                self._objects(historical=True).where(
                    _ObjectRegistryRow.object_id == object_id,
                    _ObjectRegistryRow.object_version == version,
                )
            ).scalar_one_or_none()

            if not row:
                return None
            return _row_to_record(row)

    def delete(self, object_id: str, principal: str = "animus") -> tuple[bool, str]:
        """Soft-delete a scoped current object in the same transaction as its event."""
        with self._session_factory.begin() as session:
            row = session.execute(
                self._objects().where(
                    _ObjectRegistryRow.object_id == object_id,
                    _ObjectRegistryRow.superseded_at.is_(None),
                )
            ).scalar_one_or_none()
            if row is None:
                return False, ""
            record = _row_to_record(row)
            record.created_by = principal
            now = _now_utc()
            changed = session.execute(
                sql_update(_ObjectRegistryRow)
                .where(
                    _ObjectRegistryRow.id == row.id,
                    _ObjectRegistryRow.superseded_at.is_(None),
                    *self._scope_conditions(_ObjectRegistryRow),
                )
                .values(
                    superseded_at=now,
                    lifecycle_status=LifecycleStatus.DELETED.value,
                    **({"valid_to": now} if self.scope is None else {}),
                ),
                execution_options={"synchronize_session": False},
            )
            if cast(CursorResult, changed).rowcount != 1:
                raise ConcurrencyError("Object changed during deletion.")
            event_id = self._write_ledger_event(session, EventType.DELETED.value, record)
            self._enqueue_outbox(
                session, "object.deleted", {"object_id": object_id, "event_id": event_id}
            )
            return True, event_id

    def list_current(
        self, artifact_type: str | None = None, *, limit: int | None = None
    ) -> list[ObjectRecord]:
        """List current objects in stable order, optionally bounded in SQL."""
        if limit is not None and (type(limit) is not int or limit < 1):
            raise ValueError("limit must be a positive integer.")
        with self._session_factory() as session:
            stmt = (
                self._objects()
                .where(_ObjectRegistryRow.superseded_at.is_(None))
                .order_by(_ObjectRegistryRow.object_id)
            )
            if artifact_type:
                stmt = stmt.where(_ObjectRegistryRow.artifact_type == artifact_type)
            if limit is not None:
                stmt = stmt.limit(limit)

            rows = session.execute(stmt).scalars().all()
            return [_row_to_record(r) for r in rows]

    # ------------------------------------------------------------------
    # Bitemporal queries
    # ------------------------------------------------------------------

    def as_of_valid_time(self, object_id: str, vt: datetime) -> ObjectRecord | None:
        """Retrieve the version valid at *vt* (valid time)."""
        valid_time = _utc(vt)
        with self._session_factory() as session:
            row = session.execute(
                self._objects(historical=True)
                .where(
                    _ObjectRegistryRow.object_id == object_id,
                    _ObjectRegistryRow.valid_from <= valid_time,
                    _ObjectRegistryRow.valid_to.is_(None)
                    | (_ObjectRegistryRow.valid_to > valid_time),
                )
                .order_by(_ObjectRegistryRow.object_version.desc())
                .limit(1)
            ).scalar_one_or_none()

            if not row:
                return None
            return _row_to_record(row)

    def as_of_transaction_time(self, object_id: str, tt: datetime) -> ObjectRecord | None:
        """Retrieve the version as known at *tt* (transaction time)."""
        transaction_time = _utc(tt)
        with self._session_factory() as session:
            row = session.execute(
                self._objects(historical=True).where(
                    _ObjectRegistryRow.object_id == object_id,
                    _ObjectRegistryRow.recorded_at <= transaction_time,
                    _ObjectRegistryRow.superseded_at.is_(None)
                    | (_ObjectRegistryRow.superseded_at > transaction_time),
                )
            ).scalar_one_or_none()

            if not row:
                return None
            return _row_to_record(row)

    # ------------------------------------------------------------------
    # Ledger access
    # ------------------------------------------------------------------

    def _ledger_query(self) -> Any:
        # Core events coexist with Kernel events; only the documented Core
        # envelope is exposed through this compatibility API.
        stmt = select(_LedgerEventRow).where(_LedgerEventRow.event_kind.like("object.%"))
        if self.scope is not None:
            stmt = stmt.where(
                self._objects(historical=True)
                .where(
                    _ObjectRegistryRow.object_id
                    == _LedgerEventRow.event_data["object_id"].as_string(),
                    _ObjectRegistryRow.object_version
                    == _LedgerEventRow.event_data["object_version"].as_integer(),
                )
                .exists()
            )
        return stmt

    def get_ledger_events(self, object_id: str) -> list[dict[str, Any]]:
        """Core events for an object, filtered in SQL before loading event data."""
        with self._session_factory() as session:
            rows = (
                session.execute(
                    self._ledger_query()
                    .where(
                        _LedgerEventRow.event_data["object_id"].as_string() == object_id,
                    )
                    .order_by(_LedgerEventRow.id)
                )
                .scalars()
                .all()
            )
            return [dict(row.event_data) for row in rows]

    def verify_integrity(self, event_id: str) -> bool:
        """Verify a visible Core event; out-of-scope events return False."""
        with self._session_factory() as session:
            row = session.execute(
                self._ledger_query().where(
                    _LedgerEventRow.idempotency_key == event_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            event = row.event_data
            expected = _sha256(
                {
                    "event_id": event["event_id"],
                    "event_type": event["event_type"],
                    "object_id": event["object_id"],
                    "version": event["object_version"],
                    "payload": event["payload"],
                }
            )
            return bool(event["integrity_hash"] == expected)

    # ------------------------------------------------------------------
    # Outbox processing
    # ------------------------------------------------------------------

    def claim_outbox_entries(self, worker_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Claim unprocessed outbox entries for a worker."""
        if self.scope is not None:
            raise PermissionError("Outbox operations require a trusted internal worker.")
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(_OutboxEntryRow)
                    .where(_OutboxEntryRow.processed_at.is_(None))
                    .where(_OutboxEntryRow.claimed_at.is_(None))
                    .limit(limit)
                )
                .scalars()
                .all()
            )

            now = _now_utc()
            entries = []
            for row in rows:
                row.claimed_at = now
                row.claimed_by = worker_id
                entries.append(
                    {
                        "entry_id": row.entry_id,
                        "topic": row.topic,
                        "payload": row.payload,
                        "headers": row.headers,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    }
                )
            session.commit()
            return entries

    def acknowledge_outbox_entry(self, entry_id: str, error: str | None = None) -> bool:
        """Mark an outbox entry as processed (or failed)."""
        if self.scope is not None:
            raise PermissionError("Outbox operations require a trusted internal worker.")
        with self._session_factory() as session:
            row = session.execute(
                select(_OutboxEntryRow).where(_OutboxEntryRow.entry_id == entry_id)
            ).scalar_one_or_none()

            if not row:
                return False

            if error:
                row.retry_count += 1
                row.error_message = error
                row.claimed_at = None
                row.claimed_by = None
            else:
                row.processed_at = _now_utc()
                row.error_message = None

            session.commit()
            return True


__all__ = [
    "DurableObjectStore",
    "ObjectRecord",
    "ObjectType",
    "StorageTier",
    "SecurityClass",
    "EpistemicStatus",
    "LifecycleStatus",
    "EventType",
    "ConcurrencyError",
    "LedgerValidationError",
]

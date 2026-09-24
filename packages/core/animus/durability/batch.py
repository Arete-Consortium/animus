"""Atomic, scoped batches for trusted operator importers; never a chat capability."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy import update as sql_update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from animus.durability.postgres_store import (
    ConcurrencyError,
    DurableObjectStore,
    ObjectRecord,
    _now_utc,
    _ObjectRegistryRow,
    _row_to_record,
    _sha256,
    _utc,
)


@dataclass(frozen=True, kw_only=True)
class BatchChange:
    record: ObjectRecord
    expected_version: int
    expected_fingerprint: str | None
    evidence: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class BatchResult:
    object_id: str
    version: int
    outcome: str
    event_id: str | None = None


def record_fingerprint(record: ObjectRecord) -> str:
    """Compare the whole persisted envelope except transaction-generated fields."""
    values = asdict(record)
    for key in ("version", "recorded_at", "superseded_at"):
        values.pop(key)
    for key in ("valid_from", "valid_to"):
        value = _utc(values[key])
        values[key] = value.isoformat() if value else None
    return _sha256(values)


def apply_batch(
    store: DurableObjectStore,
    changes: tuple[BatchChange, ...],
    *,
    current_allowed: Callable[[ObjectRecord], bool] | None = None,
) -> tuple[BatchResult, ...]:
    """Compare-and-swap a whole batch, including its ledger and outbox, or roll it back.

    Exact current-envelope matches are no-ops, even on replay of an already applied
    plan. Changed envelopes require both the expected version and fingerprint.
    Scope is server-selected; this API does not itself confer operator authority.
    """
    if store.scope is None:
        raise ValueError("Batch writes require an explicitly scoped store.")
    if not 1 <= len(changes) <= 250:
        raise ValueError("Batch must contain between 1 and 250 changes.")
    changes = copy.deepcopy(changes)
    ids = [c.record.object_id for c in changes]
    if len(ids) != len(set(ids)):
        raise ValueError("Batch identities must be unique.")
    if store._engine.dialect.name not in {"sqlite", "postgresql"}:
        raise ValueError("Batch writes support SQLite and PostgreSQL only.")
    store.preflight()
    for change in changes:
        if type(change.expected_version) is not int or change.expected_version < 0:
            raise ValueError("An explicit nonnegative expected version is required.")
        if (change.expected_version == 0 and change.expected_fingerprint is not None) or (
            change.expected_version > 0
            and (
                not isinstance(change.expected_fingerprint, str)
                or not re.fullmatch(r"[a-f0-9]{64}", change.expected_fingerprint)
            )
        ):
            raise ValueError("Existing versions require a baseline fingerprint.")
        # Detached JSON evidence is bounded before starting a write transaction.
        if len(json.dumps(change.evidence, allow_nan=False).encode()) > 1024 * 1024:
            raise ValueError("Batch evidence exceeds the per-record limit.")
        store._guard_write(change.record)
    results = []
    try:
        with store._session_factory.begin() as session:
            if store._engine.dialect.name == "sqlite":
                # SQLite has no row locks; acquire the write reservation before reads.
                session.execute(text("BEGIN IMMEDIATE"))
            for change in sorted(changes, key=lambda c: c.record.object_id):
                record = change.record
                current = session.execute(
                    store._objects()
                    .where(
                        _ObjectRegistryRow.object_id == record.object_id,
                        _ObjectRegistryRow.superseded_at.is_(None),
                    )
                    .with_for_update()
                ).scalar_one_or_none()
                if current is not None:
                    if current_allowed is not None and not current_allowed(_row_to_record(current)):
                        raise PermissionError("Current object is protected from this batch writer.")
                    fingerprint = record_fingerprint(_row_to_record(current))
                    if fingerprint == record_fingerprint(record):
                        results.append(
                            BatchResult(
                                object_id=record.object_id,
                                version=current.object_version,
                                outcome="unchanged",
                            )
                        )
                        continue
                    if (
                        current.object_version != change.expected_version
                        or fingerprint != change.expected_fingerprint
                    ):
                        raise ConcurrencyError("Batch baseline changed; create a new plan.")
                    version = current.object_version + 1
                else:
                    occupied = session.execute(
                        select(_ObjectRegistryRow.id)
                        .where(_ObjectRegistryRow.object_id == record.object_id)
                        .limit(1)
                    ).first()
                    if change.expected_version != 0 or occupied is not None:
                        raise ConcurrencyError("Batch identity is unavailable; create a new plan.")
                    version = 1
                candidate = replace(record, version=version)
                now = _now_utc()
                integrity = store._compute_integrity_hash(candidate)
                store._validate_object_version(candidate, integrity, candidate.valid_from, now)
                if current is not None:
                    changed = session.execute(
                        sql_update(_ObjectRegistryRow)
                        .where(
                            _ObjectRegistryRow.id == current.id,
                            _ObjectRegistryRow.object_version == change.expected_version,
                            _ObjectRegistryRow.superseded_at.is_(None),
                            *store._scope_conditions(_ObjectRegistryRow),
                        )
                        .values(superseded_at=now, lifecycle_status="superseded"),
                        execution_options={"synchronize_session": False},
                    )
                    if cast(CursorResult, changed).rowcount != 1:
                        raise ConcurrencyError("Batch changed during apply; create a new plan.")
                session.add(store._new_row(candidate, integrity, now))
                session.flush()
                outcome = "created" if current is None else "updated"
                event_id = store._write_ledger_event(
                    session,
                    outcome,
                    candidate,
                    metadata=change.evidence,
                )
                store._enqueue_outbox(
                    session,
                    f"object.{outcome}",
                    {
                        "object_id": candidate.object_id,
                        "version": version,
                        "event_id": event_id,
                    },
                )
                results.append(
                    BatchResult(
                        object_id=candidate.object_id,
                        version=version,
                        outcome=outcome,
                        event_id=event_id,
                    )
                )
    except IntegrityError:
        raise ConcurrencyError("Batch identity changed or violates registry constraints.") from None
    return tuple(results)

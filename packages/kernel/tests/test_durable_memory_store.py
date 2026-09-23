"""Tests for DurableMemoryStore using an in-memory SQLite database.

These tests verify that the durable store correctly implements the
MemoryStore interface and writes events to the ledger, without requiring
a live PostgreSQL instance.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from animus_kernel.memory.stores.durable import DurableMemoryStore
from animus_kernel.memory.types import Memory, MemoryTier, MemoryType, Sensitivity

# Use SQLite in-memory for tests — SQLAlchemy abstracts the dialect.
_TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture
def store(tmp_path: Path):
    """Create a DurableMemoryStore backed by an in-memory SQLite database."""
    # Ensure the env var doesn't leak from the host
    old_env = os.environ.get("ANIMUS_DATABASE_URL")
    os.environ["ANIMUS_DATABASE_URL"] = _TEST_DB_URL

    ds = DurableMemoryStore(owner_id="test-owner", workspace_id="test-ws")

    # Create tables manually (Alembic isn't run in test)
    from animus_kernel.memory.stores.durable import (
        _ObjectRegistryRow,
    )

    _ObjectRegistryRow.metadata.create_all(ds._engine)

    yield ds

    # Cleanup
    if old_env is None:
        os.environ.pop("ANIMUS_DATABASE_URL", None)
    else:
        os.environ["ANIMUS_DATABASE_URL"] = old_env


def _make_memory(content: str = "hello world", **kwargs) -> Memory:
    defaults = {
        "memory_type": MemoryType.SEMANTIC,
        "tags": ["test"],
        "source": "stated",
        "confidence": 1.0,
    }
    defaults.update(kwargs)
    return Memory.create(content=content, **defaults)


def test_store_creates_registry_row(store: DurableMemoryStore):
    mem = _make_memory("store test")
    store.store(mem)

    retrieved = store.retrieve(mem.id)
    assert retrieved is not None
    assert retrieved.content == "store test"
    assert retrieved.memory_type == MemoryType.SEMANTIC


def test_store_writes_event_to_ledger(store: DurableMemoryStore):
    mem = _make_memory("ledger test")
    store.store(mem)

    # Verify event was written
    from animus_kernel.memory.stores.durable import _EventLedgerRow

    with store._session_factory() as session:
        events = session.query(_EventLedgerRow).all()
        assert len(events) >= 1
        assert any(e.event_kind == "memory.stored" for e in events)


def test_update_increments_version(store: DurableMemoryStore):
    mem = _make_memory("version test")
    store.store(mem)

    mem.content = "updated content"
    ok = store.update(mem)
    assert ok is True

    retrieved = store.retrieve(mem.id)
    assert retrieved is not None
    assert retrieved.content == "updated content"
    assert retrieved.version == 2


def test_delete_marks_superseded(store: DurableMemoryStore):
    mem = _make_memory("delete test")
    store.store(mem)

    ok = store.delete(mem.id)
    assert ok is True

    retrieved = store.retrieve(mem.id)
    assert retrieved is None


def test_search_finds_matching_content(store: DurableMemoryStore):
    store.store(_make_memory("apple pie recipe"))
    store.store(_make_memory("banana bread recipe"))
    store.store(_make_memory("unrelated"))

    results = store.search("recipe", limit=10)
    assert len(results) == 2
    contents = {r.content for r in results}
    assert contents == {"apple pie recipe", "banana bread recipe"}


def test_search_respects_tier_filter(store: DurableMemoryStore):
    mem = _make_memory("secret")
    mem.sensitivity = Sensitivity.CONFIDENTIAL
    store.store(mem)

    public = store.search("secret", allowed_tiers={Sensitivity.PUBLIC})
    assert len(public) == 0

    confidential = store.search("secret", allowed_tiers={Sensitivity.CONFIDENTIAL})
    assert len(confidential) == 1


def test_list_all_returns_non_deleted(store: DurableMemoryStore):
    m1 = _make_memory("one")
    m2 = _make_memory("two")
    store.store(m1)
    store.store(m2)
    store.delete(m1.id)

    all_memories = store.list_all()
    assert len(all_memories) == 1
    assert all_memories[0].content == "two"


def test_get_all_tags_counts(store: DurableMemoryStore):
    m1 = _make_memory("a")
    m1.tags = ["foo", "bar"]
    m2 = _make_memory("b")
    m2.tags = ["foo"]
    store.store(m1)
    store.store(m2)

    tags = store.get_all_tags()
    assert tags.get("foo") == 2
    assert tags.get("bar") == 1


def test_store_with_sensitivity(store: DurableMemoryStore):
    mem = _make_memory("sensitive")
    mem.sensitivity = Sensitivity.SECRET
    store.store(mem)
    retrieved = store.retrieve(mem.id)
    assert retrieved.sensitivity == Sensitivity.SECRET


def test_store_with_tier(store: DurableMemoryStore):
    mem = _make_memory("tiered")
    mem.tier = MemoryTier.HOT
    store.store(mem)
    retrieved = store.retrieve(mem.id)
    assert retrieved.tier == MemoryTier.HOT


def test_search_by_source(store: DurableMemoryStore):
    store.store(_make_memory("learned", source="learned"))
    store.store(_make_memory("stated", source="stated"))
    results = store.search("learned", source="learned")
    assert len(results) == 1
    assert results[0].source == "learned"


def test_search_by_tags(store: DurableMemoryStore):
    m1 = _make_memory("a", tags=["foo", "bar"])
    m2 = _make_memory("b", tags=["foo"])
    store.store(m1)
    store.store(m2)
    results = store.search("a", tags=["foo", "bar"])
    assert len(results) == 1
    assert results[0].content == "a"


def test_search_min_confidence(store: DurableMemoryStore):
    store.store(_make_memory("high", confidence=0.9))
    store.store(_make_memory("low", confidence=0.3))
    results = store.search("h", min_confidence=0.5)
    assert len(results) == 1
    assert results[0].confidence == 0.9


def test_search_limit(store: DurableMemoryStore):
    for i in range(5):
        store.store(_make_memory(f"item {i}"))
    results = store.search("item", limit=3)
    assert len(results) == 3


def test_list_all_by_type(store: DurableMemoryStore):
    store.store(_make_memory("semantic", memory_type=MemoryType.SEMANTIC))
    store.store(_make_memory("episodic", memory_type=MemoryType.EPISODIC))
    results = store.list_all(memory_type=MemoryType.EPISODIC)
    assert len(results) == 1
    assert results[0].memory_type == MemoryType.EPISODIC


def test_search_by_type(store: DurableMemoryStore):
    store.store(_make_memory("shared semantic", memory_type=MemoryType.SEMANTIC))
    store.store(_make_memory("shared episodic", memory_type=MemoryType.EPISODIC))
    results = store.search("shared", memory_type=MemoryType.EPISODIC)
    assert len(results) == 1
    assert results[0].memory_type == MemoryType.EPISODIC


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_id", "hunter_os"),
        ("artifact_type", "monster"),
        ("subject_domain", "monster_hunter_wilds"),
        ("owner_id", "another-owner"),
        ("workspace_id", "another-workspace"),
    ],
)
@pytest.mark.parametrize("historical", [False, True])
def test_foreign_identity_never_loads_or_mutates(store, field, value, historical):
    """Even a legacy registry without uniqueness constraints must reject ID adoption."""
    from animus_kernel.memory.stores.durable import _EventLedgerRow, _ObjectRegistryRow

    foreign = _make_memory("foreign sentinel")
    own = _make_memory("owned sentinel", tags=["owned"])
    store.store(foreign)
    store.store(own)
    with store._session_factory() as session:
        row = session.query(_ObjectRegistryRow).filter_by(object_id=foreign.id).one()
        setattr(row, field, value)
        # No memory decoder can accept this payload: SQL must exclude it first.
        row.payload = {"sentinel": "foreign payload"}
        if historical:
            row.superseded_at = datetime.now(UTC)
        session.commit()
        before_events = session.query(_EventLedgerRow).count()
        before_rows = session.query(_ObjectRegistryRow).count()

    assert store.retrieve(foreign.id) is None
    assert [m.id for m in store.list_all()] == [own.id]
    assert [m.id for m in store.search("sentinel", limit=1)] == [own.id]
    assert store.get_all_tags() == {"owned": 1}
    updated = store.update(foreign)
    assert updated is False
    deleted = store.delete(foreign.id)
    assert deleted is False
    with pytest.raises(PermissionError, match="another registry scope"):
        store.store(foreign)

    with store._session_factory() as session:
        assert session.query(_EventLedgerRow).count() == before_events
        assert session.query(_ObjectRegistryRow).count() == before_rows
        row = session.query(_ObjectRegistryRow).filter_by(object_id=foreign.id).one()
        assert getattr(row, field) == value
        assert row.payload == {"sentinel": "foreign payload"}
        assert (row.superseded_at is not None) is historical


def test_store_rejects_legacy_null_identity(tmp_path):
    """A nullable identity in an old database is unknown, never an owned ID."""
    from sqlalchemy import MetaData

    from animus_kernel.memory.stores.durable import (
        Base,
        _EventLedgerRow,
        _ObjectRegistryRow,
    )

    legacy = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(legacy)
    legacy.tables["object_registry"].c.owner_id.nullable = True
    store = DurableMemoryStore(f"sqlite:///{tmp_path / 'legacy.db'}")
    try:
        legacy.create_all(store._engine)
        memory = _make_memory("legacy sentinel")
        store.store(memory)
        with store._session_factory() as session:
            row = session.query(_ObjectRegistryRow).one()
            row.owner_id = None
            session.commit()

        assert store.retrieve(memory.id) is None
        with pytest.raises(PermissionError, match="another registry scope"):
            store.store(memory)
        with store._session_factory() as session:
            assert session.query(_ObjectRegistryRow).count() == 1
            assert session.query(_EventLedgerRow).count() == 1
            assert session.query(_ObjectRegistryRow).one().owner_id is None
    finally:
        store._engine.dispose()


def test_update_missing_returns_false(store: DurableMemoryStore):
    mem = _make_memory("orphan")
    updated = store.update(mem)
    assert updated is False


def test_delete_missing_returns_false(store: DurableMemoryStore):
    deleted = store.delete("nonexistent")
    assert deleted is False


def test_search_no_match(store: DurableMemoryStore):
    store.store(_make_memory("xyz"))
    results = store.search("abc")
    assert results == []


def test_store_multiple_events_in_ledger(store: DurableMemoryStore):
    mem = _make_memory("multi-event")
    store.store(mem)
    store.update(mem)
    store.delete(mem.id)

    from animus_kernel.memory.stores.durable import _EventLedgerRow

    with store._session_factory() as session:
        # object_refs is JSON array; filter via JSON contains
        events = session.query(_EventLedgerRow).all()
        # Check that events for this memory exist somewhere in the ledger
        matching = [e for e in events if mem.id in (e.object_refs or [])]
        kinds = {e.event_kind for e in matching}
        assert "memory.stored" in kinds
        assert "memory.updated" in kinds
        assert "memory.deleted" in kinds


def test_versioning_fields_preserved(store: DurableMemoryStore):
    mem = _make_memory("versioned")
    mem.version = 3
    mem.parent_id = "parent-123"
    mem.change_summary = "updated content"
    store.store(mem)
    retrieved = store.retrieve(mem.id)
    assert retrieved.version == 3
    assert retrieved.parent_id == "parent-123"
    assert retrieved.change_summary == "updated content"


# ---------------------------------------------------------------------------
# Adversarial tests for _upsert_registry_row correctness
# ---------------------------------------------------------------------------


def test_upsert_only_supersedes_current_version(store: DurableMemoryStore):
    """Updating a memory must leave exactly one non-superseded row."""
    mem = _make_memory("version test")
    store.store(mem)  # v1
    mem.content = "updated"  # v2
    store.update(mem)
    mem.content = "again"  # v3
    store.update(mem)

    from animus_kernel.memory.stores.durable import _ObjectRegistryRow

    with store._session_factory() as session:
        # Total rows for this object_id should be 3
        all_rows = (
            session.query(_ObjectRegistryRow).where(_ObjectRegistryRow.object_id == mem.id).all()
        )
        assert len(all_rows) == 3

        # Exactly one must be current (non-superseded)
        current = [r for r in all_rows if r.superseded_at is None]
        assert len(current) == 1
        assert current[0].object_version == 3

        # The two historical rows must have valid superseded_at timestamps
        historical = [r for r in all_rows if r.superseded_at is not None]
        assert len(historical) == 2


def test_store_after_delete_creates_clean_row(store: DurableMemoryStore):
    """Storing a new memory with a previously-deleted id must not crash or
    resurface the old superseded row."""
    mem = _make_memory("recycle-id")
    store.store(mem)
    store.delete(mem.id)

    # Re-create with the same id (artificial, but tests the lookup filter)
    mem2 = _make_memory("recycle-id")
    mem2.id = mem.id  # force reuse of deleted id
    store.store(mem2)

    retrieved = store.retrieve(mem.id)
    assert retrieved is not None
    assert retrieved.content == "recycle-id"

    from animus_kernel.memory.stores.durable import _ObjectRegistryRow

    with store._session_factory() as session:
        all_rows = (
            session.query(_ObjectRegistryRow).where(_ObjectRegistryRow.object_id == mem.id).all()
        )
        assert len(all_rows) == 2  # original deleted + new current
        current = [r for r in all_rows if r.superseded_at is None]
        assert len(current) == 1


def test_atomic_registry_and_event(store: DurableMemoryStore):
    """Registry row and event must be committed in the same transaction.

    We verify this indirectly: after a successful store(), querying the
    registry for the row must always return a matching event in the ledger.
    """
    mem = _make_memory("atomic")
    store.store(mem)

    from animus_kernel.memory.stores.durable import _EventLedgerRow, _ObjectRegistryRow

    with store._session_factory() as session:
        row = (
            session.query(_ObjectRegistryRow)
            .where(
                _ObjectRegistryRow.object_id == mem.id,
                _ObjectRegistryRow.superseded_at.is_(None),
            )
            .one()
        )

        events = (
            session.query(_EventLedgerRow)
            .where(
                _EventLedgerRow.event_kind == "memory.stored",
                _EventLedgerRow.object_refs.contains(mem.id),
            )
            .all()
        )
        assert len(events) == 1
        assert row.recorded_at is not None
        assert events[0].recorded_at is not None


def test_update_atomicity(store: DurableMemoryStore):
    """An update must atomically supersede the old row and write an event."""
    mem = _make_memory("atomic-update")
    store.store(mem)
    mem.content = "changed"
    store.update(mem)

    from animus_kernel.memory.stores.durable import _EventLedgerRow, _ObjectRegistryRow

    with store._session_factory() as session:
        # Old row is superseded
        old = (
            session.query(_ObjectRegistryRow)
            .where(
                _ObjectRegistryRow.object_id == mem.id,
                _ObjectRegistryRow.object_version == 1,
            )
            .one()
        )
        assert old.superseded_at is not None

        # New row is current
        new = (
            session.query(_ObjectRegistryRow)
            .where(
                _ObjectRegistryRow.object_id == mem.id,
                _ObjectRegistryRow.object_version == 2,
            )
            .one()
        )
        assert new.superseded_at is None

        # Exactly one update event
        events = (
            session.query(_EventLedgerRow)
            .where(
                _EventLedgerRow.event_kind == "memory.updated",
                _EventLedgerRow.object_refs.contains(mem.id),
            )
            .all()
        )
        assert len(events) == 1


def test_delete_atomicity(store: DurableMemoryStore):
    """Delete must atomically mark the row and write the event."""
    mem = _make_memory("atomic-delete")
    store.store(mem)
    store.delete(mem.id)

    from animus_kernel.memory.stores.durable import _EventLedgerRow, _ObjectRegistryRow

    with store._session_factory() as session:
        row = (
            session.query(_ObjectRegistryRow)
            .where(
                _ObjectRegistryRow.object_id == mem.id,
            )
            .one()
        )
        assert row.superseded_at is not None
        assert row.lifecycle_status == "deleted"

        events = (
            session.query(_EventLedgerRow)
            .where(
                _EventLedgerRow.event_kind == "memory.deleted",
                _EventLedgerRow.object_refs.contains(mem.id),
            )
            .all()
        )
        assert len(events) == 1

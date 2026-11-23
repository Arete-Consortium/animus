"""Focused tests for the typed durable knowledge-edge pilot."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from animus.durability.postgres_store import (
    ConcurrencyError,
    DurableObjectStore,
    KnowledgeEdgeRecord,
    KnowledgeEdgeType,
)
from animus.durability.scope import ObjectScope


def make_store(tmp_path: Path) -> DurableObjectStore:
    store = DurableObjectStore(f"sqlite:///{tmp_path / 'knowledge.db'}")
    store.create_tables()
    return store


def make_edge(**changes: object) -> KnowledgeEdgeRecord:
    values: dict[str, object] = {
        "edge_id": "edge-animus-forgehand",
        "subject_id": "repo-animus",
        "predicate": KnowledgeEdgeType.DEPENDS_ON,
        "object_id": "component-forgehand",
        "source_ref": "repo:AreteDriver/animus@5a5a9dd2",
        "provenance": "observed",
        "evidence_grade": "A",
        "confidence": 0.98,
        "epistemic_status": "supported",
        "created_by": "audit",
        "metadata": {"task_id": "audit-001"},
    }
    values.update(changes)
    return KnowledgeEdgeRecord(**values)


def test_edge_round_trip_neighbors_ledger_and_restart(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    edge = make_edge()
    edge_id, event_id = store.store_edge(edge)

    assert edge_id == edge.edge_id
    assert event_id.startswith("evt-")
    loaded = store.retrieve_edge(edge.edge_id)
    assert loaded is not None
    assert loaded.predicate is KnowledgeEdgeType.DEPENDS_ON
    assert loaded.source_ref == edge.source_ref
    assert loaded.evidence_grade == "A"
    assert store.neighbors("repo-animus")[0].object_id == "component-forgehand"
    assert store.get_edge_ledger_events(edge.edge_id)[0]["event_id"] == event_id

    store._engine.dispose()
    restarted = DurableObjectStore(f"sqlite:///{tmp_path / 'knowledge.db'}")
    assert restarted.retrieve_edge(edge.edge_id) is not None


def test_duplicate_current_edge_is_rejected(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.store_edge(make_edge())
    with pytest.raises(ConcurrencyError):
        store.store_edge(make_edge())


def test_supersession_preserves_history_and_hides_current(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    edge = make_edge()
    store.store_edge(edge)

    ok, event_id = store.supersede_edge(edge.edge_id, principal="reviewer")

    assert ok is True
    assert event_id.startswith("evt-")
    assert store.retrieve_edge(edge.edge_id) is None
    historical = store.retrieve_edge(edge.edge_id, version=1)
    assert historical is not None
    assert historical.lifecycle_status == "superseded"
    assert store.list_edges(include_superseded=True)[0].edge_id == edge.edge_id
    assert store.get_edge_ledger_events(edge.edge_id)[-1]["event_type"] == "superseded"


def test_scoped_store_cannot_read_or_write_foreign_edges(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'knowledge.db'}"
    admin = DurableObjectStore(url)
    admin.create_tables()
    scope = ObjectScope(
        owner_id="owner-test",
        workspace_id="ws-test",
        subject_domain="project",
        security_class="internal",
        schema_id="knowledge_edge",
        artifact_types=frozenset({"knowledge_edge"}),
    )
    scoped = DurableObjectStore(url, scope=scope)
    scoped.preflight()

    foreign = make_edge()
    admin.store_edge(foreign)
    assert scoped.retrieve_edge(foreign.edge_id) is None
    assert scoped.list_edges() == []
    with pytest.raises(PermissionError):
        scoped.store_edge(make_edge(edge_id="edge-foreign-write"))
    admin.supersede_edge(foreign.edge_id)
    with pytest.raises(PermissionError):
        scoped.store_edge(make_edge(edge_id=foreign.edge_id))

    owned = make_edge(
        edge_id="edge-owned",
        owner_id="owner-test",
        workspace_id="ws-test",
    )
    scoped.store_edge(owned)
    assert scoped.retrieve_edge(owned.edge_id) is not None
    assert admin.retrieve_edge(owned.edge_id) is not None


def test_edge_confidence_is_bounded() -> None:
    with pytest.raises(ValueError, match="confidence"):
        make_edge(confidence=1.1)


@pytest.mark.parametrize("direction", ["outgoing", "incoming", "both"])
@pytest.mark.parametrize("limit", [-1, 0, 1001, 1.5, True])
def test_neighbors_rejects_invalid_limits(tmp_path: Path, direction: str, limit: object) -> None:
    store = make_store(tmp_path)
    with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
        store.neighbors("repo-animus", direction=direction, limit=limit)


@pytest.mark.parametrize("days_from_now", [-3, 1])
def test_supersession_preserves_inactive_valid_time(tmp_path: Path, days_from_now: int) -> None:
    store = make_store(tmp_path)
    valid_from = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    valid_to = valid_from + timedelta(days=1)
    edge = make_edge(valid_from=valid_from, valid_to=valid_to)
    store.store_edge(edge)
    assert store.supersede_edge(edge.edge_id)[0]
    historical = store.retrieve_edge(edge.edge_id, version=1)
    assert historical is not None
    assert historical.valid_from == valid_from
    assert historical.valid_to == valid_to
    assert historical.superseded_at is not None

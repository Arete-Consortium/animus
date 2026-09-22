"""Cross-client migrations and actual shared-registry isolation regressions.

HUNTER_TEST_DATABASE_URL optionally enables PostgreSQL cases in a unique,
disposable schema. Never uses ANIMUS_DATABASE_URL or the operator's data.
"""

from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, event, inspect, select, text

from animus.durability import postgres_store as db
from animus.durability.schema import SchemaCompatibilityError
from animus.durability.scope import ObjectScope

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path):
    if request.param == "sqlite":
        yield f"sqlite:///{tmp_path / 'registry.db'}"
        return
    url = os.environ.get("HUNTER_TEST_DATABASE_URL")
    if not url:
        pytest.skip("HUNTER_TEST_DATABASE_URL not supplied")
    admin = create_engine(url, hide_parameters=True)
    schema = f"hunter_test_{uuid.uuid4().hex}"
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_url = admin.url.update_query_dict({"options": f"-csearch_path={schema}"})
    try:
        yield scoped_url.render_as_string(hide_password=False)
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def config(url: str) -> Config:
    cfg = Config(str(ROOT / "database/alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


@pytest.fixture
def stores(database_url):
    command.upgrade(config(database_url), "head")
    admin = db.DurableObjectStore(database_url)
    scoped = db.DurableObjectStore(database_url, scope=ObjectScope.hunter("owner-test"))
    admin.preflight()
    scoped.preflight()
    yield admin, scoped
    scoped._engine.dispose()
    admin._engine.dispose()


def record(**changes) -> db.ObjectRecord:
    return replace(
        db.ObjectRecord(
            object_id="mhw-monster-example",
            schema_id="hunter_os",
            owner_id="owner-test",
            workspace_id="hunter-os",
            subject_domain="monster_hunter_wilds",
            artifact_type="monster",
            cognitive_role="knowledge",
            security_class="public",
            workflow_status="approved",
            payload={"synthetic": True},
        ),
        **changes,
    )


def counts(store) -> tuple[int, int, int]:
    with store._engine.connect() as connection:
        return tuple(
            connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in ("object_registry", "event_ledger", "outbox_entries")
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", "owner-other"),
        ("workspace_id", "ws-private"),
        ("subject_domain", "self"),
        ("security_class", "confidential"),
        ("schema_id", "private_notes"),
        ("artifact_type", "memory"),
        ("lifecycle_status", "archived"),
    ],
)
def test_scope_blocks_all_reads_and_writes(stores, field, value):
    admin, scoped = stores
    foreign = record(**{field: value})
    _, event_id = admin.store(foreign)
    point = datetime.now(timezone.utc) + timedelta(days=1)
    assert scoped.retrieve(foreign.object_id) is None
    assert scoped.retrieve_version(foreign.object_id, 1) is None
    assert scoped.as_of_valid_time(foreign.object_id, point) is None
    assert scoped.as_of_transaction_time(foreign.object_id, point) is None
    assert scoped.list_current() == []
    assert scoped.get_ledger_events(foreign.object_id) == []
    assert not scoped.verify_integrity(event_id)
    assert scoped.delete(foreign.object_id) == (False, "")
    assert scoped.update(record(), expected_version=1) == (False, "")
    with pytest.raises(PermissionError):
        scoped.store(foreign)
    with pytest.raises(PermissionError):
        scoped.update(foreign, expected_version=1)
    assert counts(admin) == (1, 1, 1)


def test_scope_reads_history_but_not_after_reclassification(stores):
    admin, scoped = stores
    item = record(valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc))
    _, first_event = scoped.store(item)
    item.payload = {"synthetic": "revision"}
    scoped.update(item, expected_version=1)
    assert scoped.retrieve_version(item.object_id, 1).payload == {"synthetic": True}
    assert len(scoped.get_ledger_events(item.object_id)) == 2
    assert scoped.verify_integrity(first_event)
    admin.update(replace(item, security_class="confidential"), expected_version=2)
    assert scoped.retrieve_version(item.object_id, 1) is None
    assert scoped.get_ledger_events(item.object_id) == []
    assert not scoped.verify_integrity(first_event)


def test_scope_requires_validation_and_expected_version(stores, monkeypatch):
    admin, scoped = stores
    scoped.store(record())
    with pytest.raises(ValueError, match="expected_version"):
        scoped.update(record())
    monkeypatch.setattr(db, "_HAS_CONTRACTS", False)
    with pytest.raises(db.LedgerValidationError, match="validation"):
        scoped.update(record(), expected_version=1)
    with pytest.raises(RuntimeError, match="contracts"):
        db.DurableObjectStore(admin.database_url, scope=ObjectScope.hunter("owner-test"))
    assert counts(admin) == (1, 1, 1)


def test_scope_cannot_use_global_outbox(stores):
    _, scoped = stores
    with pytest.raises(PermissionError):
        scoped.claim_outbox_entries("test")
    with pytest.raises(PermissionError):
        scoped.acknowledge_outbox_entry("any-id")


def test_duplicate_create_and_stale_update_leave_no_partial_evidence(stores):
    admin, scoped = stores
    scoped.store(record())
    with pytest.raises(db.ConcurrencyError):
        scoped.store(record())
    scoped.update(record(payload={"new": True}), expected_version=1)
    with pytest.raises(db.ConcurrencyError):
        scoped.update(record(), expected_version=1)
    assert counts(admin) == (2, 2, 2)


def test_failure_after_event_rolls_back_entire_transaction(stores, monkeypatch):
    admin, scoped = stores
    scoped.store(record())

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic outbox failure")

    monkeypatch.setattr(scoped, "_enqueue_outbox", fail)
    with pytest.raises(RuntimeError, match="synthetic"):
        scoped.update(record(payload={"bad": True}), expected_version=1)
    assert scoped.retrieve(record().object_id).version == 1
    assert counts(admin) == (1, 1, 1)
    with pytest.raises(RuntimeError, match="synthetic"):
        scoped.store(record(object_id="mhw-monster-another"))
    assert counts(admin) == (1, 1, 1)


def test_effective_time_is_independent_of_import_time(stores):
    _, scoped = stores
    item = record()
    scoped.store(item)
    current = scoped.retrieve(item.object_id)
    assert current.valid_from is None
    assert current.recorded_at is not None
    effective = datetime(2026, 1, 1, tzinfo=timezone.utc)
    scoped.update(replace(item, valid_from=effective), expected_version=1)
    assert scoped.retrieve(item.object_id).valid_from.date() == effective.date()


def test_effective_interval_and_deleted_history(stores):
    _, scoped = stores
    start = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=-8)))
    end = start + timedelta(days=1)
    item = record(valid_from=start, valid_to=end)
    scoped.store(item)
    assert scoped.as_of_valid_time(item.object_id, start - timedelta(seconds=1)) is None
    assert scoped.as_of_valid_time(item.object_id, start).valid_from == start
    assert scoped.as_of_valid_time(item.object_id, end) is None
    scoped.delete(item.object_id)
    assert scoped.retrieve_version(item.object_id, 1) is None
    assert scoped.as_of_valid_time(item.object_id, start) is None
    assert scoped.get_ledger_events(item.object_id) == []


def test_invalid_effective_dates_leave_no_rows(stores):
    admin, scoped = stores
    with pytest.raises(db.LedgerValidationError, match="timezone-aware"):
        scoped.store(record(valid_from=datetime(2026, 1, 1)))
    point = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(db.LedgerValidationError, match="later"):
        scoped.store(record(valid_from=point, valid_to=point))
    assert counts(admin) == (0, 0, 0)


def test_legacy_unscoped_delete_closes_valid_time(stores):
    admin, _ = stores
    item = record()
    admin.store(item)
    admin.update(item, expected_version=1)
    admin.delete(item.object_id)
    assert admin.as_of_valid_time(item.object_id, datetime.now(timezone.utc)) is None


def test_core_and_kernel_share_migrated_schema(stores):
    from animus_kernel.memory.stores.durable import DurableMemoryStore
    from animus_kernel.memory.types import Memory, MemoryType

    admin, scoped = stores
    kernel = DurableMemoryStore(database_url=admin.database_url)
    try:
        memory = Memory.create("synthetic private sentinel", MemoryType.SEMANTIC)
        kernel.store(memory)
        scoped.store(record())
        assert kernel.retrieve(memory.id).content == memory.content
        assert scoped.retrieve(memory.id) is None
        assert len(scoped.list_current()) == 1
        # Kernel records both its write and the retrieval above.
        assert counts(admin) == (2, 3, 1)
        memory.content = "synthetic private revision"
        assert kernel.update(memory)
        assert kernel.retrieve(memory.id).content == memory.content
        assert kernel.delete(memory.id)
        assert kernel.retrieve(memory.id) is None
        assert scoped.retrieve(record().object_id) is not None
    finally:
        kernel._engine.dispose()


def test_simultaneous_writers_have_one_winner(stores):
    admin, scoped = stores
    scoped.store(record())
    barrier = threading.Barrier(2)

    def attempt(index):
        writer = db.DurableObjectStore(admin.database_url, scope=ObjectScope.hunter("owner-test"))

        def before_update(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith("UPDATE object_registry"):
                barrier.wait(timeout=10)

        event.listen(writer._engine, "before_cursor_execute", before_update)
        try:
            writer.update(record(payload={"writer": index}), expected_version=1)
            return "success"
        except db.ConcurrencyError:
            return "conflict"
        finally:
            writer._engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(attempt, (1, 2)))
    assert outcomes == ["conflict", "success"]
    assert counts(admin) == (2, 2, 2)


def test_ledger_tampering_is_detected(stores):
    admin, scoped = stores
    _, event_id = scoped.store(record())
    with admin._session_factory.begin() as session:
        row = session.execute(select(db._LedgerEventRow)).scalar_one()
        row.event_data = {**row.event_data, "payload": {"tampered": True}}
    assert not scoped.verify_integrity(event_id)


def test_migration_round_trip_and_downgrade_data_guard(database_url):
    cfg = config(database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "001")
    command.upgrade(cfg, "head")
    store = db.DurableObjectStore(database_url)
    try:
        store.preflight()
        store.store(record())
        with pytest.raises(RuntimeError, match="evidence"):
            command.downgrade(cfg, "001")
        assert store.retrieve(record().object_id) is not None
    finally:
        store._engine.dispose()


def test_migration_rejects_unknown_layout_without_changes(database_url):
    cfg = config(database_url)
    command.upgrade(cfg, "001")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE event_ledger ADD COLUMN unexpected INTEGER"))
        before = inspect(engine).get_table_names()
        with pytest.raises(RuntimeError, match="Unknown"):
            command.upgrade(cfg, "head")
        assert inspect(engine).get_table_names() == before
        assert "tags" not in {c["name"] for c in inspect(engine).get_columns("object_registry")}
        store = db.DurableObjectStore(database_url)
        with pytest.raises(SchemaCompatibilityError):
            store.create_tables()
        store._engine.dispose()
    finally:
        engine.dispose()


@pytest.mark.parametrize("duplicate", [False, True])
def test_migration_preserves_existing_evidence_or_refuses_duplicates(database_url, duplicate):
    cfg = config(database_url)
    command.upgrade(cfg, "001")
    engine = create_engine(database_url)
    try:
        registry = Table("object_registry", MetaData(), autoload_with=engine)
        ledger = Table("event_ledger", MetaData(), autoload_with=engine)
        values = {
            key: value
            for key, value in asdict(record()).items()
            if key in registry.c and value is not None
        }
        values.update(id=1, object_version=1, content_sha256="0" * 64)
        with engine.begin() as connection:
            connection.execute(registry.insert().values(**values))
            connection.execute(
                ledger.insert().values(
                    id=1,
                    event_kind="memory.stored",
                    actor_refs=["original"],
                    object_refs=[values["object_id"]],
                    event_data={"sentinel": "preserve"},
                    idempotency_key="existing-event",
                )
            )
            if duplicate:
                connection.execute(
                    registry.insert().values(**{**values, "id": 2, "object_version": 2})
                )
        if duplicate:
            with pytest.raises(RuntimeError, match="Duplicate current"):
                command.upgrade(cfg, "head")
            assert "tags" not in {c["name"] for c in inspect(engine).get_columns("object_registry")}
            assert "outbox_entries" not in inspect(engine).get_table_names()
        else:
            command.upgrade(cfg, "head")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    select(registry.c.payload).where(registry.c.id == 1)
                ).scalar_one()
                == values["payload"]
            )
            assert connection.execute(select(ledger.c.event_data)).scalar_one() == {
                "sentinel": "preserve"
            }
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == ("001" if duplicate else "002")
    finally:
        engine.dispose()


def test_database_url_is_not_logged(tmp_path, caplog, monkeypatch):
    import logging

    # Alembic and application logging can disable propagation; prove the
    # assertion observes the initialization log instead of an empty capture.
    monkeypatch.setattr(db.logger, "disabled", False)
    monkeypatch.setattr(db.logger, "propagate", True)
    monkeypatch.setattr(logging.getLogger("animus"), "propagate", True)
    with caplog.at_level("DEBUG", logger="animus.durability.postgres_store"):
        store = db.DurableObjectStore(f"sqlite:///{tmp_path / 'private-location.db'}")
    store._engine.dispose()
    assert "DurableObjectStore initialized" in caplog.text
    assert "private-location" not in caplog.text


def test_operator_preflight_is_read_only(stores, monkeypatch, capsys):
    from animus.durability.cli import main

    admin, scoped = stores
    scoped.store(record())
    monkeypatch.setenv("ANIMUS_DATABASE_URL", admin.database_url)
    before = counts(admin)
    assert main(["preflight"]) == 0
    assert "compatible" in capsys.readouterr().out
    assert counts(admin) == before


def test_operator_preflight_suppresses_connection_details(monkeypatch, capsys):
    from animus.durability.cli import main

    def failed(*args, **kwargs):
        raise RuntimeError("synthetic-secret-connection-detail")

    monkeypatch.setattr(db, "DurableObjectStore", failed)
    assert main(["preflight"]) == 2
    captured = capsys.readouterr()
    assert "synthetic-secret" not in captured.err + captured.out


def test_hunter_envelope_contract_and_generated_model():
    from dataclasses import asdict

    from animus_contracts import validate
    from animus_types.object_version import ObjectVersion

    payload = asdict(record())
    payload["object_version"] = payload.pop("version")
    payload["recorded_at"] = datetime.now(timezone.utc).isoformat()
    payload["content_sha256"] = "0" * 64
    validate(payload, "object_version")
    parsed = ObjectVersion.model_validate(payload)
    assert parsed.workspace_id == "hunter-os"

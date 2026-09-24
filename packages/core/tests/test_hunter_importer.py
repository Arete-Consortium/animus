"""Real migration-created SQL transactions; no production databases or game approvals."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from animus.durability.batch import BatchChange, apply_batch, record_fingerprint
from animus.durability.postgres_store import ConcurrencyError, DurableObjectStore
from animus.durability.scope import ObjectScope
from animus.hunter_os.import_cli import main
from animus.hunter_os.importer import HunterImportError, HunterOSImporter, ImportPlan
from animus.hunter_os.repository import HunterOSRepository, HunterOSReviewRepository

from . import test_registry_compatibility as registry

stores = registry.stores
database_url = registry.database_url
counts = registry.counts
record = registry.record

AS_OF = date(2026, 9, 24)
ROOT = Path(__file__).resolve().parents[3]
RATHIAN = "mhw-monster-rathian"


@pytest.fixture
def source_root(tmp_path):
    destination = tmp_path / "sources"
    shutil.copytree(ROOT / "integrations/hunter_review/sources", destination)
    return destination


def revise(root, *, path="records/rathian.yaml", append="\n# Source revision\n"):
    source = root / path
    source.write_text(source.read_text() + append)
    manifest = root / "provenance.json"
    payload = json.loads(manifest.read_text())
    next(f for f in payload["files"] if f["path"] == path)["sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    manifest.write_text(json.dumps(payload))


def test_apply_preserves_evidence_and_is_invisible_to_chat(stores):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    plan = importer.plan(as_of=AS_OF)
    assert counts(admin) == (0, 0, 0)
    assert [i.action for i in plan.items] == ["create"] * 4
    result = importer.apply(ImportPlan.from_json(plan.to_json()))
    assert [r.outcome for r in result.records] == ["created"] * 4
    assert result.held == 105
    assert counts(admin) == (4, 4, 4)
    for item in plan.items:
        row = scoped.retrieve(item.object_id)
        assert row.workflow_status == "candidate"
        assert row.epistemic_status == "unverified"
        assert row.valid_from is None and row.valid_to is None
        assert HunterOSRepository(scoped).get(item.object_id) is None
        assert HunterOSReviewRepository(scoped).inspect(item.object_id).record.status == "review"
        event = scoped.get_ledger_events(item.object_id)[0]
        evidence = event["payload"]["metadata"]["hunter_import"]
        raw = evidence["source"]["raw_text"].encode()
        assert hashlib.sha256(raw).hexdigest() == evidence["source"]["provenance"]["sha256"]
        assert row.trace_id.startswith("hunter-import:")
        assert scoped.verify_integrity(event["event_id"])
        assert evidence["source_claims"]["status"] == "verified"


def test_replay_replan_and_new_audit_day_are_noops(stores):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    plan = importer.plan(as_of=AS_OF)
    importer.apply(plan)
    for candidate in (plan, importer.plan(as_of=AS_OF), importer.plan(as_of=date(2026, 9, 25))):
        result = importer.apply(candidate)
        assert all(r.outcome == "unchanged" and r.event_id is None for r in result.records)
        assert counts(admin) == (4, 4, 4)


def test_source_only_change_creates_one_version_with_raw_evidence(stores, source_root):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    first = importer.plan(source_root=source_root, as_of=AS_OF)
    importer.apply(first, source_root=source_root)
    revise(source_root)
    second = importer.plan(source_root=source_root, as_of=AS_OF)
    assert {i.object_id for i in second.items if i.action == "update"} == {RATHIAN}
    result = importer.apply(second, source_root=source_root)
    assert [r.outcome for r in result.records].count("updated") == 1
    assert counts(admin) == (5, 5, 5)
    assert scoped.retrieve(RATHIAN).version == 2
    assert scoped.retrieve_version(RATHIAN, 1).valid_to is None
    assert scoped.get_ledger_events(RATHIAN)[-1]["payload"]["metadata"]["hunter_import"]["source"][
        "raw_text"
    ].endswith("# Source revision\n")
    with pytest.raises(HunterImportError, match="changed"):
        importer.apply(first, source_root=source_root)
    assert counts(admin) == (5, 5, 5)


def test_unrelated_forum_edit_does_not_reversion_records(stores, source_root):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    importer.apply(importer.plan(source_root=source_root, as_of=AS_OF), source_root=source_root)
    revise(source_root, path="forum/weapons.md")
    result = importer.apply(
        importer.plan(source_root=source_root, as_of=AS_OF), source_root=source_root
    )
    assert all(r.outcome == "unchanged" for r in result.records)
    assert counts(admin) == (4, 4, 4)


@pytest.mark.parametrize("stage", ["new", "update"])
def test_late_outbox_failure_rolls_back_entire_batch(stores, source_root, monkeypatch, stage):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    before = (0, 0, 0)
    if stage == "update":
        importer.apply(importer.plan(source_root=source_root, as_of=AS_OF), source_root=source_root)
        for path in sorted((source_root / "records").glob("*.yaml")):
            revise(source_root, path=f"records/{path.name}")
        before = (4, 4, 4)
    original = scoped._enqueue_outbox
    calls = 0

    def fail_late(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise RuntimeError("synthetic outbox failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(scoped, "_enqueue_outbox", fail_late)
    with pytest.raises(RuntimeError, match="synthetic"):
        importer.apply(importer.plan(source_root=source_root, as_of=AS_OF), source_root=source_root)
    assert counts(admin) == before
    if stage == "update":
        assert all(
            scoped.retrieve(i.object_id).version == 1
            for i in importer.plan(source_root=source_root, as_of=AS_OF).items
        )


def test_changed_registry_baseline_rejects_whole_update_batch(stores, source_root):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    importer.apply(importer.plan(source_root=source_root, as_of=AS_OF), source_root=source_root)
    for path in sorted((source_root / "records").glob("*.yaml")):
        revise(source_root, path=f"records/{path.name}")
    stale = importer.plan(source_root=source_root, as_of=AS_OF)
    current = scoped.retrieve(RATHIAN)
    current.payload["notes"].append("Concurrent edit")
    scoped.update(current, expected_version=1)
    with pytest.raises(HunterImportError, match="baseline"):
        importer.apply(stale, source_root=source_root)
    assert counts(admin) == (5, 5, 5)
    assert scoped.retrieve(RATHIAN).payload["notes"][-1] == "Concurrent edit"


def test_approved_record_cannot_be_overwritten_even_with_forged_plan(stores):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    plan = importer.plan(as_of=AS_OF)
    importer.apply(plan)
    current = scoped.retrieve(RATHIAN)
    current.workflow_status = "approved"
    scoped.update(current, expected_version=1)
    fresh = importer.plan(as_of=AS_OF)
    assert "registry.protected_record" in fresh.issues
    forged = replace(
        fresh, issues=(), items=tuple(replace(i, action="update") for i in fresh.items)
    )
    with pytest.raises(HunterImportError, match="conflicts"):
        importer.apply(forged)
    assert counts(admin) == (5, 5, 5)


@pytest.mark.parametrize("deleted", [False, True])
def test_private_or_historical_identity_collision_rolls_back(stores, deleted):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)

    private = record(object_id=RATHIAN, owner_id="owner-private", security_class="confidential")
    admin.store(private)
    if deleted:
        admin.delete(private.object_id)
    before = counts(admin)
    plan = importer.plan(as_of=AS_OF)
    assert "owner-private" not in plan.to_json()
    with pytest.raises(HunterImportError, match="identity"):
        importer.apply(plan)
    assert counts(admin) == before
    assert admin.retrieve_version(RATHIAN, 1).owner_id == "owner-private"
    if deleted:
        assert admin.retrieve(RATHIAN) is None


def test_tampered_preview_or_inventory_cannot_be_applied(stores):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    plan = importer.plan(as_of=AS_OF)
    for forged in (
        replace(plan, preview_json=plan.preview_json.replace('"review"', '"verified"')),
        replace(plan, items=plan.items[:-1]),
        replace(plan, items=plan.items + plan.items[:1]),
    ):
        with pytest.raises(HunterImportError):
            importer.apply(forged)
    assert counts(admin) == (0, 0, 0)


def test_destination_and_owner_binding(stores):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    plan = importer.plan(as_of=AS_OF)
    with pytest.raises(ValueError, match="scope"):
        HunterOSImporter(admin)
    for forged in (replace(plan, destination="a" * 64), replace(plan, owner_id="other")):
        with pytest.raises(HunterImportError, match="destination"):
            importer.apply(forged)
    assert counts(admin) == (0, 0, 0)


def test_structural_conflict_prevents_partial_import(stores, source_root):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    revise(source_root, append="\nunmapped: must review\n")
    plan = importer.plan(source_root=source_root, as_of=AS_OF)
    assert "source.conversion_conflicts" in plan.issues
    with pytest.raises(HunterImportError, match="conflicts"):
        importer.apply(plan, source_root=source_root)
    assert counts(admin) == (0, 0, 0)


@pytest.mark.parametrize("existing", [False, True])
def test_concurrent_identical_imports_commit_once(stores, source_root, existing):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    if existing:
        importer.apply(importer.plan(source_root=source_root, as_of=AS_OF), source_root=source_root)
        for path in sorted((source_root / "records").glob("*.yaml")):
            revise(source_root, path=f"records/{path.name}")
    plan = importer.plan(source_root=source_root, as_of=AS_OF)

    def apply_once():
        worker = DurableObjectStore(scoped.database_url, scope=ObjectScope.hunter("owner-test"))
        try:
            return HunterOSImporter(worker).apply(plan, source_root=source_root)
        except HunterImportError:
            return None  # Simultaneous creates may lose the unique-key race; retry safely.
        finally:
            worker._engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: apply_once(), range(2)))
    assert any(r is not None for r in results)
    replay = HunterOSImporter(scoped).apply(plan, source_root=source_root)
    assert all(r.outcome == "unchanged" for r in replay.records)
    assert counts(admin) == ((8, 8, 8) if existing else (4, 4, 4))


def test_batch_requires_scope_expected_version_and_unique_ids(stores):
    admin, scoped = stores

    change = BatchChange(
        record=record(), expected_version=0, expected_fingerprint=None, evidence={}
    )
    for bad in (
        (),
        (change, change),
        (replace(change, expected_version=True),),
        (replace(change, expected_version=1),),
    ):
        with pytest.raises(ValueError):
            apply_batch(scoped, bad)
    with pytest.raises(ValueError, match="scoped"):
        apply_batch(admin, (change,))
    with pytest.raises(PermissionError):
        apply_batch(scoped, (replace(change, record=replace(record(), owner_id="other")),))
    assert counts(admin) == (0, 0, 0)


def test_fingerprint_detects_out_of_band_envelope_change(stores):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    importer.apply(importer.plan(as_of=AS_OF))
    current = scoped.retrieve(RATHIAN)
    before = record_fingerprint(current)
    candidate = copy.deepcopy(current)
    candidate.payload["notes"].append("new proposal")
    with admin._engine.begin() as connection:
        connection.execute(
            text("UPDATE object_registry SET workflow_status='approved' WHERE object_id=:id"),
            {"id": RATHIAN},
        )
    with pytest.raises(ConcurrencyError):
        apply_batch(
            scoped,
            (
                BatchChange(
                    record=candidate, expected_version=1, expected_fingerprint=before, evidence={}
                ),
            ),
        )
    assert counts(admin) == (4, 4, 4)


def test_cli_plan_and_explicit_apply_replay(stores, tmp_path, monkeypatch, capsys):
    admin, scoped = stores
    monkeypatch.setenv("ANIMUS_DATABASE_URL", scoped.database_url)
    path = tmp_path / "plan.json"
    status = main(["--owner", "owner-test", "plan", "--as-of", str(AS_OF), "--output", str(path)])
    assert status == 0
    assert counts(admin) == (0, 0, 0)
    assert json.loads(capsys.readouterr().out)["actions"] == {"create": 4}
    for _ in range(2):
        status = main(["--owner", "owner-test", "apply-review", "--plan", str(path)])
        assert status == 0
        assert json.loads(capsys.readouterr().out)["held"] == 105
    assert counts(admin) == (4, 4, 4)
    status = main(["--owner", "owner-test", "plan", "--as-of", str(AS_OF), "--output", str(path)])
    assert status == 1
    assert "postgresql" not in capsys.readouterr().err


def test_plan_strict_json_rejects_unknown_fields_and_boolean_version():
    for data in ({"extra": True}, {"format_version": "wrong"}):
        with pytest.raises(HunterImportError):
            ImportPlan.from_json(json.dumps(data))


@pytest.mark.parametrize(
    "url",
    ["sqlite:///registry.db", "sqlite:///:memory:", "sqlite:///file:/tmp/registry.db?uri=true"],
)
def test_ambiguous_sqlite_destination_is_rejected(url):
    store = DurableObjectStore(url, scope=ObjectScope.hunter("owner-test"))
    try:
        with pytest.raises(ValueError, match="absolute"):
            HunterOSImporter(store)
    finally:
        store._engine.dispose()


def test_plan_rejects_duplicate_keys_and_boolean_versions(stores):
    _, scoped = stores
    plan = HunterOSImporter(scoped).plan(as_of=AS_OF)
    data = json.loads(plan.to_json())
    data["items"][0]["expected_version"] = True
    with pytest.raises(HunterImportError):
        ImportPlan.from_json(json.dumps(data))
    duplicate = plan.to_json().replace('"owner_id":', '"owner_id": "other", "owner_id":', 1)
    with pytest.raises(HunterImportError):
        ImportPlan.from_json(duplicate)


def test_guard_rechecked_under_transaction_lock(stores):
    admin, scoped = stores
    importer = HunterOSImporter(scoped)
    importer.apply(importer.plan(as_of=AS_OF))
    current = scoped.retrieve(RATHIAN)
    candidate = copy.deepcopy(current)
    current.workflow_status = "approved"
    scoped.update(current, expected_version=1)
    from animus.hunter_os.importer import _owned

    # Even a caller who supplies the approved row's current version/fingerprint
    # cannot use the importer guard to overwrite it with an old review payload.
    with pytest.raises(PermissionError, match="protected"):
        apply_batch(
            scoped,
            (
                BatchChange(
                    record=candidate,
                    expected_version=2,
                    expected_fingerprint=record_fingerprint(scoped.retrieve(RATHIAN)),
                    evidence={},
                ),
            ),
            current_allowed=_owned,
        )
    assert scoped.retrieve(RATHIAN).workflow_status == "approved"
    assert counts(admin) == (5, 5, 5)

"""Synthetic domain evidence and real scoped SQL; no game facts or live services."""

from __future__ import annotations

import copy
import os
import uuid
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from animus.durability.postgres_store import DurableObjectStore, ObjectRecord
from animus.durability.scope import ObjectScope
from animus.hunter_os.audit import EligibilityPolicy, audit_record
from animus.hunter_os.models import HunterDataError, parse_record, record_payload
from animus.hunter_os.repository import (
    HunterOSRepository,
    HunterOSReviewRepository,
    HunterUnavailableError,
)

POLICY = EligibilityPolicy(as_of=date(2026, 9, 22))
EVIDENCE = {"text": "Synthetic feature", "source_ids": ["source-a"]}
HORN = {
    "notes": ["note-a", "note-b"],
    "source_ids": ["source-a"],
    "complete": True,
    "melodies": [
        {
            "name": "Synthetic melody",
            "note_sequence": ["note-a", "note-b"],
            "effect_ids": ["effect-a", "effect-b"],
            "source_ids": ["source-a"],
        }
    ],
    "echo_bubble": EVIDENCE,
    "special_performance": EVIDENCE,
}
BODIES = {
    "monster": {
        "weakness_primary": "Synthetic weakness",
        "targets": {"hunting_horn": ["Synthetic target"]},
        "fight_plan": ["Synthetic plan"],
    },
    "special_encounter": {
        "mechanics": [EVIDENCE],
        "capture_rule": "Synthetic rule",
        "timeline_complete": True,
        "phases": [{"name": "Synthetic phase", "mechanics": [EVIDENCE]}],
    },
    "weapon_type": {
        "weapon_type": "hunting_horn",
        "controls": {"encore": {"test-platform": "test-button"}},
        "rules": ["Exact weapon evidence required"],
        "core_loop": ["Synthetic loop"],
    },
    "exact_weapon": {"weapon_type": "hunting_horn", "upgrade_name": "Synthetic III", "horn": HORN},
    "hunting_horn_tree": {"exact_weapon_ids": ["mhw-exact-weapon"], "overview": [EVIDENCE]},
    "guide": {
        "topic": "Synthetic topic",
        "sections": {"Preparation": ["Synthetic encore instructions"]},
    },
    "farm_route": {
        "target_item_ids": ["mhw-item-reference"],
        "steps": [{"location": "Synthetic place", "method": EVIDENCE}],
    },
    "item_reference": {"uses": [EVIDENCE], "acquisition": [EVIDENCE]},
    "skill_reference": {"levels": [{"level": 1, "effect": EVIDENCE}]},
}


def payload(kind="monster", **changes):
    return copy.deepcopy(
        {
            "id": "mhw-" + kind.replace("_", "-"),
            "name": "Synthetic " + kind,
            "record_type": kind,
            "status": "verified",
            "verified_date": "2026-09-20",
            "sources": [
                {
                    "id": "source-a",
                    "document": "Synthetic test source",
                    "section": "Test section",
                    "content_sha256": "a" * 64,
                }
            ],
            **BODIES[kind],
            **changes,
        }
    )


@pytest.fixture(params=["sqlite", "postgresql"])
def store(request, tmp_path):
    admin = None
    if request.param == "sqlite":
        url = f"sqlite:///{tmp_path / 'hunter.db'}"
    else:
        target = os.getenv("HUNTER_TEST_DATABASE_URL")
        if not target:
            pytest.skip("HUNTER_TEST_DATABASE_URL not supplied")
        admin = create_engine(target, hide_parameters=True)
        schema = f"hunter_domain_{uuid.uuid4().hex}"
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = admin.url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(
            hide_password=False
        )
    scoped = None
    try:
        cfg = Config()
        cfg.set_main_option(
            "script_location", str(Path(__file__).resolve().parents[3] / "database/migrations")
        )
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
        command.upgrade(cfg, "head")
        scoped = DurableObjectStore(url, scope=ObjectScope.hunter("owner-test"))
        yield scoped
    finally:
        if scoped:
            scoped._engine.dispose()
        if admin:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()


def put(store, raw, **envelope):
    record = ObjectRecord(
        object_id=raw["id"],
        schema_id="hunter_os",
        owner_id="owner-test",
        workspace_id="hunter-os",
        subject_domain="monster_hunter_wilds",
        security_class="public",
        artifact_type=raw["record_type"],
        workflow_status="approved",
        epistemic_status="supported",
        payload=raw,
    )
    record = replace(record, **envelope)
    store.store(record)
    return record


@pytest.mark.parametrize("kind", BODIES)
def test_nine_record_types_round_trip_without_invented_dates(kind):
    raw = payload(kind)
    parsed = parse_record(raw)
    canonical = record_payload(parsed)
    assert record_payload(parse_record(canonical)) == canonical
    assert canonical["patch_version"] is None
    assert audit_record(parsed, POLICY).eligible
    assert canonical["sources"][0]["content_sha256"] == "a" * 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("verified_date", "not-a-date"),
        ("verified_date", "2026-02-30"),
        ("verified_date", "2026-09-20T00:00:00Z"),
        ("id", "rathian"),
        ("game", "monster_hunter_world"),
        ("schema_version", "9.0.0"),
        ("status", "trust-me"),
        ("patch_sensitive", "false"),
        ("name", 7),
        ("name", "  "),
        ("unexpected", "do not silently discard"),
    ],
)
def test_payload_rejects_malformed_or_coerced_fields(field, value):
    with pytest.raises(HunterDataError):
        parse_record(payload(**{field: value}))


def test_nested_unknown_fields_and_false_strings_rejected():
    raw = payload("exact_weapon")
    raw["horn"]["complete"] = "false"
    with pytest.raises(HunterDataError):
        parse_record(raw)
    raw = payload()
    raw["sources"][0]["credentials"] = "must-not-appear"
    with pytest.raises(HunterDataError) as error:
        parse_record(raw)
    assert "must-not-appear" not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"verified_date": None}, "verification.missing"),
        ({"verified_date": "2026-09-23"}, "verification.future"),
        ({"status": "review"}, "review.required"),
        ({"review_reasons": ["Needs exact evidence"]}, "review.required"),
        ({"sources": []}, "source.missing"),
        ({"sources": [{"id": "source-a", "document": "Synthetic"}]}, "source.locator"),
        ({"fight_plan": []}, "monster.incomplete"),
    ],
)
def test_incomplete_records_are_structural_but_held(changes, code):
    report = audit_record(parse_record(payload(**changes)), POLICY)
    assert not report.eligible
    assert code in {finding.code for finding in report.findings}


def test_patch_freshness_requires_explicit_policy_and_always_retains_warning():
    record = parse_record(payload(status="patch-sensitive", patch_version="test-patch"))
    assert not audit_record(record, POLICY).eligible
    fresh = EligibilityPolicy(as_of=POLICY.as_of, max_patch_age_days=2, current_patch="test-patch")
    report = audit_record(record, fresh)
    assert report.eligible and not report.auto_publishable
    assert "patch.caveat" in {f.code for f in report.findings}
    assert not audit_record(record, replace(fresh, max_patch_age_days=1)).eligible
    assert not audit_record(record, replace(fresh, current_patch="other-patch")).eligible
    assert not audit_record(record, replace(fresh, as_of=date(2026, 9, 19))).eligible


@pytest.mark.parametrize(
    "change",
    [
        {"complete": False},
        {"notes": []},
        {"melodies": []},
        {"echo_bubble": None},
        {"special_performance": None},
        {"source_ids": []},
        {"echo_bubble": {"text": "Synthetic", "source_ids": ["missing-source"]}},
    ],
)
def test_exact_horn_rejects_missing_feature_evidence(change):
    raw = payload("exact_weapon")
    raw["horn"].update(change)
    assert not audit_record(parse_record(raw), POLICY).eligible


def test_incomplete_encounter_timeline_is_a_visible_caveat():
    record = parse_record(payload("special_encounter", timeline_complete=False, phases=[]))
    report = audit_record(record, POLICY)
    assert report.eligible and not report.auto_publishable
    assert {f.code for f in report.findings} == {"encounter.timeline"}


@pytest.mark.parametrize("kind", BODIES)
def test_repository_reads_all_nine_types(store, kind):
    raw = payload(kind)
    put(store, raw)
    result = HunterOSRepository(store, policy=POLICY).get(raw["id"])
    assert result.record.record_type == kind
    assert result.version == 1
    assert result.valid_from is None and result.recorded_at is not None
    assert result.audit.eligible


def test_repository_requires_exact_scope(store):
    generic = DurableObjectStore(store.database_url)
    wrong = DurableObjectStore(
        store.database_url, scope=replace(store.scope, security_class="confidential")
    )
    try:
        for candidate in (generic, wrong):
            with pytest.raises(ValueError, match="scope"):
                HunterOSRepository(candidate)
    finally:
        generic._engine.dispose()
        wrong._engine.dispose()


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", "owner-other"),
        ("workspace_id", "ws-private"),
        ("security_class", "confidential"),
        ("subject_domain", "self"),
        ("schema_id", "private_notes"),
        ("artifact_type", "memory"),
        ("lifecycle_status", "archived"),
    ],
)
def test_repository_never_decodes_foreign_payloads(store, monkeypatch, field, value):
    admin = DurableObjectStore(store.database_url)
    try:
        raw = payload()
        raw["private_sentinel"] = "Never decode private data"
        put(admin, raw, **{field: value})
        repo = HunterOSRepository(store, policy=POLICY)
        review = HunterOSReviewRepository(store, policy=POLICY)

        def forbidden(*args):
            pytest.fail("out-of-scope data reached the domain decoder")

        monkeypatch.setattr(repo, "_decode", forbidden)
        assert repo.get(raw["id"]) is None
        assert repo.search("private") == ()
        assert review.history(raw["id"]) == ()
    finally:
        admin._engine.dispose()


def test_held_and_unapproved_data_only_available_to_operator(store):
    put(store, payload(status="review"))
    put(store, payload("guide"), workflow_status="candidate")
    repo = HunterOSRepository(store, policy=POLICY)
    review = HunterOSReviewRepository(store, policy=POLICY)
    assert repo.get("mhw-monster") is None
    assert repo.get("mhw-guide") is None
    assert repo.search("Synthetic") == ()
    assert not review.inspect("mhw-monster").audit.eligible
    assert not review.inspect("mhw-guide").audit.eligible
    assert not hasattr(repo, "store") and not hasattr(repo, "history")


def test_identity_mismatch_and_corruption_fail_closed(store):
    put(store, payload(), object_id="mhw-other")
    repo = HunterOSRepository(store, policy=POLICY)
    with pytest.raises(HunterDataError, match="envelope"):
        repo.get("mhw-other")
    with pytest.raises(HunterDataError):
        repo.search("Synthetic")


def test_variant_lookup_never_substitutes_normal_or_special(store):
    put(store, payload(variant="tempered"))
    put(store, payload("special_encounter"))
    repo = HunterOSRepository(store, policy=POLICY)
    assert repo.monster("mhw-monster") is None
    assert repo.monster("mhw-monster", variant="tempered") is not None
    assert repo.monster("mhw-special-encounter") is None


def test_tree_overview_cannot_satisfy_exact_horn_lookup(store):
    put(store, payload("hunting_horn_tree"))
    put(store, payload("weapon_type"))
    put(store, payload("exact_weapon"))
    repo = HunterOSRepository(store, policy=POLICY)
    assert repo.exact_weapon("mhw-hunting-horn-tree") is None
    assert repo.exact_weapon("mhw-weapon-type") is None
    assert [e.record.id for e in repo.horns_with_effects(["effect-a", "effect-b"])] == [
        "mhw-exact-weapon"
    ]
    assert repo.horns_with_effects(["effect-a", "missing-effect"]) == ()


def test_ammo_support_absence_unknown_and_handling_are_distinct(store):
    ammo = [
        {
            "ammo": "synthetic-ammo",
            "level": 1,
            "support": "supported",
            "rapid_fire": False,
            "source_ids": ["source-a"],
        },
        {"ammo": "synthetic-ammo", "level": 2, "support": "unknown"},
        {
            "ammo": "synthetic-ammo",
            "level": 3,
            "support": "unsupported",
            "source_ids": ["source-a"],
        },
    ]
    put(store, payload("exact_weapon", weapon_type="light_bowgun", horn=None, ammo_table=ammo))
    repo = HunterOSRepository(store, policy=POLICY)
    found = repo.bowguns_with_ammo("synthetic-ammo", level=1)
    assert len(found) == 1 and not found[0].audit.auto_publishable
    assert found[0].record.ammo_table[0].rapid_fire is False
    assert found[0].record.ammo_table[0].reload is None
    assert repo.bowguns_with_ammo("synthetic-ammo", level=2) == ()
    assert repo.bowguns_with_ammo("synthetic-ammo", level=3) == ()
    assert repo.bowguns_with_ammo("not-in-table") == ()


def test_search_limits_order_and_candidate_overflow(store):
    put(store, payload("guide", id="mhw-z", name="Twin"))
    put(store, payload("guide", id="mhw-a", name="Twin"))
    repo = HunterOSRepository(store, policy=POLICY)
    assert [e.record.id for e in repo.search("Encore")] == ["mhw-a", "mhw-z"]
    assert len(repo.search("Encore", limit=1)) == 1
    assert repo.search("   ") == ()
    for limit in (0, -1, 51, True):
        with pytest.raises(ValueError):
            repo.search("Encore", limit=limit)
    with pytest.raises(ValueError):
        repo.search("x" * 201)
    with pytest.raises(HunterUnavailableError, match="candidate"):
        HunterOSRepository(store, policy=POLICY, max_candidates=1).search("Encore")
    assert len(store.list_current(limit=1)) == 1


def test_history_respects_reclassification_and_deletion(store):
    raw = payload()
    obj = put(store, raw)
    store.update(replace(obj, payload=payload(name="Synthetic second")), expected_version=1)
    review = HunterOSReviewRepository(store, policy=POLICY)
    assert [e.version for e in review.history(obj.object_id)] == [2, 1]
    assert [e.version for e in review.history(obj.object_id, limit=1)] == [2]
    admin = DurableObjectStore(store.database_url)
    try:
        admin.update(replace(obj, security_class="confidential"), expected_version=2)
        assert review.history(obj.object_id) == ()
        assert review.inspect(obj.object_id) is None
    finally:
        admin._engine.dispose()
    put(store, payload("guide"))
    store.delete("mhw-guide")
    assert review.history("mhw-guide") == ()


def test_database_error_has_no_secret_or_fallback(store, monkeypatch):
    repo = HunterOSRepository(store, policy=POLICY)

    def fail(*args, **kwargs):
        raise OperationalError("synthetic-secret-sql", {}, RuntimeError("private"))

    monkeypatch.setattr(store, "retrieve", fail)
    with pytest.raises(HunterUnavailableError) as exc:
        repo.get("mhw-monster")
    assert "secret" not in str(exc.value) and exc.value.__cause__ is None


@pytest.mark.parametrize(
    "kind,changes,code",
    [
        ("special_encounter", {"mechanics": []}, "encounter.incomplete"),
        ("special_encounter", {"phases": []}, "encounter.phases"),
        ("weapon_type", {"controls": {}}, "weapon.incomplete"),
        ("weapon_type", {"exact_weapon_required": False}, "weapon.exact_required"),
        ("exact_weapon", {"weapon_type": "bow"}, "weapon.horn_mismatch"),
        ("exact_weapon", {"weapon_type": "light_bowgun", "horn": None}, "ammo.missing"),
        ("hunting_horn_tree", {"overview": []}, "tree.incomplete"),
        ("guide", {"sections": {}}, "guide.incomplete"),
        ("farm_route", {"steps": []}, "farm.incomplete"),
        ("item_reference", {"acquisition": []}, "item.incomplete"),
        ("skill_reference", {"levels": []}, "skill.levels"),
    ],
)
def test_family_specific_evidence_gates(kind, changes, code):
    report = audit_record(parse_record(payload(kind, **changes)), POLICY)
    assert not report.eligible
    assert code in {f.code for f in report.findings}


@pytest.mark.parametrize(
    "ammo,code",
    [
        ([{"ammo": "test", "support": "supported"}], "source.feature"),
        ([{"ammo": "test", "support": "unknown", "rapid_fire": False}], "ammo.contradiction"),
        (
            [
                {
                    "ammo": "test",
                    "support": "unsupported",
                    "recoil": "Synthetic",
                    "source_ids": ["source-a"],
                }
            ],
            "ammo.contradiction",
        ),
        (
            [{"ammo": "test", "support": "supported", "source_ids": ["source-a"]}] * 2,
            "ammo.duplicate",
        ),
    ],
)
def test_ammo_conflicts_and_unsupported_claims_are_held(ammo, code):
    record = parse_record(
        payload("exact_weapon", weapon_type="light_bowgun", horn=None, ammo_table=ammo)
    )
    report = audit_record(record, POLICY)
    assert not report.eligible
    assert code in {f.code for f in report.findings}


def test_dataclass_construction_cannot_bypass_boundary_validation():
    record = parse_record(payload())
    with pytest.raises(HunterDataError):
        record_payload(replace(record, patch_sensitive="false"))
    raw = payload("exact_weapon")
    raw["horn"]["melodies"][0]["note_sequence"] = ["not-on-this-horn"]
    assert not audit_record(parse_record(raw), POLICY).eligible
    raw = payload()
    raw["sources"] *= 2
    assert not audit_record(parse_record(raw), POLICY).eligible


@pytest.mark.parametrize(
    "kwargs",
    [
        {"as_of": "2026-09-22"},
        {"max_patch_age_days": -1},
        {"max_patch_age_days": True},
        {"current_patch": "  "},
    ],
)
def test_invalid_operator_policy_rejected(kwargs):
    with pytest.raises(ValueError):
        EligibilityPolicy(**kwargs)


def test_result_mutation_does_not_change_sql_or_later_reads(store):
    put(store, payload())
    repo = HunterOSRepository(store, policy=POLICY)
    entry = repo.get("mhw-monster")
    entry.record.targets["general"] = ("Unpersisted mutation",)
    assert "general" not in repo.get("mhw-monster").record.targets


def test_schema_version_mismatch_is_not_silently_reinterpreted(store):
    put(store, payload(), schema_version="2.0.0")
    with pytest.raises(HunterDataError, match="envelope"):
        HunterOSRepository(store, policy=POLICY).get("mhw-monster")


def test_specialist_query_input_bounds(store):
    repo = HunterOSRepository(store, policy=POLICY)
    for effects in ([], "effect-a", ["effect-a"] * 21, ["bad id"]):
        with pytest.raises(ValueError):
            repo.horns_with_effects(effects)
    for level in (-1, 0, True):
        with pytest.raises(ValueError):
            repo.bowguns_with_ammo("test", level=level)
    with pytest.raises(ValueError):
        repo.get("../../private")
    with pytest.raises(ValueError):
        repo.bowguns_with_ammo("test ammo")

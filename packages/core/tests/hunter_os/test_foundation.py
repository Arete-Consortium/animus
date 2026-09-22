"""Foundation tests for the Hunter OS domain."""

from pathlib import Path

from animus.hunter_os import (
    AuditSeverity,
    GuideRecord,
    HunterOSRepository,
    MonsterRecord,
    SpecialEncounterRecord,
    WeaponTypeRecord,
    audit_record,
)


def _repo() -> HunterOSRepository:
    data = Path(__file__).resolve().parents[2] / "animus" / "hunter_os" / "data"
    return HunterOSRepository(data)


def test_vertical_slice_loads() -> None:
    records = _repo().all()
    assert {record.id for record in records} == {
        "rathian",
        "hunting_horn",
        "combat_healer_hh_lbg",
        "omega_planetes",
    }


def test_rathian_semantics_preserve_weapon_specific_targets() -> None:
    record = _repo().get("rathian")
    assert isinstance(record, MonsterRecord)
    assert record.weakness_primary == "Dragon"
    assert record.targets["hunting_horn"] == ("Head",)
    assert record.targets["sever"] == ("Tail",)
    assert audit_record(record).publishable


def test_hunting_horn_preserves_horn_specific_rule() -> None:
    record = _repo().get("hunting_horn")
    assert isinstance(record, WeaponTypeRecord)
    assert record.controls["perform"]["xbox"] == "RT"
    report = audit_record(record)
    assert report.publishable
    assert not report.warnings


def test_combat_healer_is_structured_guide() -> None:
    record = _repo().get("combat_healer_hh_lbg")
    assert isinstance(record, GuideRecord)
    assert "Wide-Range" in record.sections["core_support"]
    assert audit_record(record).publishable


def test_special_encounter_warns_when_timeline_is_incomplete() -> None:
    record = _repo().get("omega_planetes")
    assert isinstance(record, SpecialEncounterRecord)
    report = audit_record(record)
    assert report.publishable
    assert any(
        finding.severity == AuditSeverity.WARN and finding.code == "special.timeline"
        for finding in report.findings
    )


def test_search() -> None:
    hits = _repo().search("healer")
    assert [record.id for record in hits] == ["combat_healer_hh_lbg"]

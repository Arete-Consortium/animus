"""Deterministic eligibility checks. Passing is evidence completeness, not fact checking."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal

from animus.hunter_os.models import (
    ExactWeaponRecord,
    FarmRouteRecord,
    GuideRecord,
    HuntingHornTreeRecord,
    ItemReferenceRecord,
    MonsterRecord,
    Record,
    SkillReferenceRecord,
    SpecialEncounterRecord,
    WeaponTypeRecord,
    parse_record,
    record_payload,
)


@dataclass(frozen=True, kw_only=True)
class EligibilityPolicy:
    """Operator policy; omit patch freshness limits to hold patch-sensitive facts."""

    as_of: date | None = None
    max_patch_age_days: int | None = None
    current_patch: str | None = None

    def __post_init__(self) -> None:
        if self.as_of is not None and type(self.as_of) is not date:
            raise ValueError("as_of must be a date.")
        if self.max_patch_age_days is not None and (
            type(self.max_patch_age_days) is not int or self.max_patch_age_days < 0
        ):
            raise ValueError("max_patch_age_days must be a nonnegative integer.")
        if self.current_patch is not None and not self.current_patch.strip():
            raise ValueError("current_patch must be nonempty when supplied.")


@dataclass(frozen=True, kw_only=True)
class AuditFinding:
    severity: Literal["warn", "block"]
    code: str
    message: str


@dataclass(frozen=True, kw_only=True)
class AuditReport:
    record_id: str
    findings: tuple[AuditFinding, ...]

    @property
    def eligible(self) -> bool:
        return not any(f.severity == "block" for f in self.findings)

    @property
    def auto_publishable(self) -> bool:
        return not self.findings


def _walk(value: Any) -> Iterator[Any]:
    if is_dataclass(value) and not isinstance(value, type):
        yield value
        for f in fields(value):
            yield from _walk(getattr(value, f.name))
    elif isinstance(value, (tuple, list)):
        for child in value:
            yield from _walk(child)
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)


def audit_record(record: Record, policy: EligibilityPolicy | None = None) -> AuditReport:
    """Reject malformed data; report review gates and preserve every caveat."""
    record = parse_record(record_payload(record))
    policy = policy or EligibilityPolicy()
    today = policy.as_of or datetime.now(timezone.utc).date()
    findings: list[AuditFinding] = []

    def add(code: str, message: str, severity: Literal["warn", "block"] = "block") -> None:
        finding = AuditFinding(severity=severity, code=code, message=message)
        if finding not in findings:
            findings.append(finding)

    if record.status == "review" or record.review_reasons:
        add("review.required", "Record requires operator review.")
    if record.verified_date is None:
        add("verification.missing", "Verification date is unknown.")
    elif record.verified_date > today:
        add("verification.future", "Verification date is in the future.")
    source_ids = {s.id for s in record.sources}
    if not source_ids:
        add("source.missing", "Source evidence is missing.")
    if len(source_ids) != len(record.sources):
        add("source.duplicate", "Source IDs must be unique within a record.")
    if any(not s.content_sha256 or not s.section for s in record.sources):
        add("source.locator", "Each source needs a content hash and section locator.")
    for node in _walk(record):
        if hasattr(node, "source_ids"):
            refs = node.source_ids
            if not refs or not set(refs).issubset(source_ids):
                # Unknown ammo is explicitly allowed to have no evidence yet.
                if getattr(node, "support", None) != "unknown" or refs:
                    add("source.feature", "A feature lacks resolvable source evidence.")

    sensitive = record.patch_sensitive or record.status == "patch-sensitive"
    if sensitive:
        add(
            "patch.caveat",
            "Patch-sensitive fact; retain its verification date and patch caveat.",
            "warn",
        )
        if policy.max_patch_age_days is None:
            add("patch.policy", "No patch freshness policy is configured.")
        elif (
            record.verified_date and (today - record.verified_date).days > policy.max_patch_age_days
        ):
            add("patch.stale", "Verification is older than the configured patch freshness limit.")
        if policy.current_patch is not None and record.patch_version != policy.current_patch:
            add("patch.mismatch", "Record has not been verified against the configured patch.")

    if isinstance(record, MonsterRecord):
        if not record.weakness_primary or not any(record.targets.values()) or not record.fight_plan:
            add(
                "monster.incomplete",
                "Monster needs weakness, role-specific targets and fight plan.",
            )
    elif isinstance(record, SpecialEncounterRecord):
        if not record.mechanics or not record.capture_rule:
            add("encounter.incomplete", "Encounter needs mechanics and capture rule.")
        if not record.timeline_complete:
            add(
                "encounter.timeline",
                "Encounter timeline is incomplete; do not imply full phase coverage.",
                "warn",
            )
        elif not record.phases or any(not phase.mechanics for phase in record.phases):
            add("encounter.phases", "A complete timeline needs populated phases.")
    elif isinstance(record, WeaponTypeRecord):
        if (
            not record.controls
            or not all(record.controls.values())
            or not record.core_loop
            or not record.rules
        ):
            add("weapon.incomplete", "Weapon type needs controls, rules and a core loop.")
        if (
            record.weapon_type in ("hunting_horn", "light_bowgun", "heavy_bowgun")
            and not record.exact_weapon_required
        ):
            add("weapon.exact_required", "Song and ammo facts require exact weapon evidence.")
    elif isinstance(record, ExactWeaponRecord):
        if record.weapon_type == "hunting_horn":
            horn = record.horn
            if (
                horn is None
                or not horn.complete
                or not horn.notes
                or not horn.melodies
                or horn.echo_bubble is None
                or horn.special_performance is None
            ):
                add(
                    "horn.incomplete",
                    "Exact horn needs notes, melodies, Echo Bubble and Special Performance evidence.",
                )
            if horn and any(not m.note_sequence or not m.effect_ids for m in horn.melodies):
                add("horn.melody", "Every melody needs its exact note sequence and effects.")
            if horn and any(not set(m.note_sequence).issubset(horn.notes) for m in horn.melodies):
                add("horn.notes", "Melody sequence uses a note absent from this exact horn.")
        elif record.horn is not None:
            add("weapon.horn_mismatch", "Horn facts are attached to a different weapon type.")
        if record.weapon_type in ("light_bowgun", "heavy_bowgun"):
            if not record.ammo_table:
                add("ammo.missing", "Exact bowgun ammo evidence is missing.")
            keys = [(a.ammo, a.level) for a in record.ammo_table]
            if len(keys) != len(set(keys)):
                add("ammo.duplicate", "Conflicting or duplicate ammo/level entries require review.")
            for ammo in record.ammo_table:
                if ammo.support == "unknown":
                    add("ammo.unknown", "Some ammo compatibility remains unknown.", "warn")
                if ammo.support != "supported" and any(
                    v is not None for v in (ammo.rapid_fire, ammo.reload, ammo.recoil)
                ):
                    add(
                        "ammo.contradiction",
                        "Unsupported or unknown ammo cannot assert handling properties.",
                    )
        elif record.ammo_table:
            add("weapon.ammo_mismatch", "Ammo facts are attached to a different weapon type.")
    elif isinstance(record, HuntingHornTreeRecord):
        if not record.exact_weapon_ids or not record.overview:
            add("tree.incomplete", "Horn tree needs exact weapon references and an overview.")
        add("tree.not_exact", "Tree overview is not proof of any exact horn's song set.", "warn")
    elif isinstance(record, GuideRecord):
        if not record.topic or not record.sections or not all(record.sections.values()):
            add("guide.incomplete", "Guide needs a topic and populated sections.")
    elif isinstance(record, FarmRouteRecord):
        if not record.target_item_ids or not record.steps:
            add("farm.incomplete", "Farm route needs target items and steps.")
    elif isinstance(record, ItemReferenceRecord):
        if not record.uses or not record.acquisition:
            add("item.incomplete", "Item reference needs uses and acquisition evidence.")
    elif isinstance(record, SkillReferenceRecord):
        levels = [level.level for level in record.levels]
        if not levels or len(levels) != len(set(levels)):
            add("skill.levels", "Skill reference needs unique evidenced levels.")
    return AuditReport(record_id=record.id, findings=tuple(findings))

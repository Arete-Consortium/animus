"""Versioned Hunter payloads; incomplete facts remain representable for review.

Dataclasses are the domain API. All persistence boundaries must use parse_record
or record_payload, which validate the discriminated union without scalar coercion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Any, ClassVar, Literal, cast

from pydantic import ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError

Text = Annotated[str, StringConstraints(min_length=1, max_length=8000, pattern=r"\S")]
RecordId = Annotated[str, StringConstraints(pattern=r"^mhw-[a-z0-9][a-z0-9_-]*$", max_length=128)]
SourceId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=128)]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
PositiveInt = Annotated[int, Field(gt=0)]
WeaponKind = Literal[
    "great_sword",
    "long_sword",
    "sword_and_shield",
    "dual_blades",
    "hammer",
    "hunting_horn",
    "lance",
    "gunlance",
    "switch_axe",
    "charge_blade",
    "insect_glaive",
    "light_bowgun",
    "heavy_bowgun",
    "bow",
]
TargetRole = Literal["general", "hunting_horn", "sever", "shot", "focus", "phase_specific"]
RecordStatus = Literal["verified", "patch-sensitive", "weapon-specific", "review"]


class _Strict:
    __pydantic_config__: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


@dataclass(frozen=True, kw_only=True)
class SourceRef(_Strict):
    """Locator and content hash identify the evidence an operator reviewed."""

    id: SourceId
    document: Text
    section: Text | None = None
    content_sha256: Digest | None = None
    url: Text | None = None
    source_revision: Text | None = None
    note: Text | None = None


@dataclass(frozen=True, kw_only=True)
class EvidenceText(_Strict):
    text: Text
    source_ids: tuple[SourceId, ...] = ()


@dataclass(frozen=True, kw_only=True)
class Relationship(_Strict):
    relation: Text
    record_id: RecordId


@dataclass(frozen=True, kw_only=True)
class HunterRecord(_Strict):
    id: RecordId
    name: Text
    record_type: str
    schema_version: Literal["1.0.0"] = "1.0.0"
    game: Literal["monster_hunter_wilds"] = "monster_hunter_wilds"
    status: RecordStatus = "review"
    verified_date: date | None = None
    patch_version: Text | None = None
    patch_sensitive: bool = False
    variant: Text = "normal"
    sources: tuple[SourceRef, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    tags: tuple[Text, ...] = ()
    review_reasons: tuple[Text, ...] = ()
    notes: tuple[Text, ...] = ()


@dataclass(frozen=True, kw_only=True)
class MonsterRecord(HunterRecord):
    record_type: Literal["monster"] = "monster"
    weakness_primary: Text | None = None
    weakness_secondary: tuple[Text, ...] = ()
    targets: dict[TargetRole, tuple[Text, ...]] = field(default_factory=dict)
    control_prep: tuple[Text, ...] = ()
    status_prep: tuple[Text, ...] = ()
    fight_plan: tuple[Text, ...] = ()
    capture_rule: Text | None = None


@dataclass(frozen=True, kw_only=True)
class EncounterPhase(_Strict):
    name: Text
    mechanics: tuple[EvidenceText, ...] = ()
    transition: EvidenceText | None = None


@dataclass(frozen=True, kw_only=True)
class SpecialEncounterRecord(HunterRecord):
    record_type: Literal["special_encounter"] = "special_encounter"
    weakness_primary: Text | None = None
    targets: dict[TargetRole, tuple[Text, ...]] = field(default_factory=dict)
    mechanics: tuple[EvidenceText, ...] = ()
    capture_rule: Text | None = None
    phases: tuple[EncounterPhase, ...] = ()
    timeline_complete: bool = False


@dataclass(frozen=True, kw_only=True)
class WeaponTypeRecord(HunterRecord):
    weapon_type: WeaponKind
    record_type: Literal["weapon_type"] = "weapon_type"
    controls: dict[Text, dict[Text, Text]] = field(default_factory=dict)
    rules: tuple[Text, ...] = ()
    core_loop: tuple[Text, ...] = ()
    failure_modes: tuple[Text, ...] = ()
    exact_weapon_required: bool = True


@dataclass(frozen=True, kw_only=True)
class Melody(_Strict):
    name: Text
    note_sequence: tuple[Text, ...] = ()
    effect_ids: tuple[SourceId, ...] = ()
    source_ids: tuple[SourceId, ...] = ()


@dataclass(frozen=True, kw_only=True)
class HornDetails(_Strict):
    notes: tuple[Text, ...] = ()
    melodies: tuple[Melody, ...] = ()
    echo_bubble: EvidenceText | None = None
    special_performance: EvidenceText | None = None
    source_ids: tuple[SourceId, ...] = ()
    complete: bool = False


@dataclass(frozen=True, kw_only=True)
class AmmoEntry(_Strict):
    ammo: SourceId
    level: PositiveInt | None = None
    support: Literal["supported", "unsupported", "unknown"] = "unknown"
    rapid_fire: bool | None = None
    reload: Text | None = None
    recoil: Text | None = None
    source_ids: tuple[SourceId, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ExactWeaponRecord(HunterRecord):
    weapon_type: WeaponKind
    upgrade_name: Text
    record_type: Literal["exact_weapon"] = "exact_weapon"
    tree_id: RecordId | None = None
    parent_weapon_id: RecordId | None = None
    rarity: PositiveInt | None = None
    horn: HornDetails | None = None
    ammo_table: tuple[AmmoEntry, ...] = ()


@dataclass(frozen=True, kw_only=True)
class HuntingHornTreeRecord(HunterRecord):
    record_type: Literal["hunting_horn_tree"] = "hunting_horn_tree"
    exact_weapon_ids: tuple[RecordId, ...] = ()
    overview: tuple[EvidenceText, ...] = ()


@dataclass(frozen=True, kw_only=True)
class GuideRecord(HunterRecord):
    record_type: Literal["guide"] = "guide"
    topic: Text | None = None
    sections: dict[Text, tuple[Text, ...]] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class FarmStep(_Strict):
    location: Text
    method: EvidenceText
    conditions: tuple[Text, ...] = ()


@dataclass(frozen=True, kw_only=True)
class FarmRouteRecord(HunterRecord):
    record_type: Literal["farm_route"] = "farm_route"
    target_item_ids: tuple[RecordId, ...] = ()
    steps: tuple[FarmStep, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ItemReferenceRecord(HunterRecord):
    record_type: Literal["item_reference"] = "item_reference"
    uses: tuple[EvidenceText, ...] = ()
    acquisition: tuple[EvidenceText, ...] = ()


@dataclass(frozen=True, kw_only=True)
class SkillLevel(_Strict):
    level: PositiveInt
    effect: EvidenceText


@dataclass(frozen=True, kw_only=True)
class SkillReferenceRecord(HunterRecord):
    record_type: Literal["skill_reference"] = "skill_reference"
    levels: tuple[SkillLevel, ...] = ()
    restrictions: tuple[EvidenceText, ...] = ()


Record = Annotated[
    MonsterRecord
    | SpecialEncounterRecord
    | WeaponTypeRecord
    | ExactWeaponRecord
    | HuntingHornTreeRecord
    | GuideRecord
    | FarmRouteRecord
    | ItemReferenceRecord
    | SkillReferenceRecord,
    Field(discriminator="record_type"),
]
_ADAPTER: TypeAdapter[Record] = TypeAdapter(Record)


class HunterDataError(ValueError):
    """Malformed or mismatched domain data; message deliberately excludes payloads."""


def parse_record(payload: dict[str, Any]) -> Record:
    """Validate JSON primitives, including real ISO dates and strict booleans."""
    try:
        return _ADAPTER.validate_json(json.dumps(payload, allow_nan=False), strict=True)
    except (ValidationError, TypeError, ValueError):
        raise HunterDataError(
            "Invalid Hunter payload; inspect it through operator tooling."
        ) from None


def record_payload(record: Record) -> dict[str, Any]:
    """Return validated JSON-ready data; constructing a dataclass is not validation."""
    try:
        payload = _ADAPTER.dump_python(record, mode="json", warnings=False)
        validated = parse_record(payload)
        return cast(dict[str, Any], _ADAPTER.dump_python(validated, mode="json"))
    except (TypeError, ValueError):
        raise HunterDataError("Invalid Hunter record; no data was written.") from None

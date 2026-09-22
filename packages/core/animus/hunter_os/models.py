"""Typed records for the Hunter OS knowledge domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

WILDS_GAME_ID = "monster_hunter_wilds"


class RecordStatus(str, Enum):
    """Verification state carried by every canonical Hunter OS record."""

    VERIFIED = "verified"
    PATCH_SENSITIVE = "patch-sensitive"
    WEAPON_SPECIFIC = "weapon-specific"
    REVIEW = "review"


class AuditSeverity(str, Enum):
    """Severity returned by Hunter OS validation."""

    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True, kw_only=True)
class SourceRef:
    """Human-readable provenance for a canonical fact set."""

    document: str
    section: str = ""
    note: str = ""


@dataclass(frozen=True, kw_only=True)
class HunterRecord:
    """Base metadata shared by all Hunter OS records."""

    id: str
    name: str
    record_type: str
    game: str = WILDS_GAME_ID
    status: RecordStatus = RecordStatus.REVIEW
    verified_date: str = ""
    sources: tuple[SourceRef, ...] = ()
    tags: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class MonsterRecord(HunterRecord):
    """Normal/tempered-style monster quick-reference data."""

    weakness_primary: str = ""
    weakness_secondary: tuple[str, ...] = ()
    targets: dict[str, tuple[str, ...]] = field(default_factory=dict)
    control_prep: tuple[str, ...] = ()
    status_prep: tuple[str, ...] = ()
    fight_plan: tuple[str, ...] = ()
    capture_rule: str = ""
    variant: str = "normal"


@dataclass(frozen=True, kw_only=True)
class WeaponTypeRecord(HunterRecord):
    """Weapon-type controls and invariant system rules."""

    controls: dict[str, dict[str, str]] = field(default_factory=dict)
    rules: tuple[str, ...] = ()
    core_loop: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class GuideRecord(HunterRecord):
    """Cross-cutting Hunter OS guide/build record."""

    sections: dict[str, tuple[str, ...]] = field(default_factory=dict)
    related_records: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class SpecialEncounterRecord(HunterRecord):
    """Mechanic-driven encounter that should not be reduced to a normal card."""

    weakness_primary: str = ""
    targets: dict[str, tuple[str, ...]] = field(default_factory=dict)
    mechanics: tuple[str, ...] = ()
    capture_rule: str = ""
    phase_notes: tuple[str, ...] = ()
    timeline_complete: bool = False


@dataclass(frozen=True, kw_only=True)
class AuditFinding:
    """One machine-readable audit result."""

    severity: AuditSeverity
    code: str
    message: str


@dataclass(frozen=True, kw_only=True)
class AuditReport:
    """Audit result for a Hunter OS record."""

    record_id: str
    findings: tuple[AuditFinding, ...]

    @property
    def blocked(self) -> bool:
        return any(f.severity == AuditSeverity.BLOCK for f in self.findings)

    @property
    def warnings(self) -> tuple[AuditFinding, ...]:
        return tuple(f for f in self.findings if f.severity == AuditSeverity.WARN)

    @property
    def publishable(self) -> bool:
        return not self.blocked


def tupleize(value: Any) -> tuple[str, ...]:
    """Normalize a YAML scalar/list into a tuple of strings."""

    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)

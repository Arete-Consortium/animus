"""Deterministic audits for Hunter OS canonical records."""

from __future__ import annotations

from .models import (
    AuditFinding,
    AuditReport,
    AuditSeverity,
    GuideRecord,
    HunterRecord,
    MonsterRecord,
    RecordStatus,
    SpecialEncounterRecord,
    WILDS_GAME_ID,
    WeaponTypeRecord,
)


def _finding(severity: AuditSeverity, code: str, message: str) -> AuditFinding:
    return AuditFinding(severity=severity, code=code, message=message)


def audit_record(record: HunterRecord) -> AuditReport:
    """Audit one record without consulting Animus memory or an LLM."""

    findings: list[AuditFinding] = []

    if record.game != WILDS_GAME_ID:
        findings.append(
            _finding(
                AuditSeverity.BLOCK,
                "scope.game",
                f"Record game must be {WILDS_GAME_ID!r}.",
            )
        )

    if not record.sources:
        findings.append(
            _finding(AuditSeverity.BLOCK, "provenance.sources", "No source provenance.")
        )

    if not record.verified_date:
        findings.append(
            _finding(AuditSeverity.BLOCK, "provenance.date", "No verified date.")
        )

    if record.status == RecordStatus.REVIEW:
        findings.append(
            _finding(
                AuditSeverity.BLOCK,
                "status.review",
                "Record is explicitly marked for review.",
            )
        )

    if isinstance(record, MonsterRecord):
        _audit_monster(record, findings)
    elif isinstance(record, WeaponTypeRecord):
        _audit_weapon(record, findings)
    elif isinstance(record, GuideRecord):
        _audit_guide(record, findings)
    elif isinstance(record, SpecialEncounterRecord):
        _audit_special(record, findings)

    if not findings:
        findings.append(_finding(AuditSeverity.PASS, "record.valid", "Record passed audit."))

    return AuditReport(record_id=record.id, findings=tuple(findings))


def _audit_monster(record: MonsterRecord, findings: list[AuditFinding]) -> None:
    if not record.weakness_primary:
        findings.append(
            _finding(AuditSeverity.BLOCK, "monster.weakness", "Primary weakness missing.")
        )
    if not any(record.targets.values()):
        findings.append(_finding(AuditSeverity.BLOCK, "monster.targets", "Targets missing."))
    if not record.fight_plan:
        findings.append(
            _finding(AuditSeverity.BLOCK, "monster.fight_plan", "Fight plan missing.")
        )


def _audit_weapon(record: WeaponTypeRecord, findings: list[AuditFinding]) -> None:
    if not record.controls:
        findings.append(_finding(AuditSeverity.BLOCK, "weapon.controls", "Controls missing."))
    if record.id == "hunting_horn":
        required = {"note_1", "note_2", "note_3", "perform", "encore", "echo_bubble", "reverb"}
        missing = sorted(required.difference(record.controls))
        if missing:
            findings.append(
                _finding(
                    AuditSeverity.BLOCK,
                    "hh.controls",
                    f"Missing Hunting Horn controls: {', '.join(missing)}",
                )
            )
        if not any("horn-specific" in rule.casefold() for rule in record.rules):
            findings.append(
                _finding(
                    AuditSeverity.BLOCK,
                    "hh.song_specificity",
                    "Hunting Horn must explicitly preserve horn-specific melody rules.",
                )
            )


def _audit_guide(record: GuideRecord, findings: list[AuditFinding]) -> None:
    if not record.sections:
        findings.append(_finding(AuditSeverity.BLOCK, "guide.sections", "Guide has no sections."))


def _audit_special(
    record: SpecialEncounterRecord,
    findings: list[AuditFinding],
) -> None:
    if not record.mechanics:
        findings.append(
            _finding(AuditSeverity.BLOCK, "special.mechanics", "Special mechanics missing.")
        )
    if not record.capture_rule:
        findings.append(
            _finding(AuditSeverity.BLOCK, "special.capture", "Capture rule missing.")
        )
    if not record.timeline_complete:
        findings.append(
            _finding(
                AuditSeverity.WARN,
                "special.timeline",
                "Quick-reference data is verified, but a complete mechanic timeline is not yet modeled.",
            )
        )

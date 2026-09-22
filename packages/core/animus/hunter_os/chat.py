"""Grounded, share-safe chat context for Monster Hunter Wilds."""

from __future__ import annotations

from dataclasses import dataclass

from .audit import audit_record
from .models import (
    GuideRecord,
    HunterRecord,
    MonsterRecord,
    SpecialEncounterRecord,
    WeaponTypeRecord,
)
from .repository import HunterOSRepository

HUNTER_CHAT_SYSTEM = """You are answering a Monster Hunter Wilds question in a shared Discord channel.
Use ONLY the supplied Hunter OS records for Monster Hunter factual claims.
Do not use or request general Animus memory, personal memory, or unrelated project context.
Do not silently fill missing exact facts from model knowledge.
If the records do not verify an exact fact, say that Hunter OS does not currently verify it.
Keep the answer practical and concise for players who may be mid-hunt.
"""


@dataclass(frozen=True)
class HunterChatContext:
    """Canonical record bundle supplied to the cognitive layer."""

    question: str
    records: tuple[HunterRecord, ...]
    text: str

    @property
    def found(self) -> bool:
        return bool(self.records)


class HunterOSChatService:
    """Retrieve Hunter OS facts without touching the general Animus memory layer."""

    def __init__(self, repository: HunterOSRepository | None = None) -> None:
        self.repository = repository or HunterOSRepository()

    def context_for(self, question: str, limit: int = 6) -> HunterChatContext:
        candidates = self.repository.search(question, limit=max(limit * 2, limit))
        records: list[HunterRecord] = []

        for record in candidates:
            report = audit_record(record)
            if report.blocked:
                continue
            records.append(record)
            if len(records) >= limit:
                break

        text = self._format_context(tuple(records))
        return HunterChatContext(question=question, records=tuple(records), text=text)

    @staticmethod
    def _format_context(records: tuple[HunterRecord, ...]) -> str:
        if not records:
            return "HUNTER_OS_CONTEXT: no verified matching record."

        sections = [
            "HUNTER_OS_CONTEXT",
            "Scope: Monster Hunter Wilds only.",
            "Privacy boundary: canonical Hunter OS records only; no general Animus memory.",
        ]
        for record in records:
            sections.append(_format_record(record))
        return "\n\n".join(sections)

    def prompt_for(self, question: str, limit: int = 6) -> tuple[str, str]:
        """Return (user_prompt, system_prompt) for the cognitive layer."""

        context = self.context_for(question, limit=limit)
        user_prompt = f"{context.text}\n\nQUESTION:\n{question}"
        return user_prompt, HUNTER_CHAT_SYSTEM


def _format_record(record: HunterRecord) -> str:
    header = (
        f"RECORD {record.id}\n"
        f"Name: {record.name}\n"
        f"Type: {record.record_type}\n"
        f"Status: {record.status.value}\n"
        f"Verified: {record.verified_date}"
    )
    source_text = "; ".join(
        f"{source.document}{' / ' + source.section if source.section else ''}"
        for source in record.sources
    )

    lines = [header, f"Sources: {source_text}"]

    if isinstance(record, MonsterRecord):
        lines.extend(
            [
                f"Primary weakness: {record.weakness_primary}",
                f"Secondary weakness: {', '.join(record.weakness_secondary) or 'none recorded'}",
                f"Targets: {_format_mapping(record.targets)}",
                f"Control/prep: {', '.join(record.control_prep) or 'none recorded'}",
                f"Status prep: {', '.join(record.status_prep) or 'none recorded'}",
                f"Fight plan: {'; '.join(record.fight_plan)}",
            ]
        )
    elif isinstance(record, WeaponTypeRecord):
        lines.extend(
            [
                f"Controls: {_format_controls(record.controls)}",
                f"Rules: {'; '.join(record.rules)}",
                f"Core loop: {'; '.join(record.core_loop)}",
                f"Failure modes: {'; '.join(record.failure_modes)}",
            ]
        )
    elif isinstance(record, GuideRecord):
        lines.append(f"Sections: {_format_mapping(record.sections)}")
    elif isinstance(record, SpecialEncounterRecord):
        lines.extend(
            [
                f"Primary weakness: {record.weakness_primary}",
                f"Targets: {_format_mapping(record.targets)}",
                f"Mechanics: {', '.join(record.mechanics)}",
                f"Capture: {record.capture_rule}",
                f"Timeline complete: {record.timeline_complete}",
            ]
        )

    return "\n".join(lines)


def _format_mapping(mapping: dict[str, tuple[str, ...]]) -> str:
    return " | ".join(
        f"{key}={', '.join(values)}" for key, values in mapping.items()
    )


def _format_controls(controls: dict[str, dict[str, str]]) -> str:
    chunks = []
    for action, bindings in controls.items():
        platform_text = ", ".join(f"{platform}:{value}" for platform, value in bindings.items())
        chunks.append(f"{action} [{platform_text}]")
    return " | ".join(chunks)

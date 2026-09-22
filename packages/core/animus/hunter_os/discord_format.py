"""Discord companion-text formatting for Hunter OS cards."""

from __future__ import annotations

import re

from .models import (
    GuideRecord,
    HunterRecord,
    MonsterRecord,
    SpecialEncounterRecord,
    WeaponTypeRecord,
)

DISCORD_MESSAGE_LIMIT = 2000


class DiscordFormatError(ValueError):
    """Raised when a record cannot be represented safely inside Discord limits."""


def format_record_message(record: HunterRecord) -> str:
    """Create searchable companion text for a Hunter OS card."""

    lines = [
        f"**{record.name.upper()}**",
        f"`{record.record_type}` • **{record.status.value.upper()}** • verified {record.verified_date}",
        "",
    ]

    if isinstance(record, MonsterRecord):
        weakness = record.weakness_primary
        if record.weakness_secondary:
            weakness += f" / {', '.join(record.weakness_secondary)}"
        lines.append(f"**Weakness:** {weakness}")
        if record.targets:
            lines.append(f"**Targets:** {_mapping(record.targets)}")
        prep = (*record.control_prep, *record.status_prep)
        if prep:
            lines.append(f"**Prep:** {', '.join(prep)}")
        if record.fight_plan:
            lines.append(f"**Fight:** {' '.join(record.fight_plan)}")

    elif isinstance(record, WeaponTypeRecord):
        if record.core_loop:
            lines.append(f"**Core loop:** {' '.join(record.core_loop)}")
        if record.rules:
            lines.append(f"**Rules:** {' '.join(record.rules)}")
        lines.append("**Controls:** see attached field card.")

    elif isinstance(record, GuideRecord):
        for section, values in record.sections.items():
            lines.append(f"**{section.replace('_', ' ').title()}:** {'; '.join(values)}")

    elif isinstance(record, SpecialEncounterRecord):
        lines.append(f"**Weakness:** {record.weakness_primary}")
        lines.append(f"**Targets:** {_mapping(record.targets)}")
        lines.append(f"**Mechanics:** {', '.join(record.mechanics)}")
        lines.append(f"**Capture:** {record.capture_rule}")
        if not record.timeline_complete:
            lines.append("⚠️ Complete mechanic timeline not yet modeled.")

    lines.extend(
        [
            "",
            _tags(record),
            f"Hunter OS • Wilds only • record `{record.id}`",
        ]
    )

    message = "\n".join(line for line in lines if line is not None)
    if len(message) > DISCORD_MESSAGE_LIMIT:
        raise DiscordFormatError(
            f"Discord companion text for {record.id!r} exceeds {DISCORD_MESSAGE_LIMIT} characters."
        )
    return message


def _mapping(mapping: dict[str, tuple[str, ...]]) -> str:
    return " | ".join(
        f"{key.replace('_', ' ').title()}: {', '.join(values)}"
        for key, values in mapping.items()
        if values
    )


def _tags(record: HunterRecord) -> str:
    raw = (record.record_type, *record.tags)
    tags = []
    seen = set()
    for item in raw:
        tag = re.sub(r"[^a-z0-9]+", "-", item.casefold()).strip("-")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(f"#{tag}")
    return " ".join(tags[:10])

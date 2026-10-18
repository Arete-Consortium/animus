"""OgmaOutput dataclass — the external-read contract per ``skills/ogma/SKILL.md``.

Owns the markdown round-trip: ``OgmaOutput`` → ``to_markdown()`` (the SKILL.md
External template, literally) → ``from_markdown()`` parses it back. Round-trip
is enforced by tests; downstream consumers (v1.1 supported-memory indexer, v3
MCP tool) read prior outputs via ``from_markdown``.

The "missing field fails the skill" rule from SKILL.md is enforced in
``__post_init__`` — every required field MUST be non-empty at construction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

DEFAULT_OUTPUT_DIR = Path("~/projects/notes/ogma").expanduser()
SLUG_MAX_CHARS = 60
AnimusGapStatus = Literal["NONE", "PARTIAL", "FULL"]
RoiEffort = Literal["trivial", "moderate", "substantial"]


class OgmaParseError(ValueError):
    """Raised when ``from_markdown`` cannot recover the contract."""


@dataclass(frozen=True)
class OgmaOutput:
    """One Ogma external-read synthesis. Maps 1:1 to SKILL.md §External."""

    title: str
    source_id: str
    item_id: str
    date: date
    concept: str
    novelty: str
    animus_gap: AnimusGapStatus
    animus_gap_notes: str
    weaknesses: str
    proposal: str
    roi_value: str
    roi_effort: RoiEffort
    roi_priority: str
    risks: str
    confidence: float
    confidence_justification: str
    sources_cited: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        required = {
            "title": self.title,
            "source_id": self.source_id,
            "item_id": self.item_id,
            "concept": self.concept,
            "novelty": self.novelty,
            "animus_gap_notes": self.animus_gap_notes,
            "weaknesses": self.weaknesses,
            "proposal": self.proposal,
            "roi_value": self.roi_value,
            "roi_priority": self.roi_priority,
            "risks": self.risks,
            "confidence_justification": self.confidence_justification,
        }
        for name, value in required.items():
            if not (value and value.strip()):
                raise ValueError(f"OgmaOutput: required field {name} is empty")
        if self.animus_gap not in ("NONE", "PARTIAL", "FULL"):
            raise ValueError(
                f"OgmaOutput: animus_gap must be NONE|PARTIAL|FULL, got {self.animus_gap!r}"
            )
        if self.roi_effort not in ("trivial", "moderate", "substantial"):
            raise ValueError(
                f"OgmaOutput: roi_effort must be trivial|moderate|substantial, "
                f"got {self.roi_effort!r}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"OgmaOutput: confidence must be in [0.0, 1.0], got {self.confidence}")
        if not self.sources_cited:
            raise ValueError("OgmaOutput: sources_cited must contain at least one entry")

    @property
    def slug(self) -> str:
        return _make_slug(self.title, self.item_id)

    def to_markdown(self) -> str:
        cited = "\n".join(f"- {c}" for c in self.sources_cited)
        return (
            f"# {self.title}\n"
            f"\n"
            f"**Source:** {self.item_id}  •  **Date:** {self.date.isoformat()}\n"
            f"**Cited from:** {self.source_id}\n"
            f"\n"
            f"## Concept\n{self.concept}\n"
            f"\n"
            f"## Novelty\n{self.novelty}\n"
            f"\n"
            f"## Animus gap\n"
            f"**Status:** {self.animus_gap}\n"
            f"{self.animus_gap_notes}\n"
            f"\n"
            f"## Weaknesses in the source\n{self.weaknesses}\n"
            f"\n"
            f"## Proposal — how we build it better\n{self.proposal}\n"
            f"\n"
            f"## ROI\n"
            f"**Value:** {self.roi_value}\n"
            f"**Effort:** {self.roi_effort}\n"
            f"**Priority:** {self.roi_priority}\n"
            f"\n"
            f"## Risks\n{self.risks}\n"
            f"\n"
            f"## Confidence\n"
            f"{self.confidence:.2f} — {self.confidence_justification}\n"
            f"\n"
            f"## Sources cited\n{cited}\n"
        )

    def write(self, output_dir: Path | None = None) -> Path:
        target_dir = output_dir or DEFAULT_OUTPUT_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{self.date.isoformat()}-{self.slug}.md"
        path.write_text(self.to_markdown(), encoding="utf-8")
        return path

    @classmethod
    def from_markdown(cls, text: str, *, source_id: str, item_id: str) -> OgmaOutput:
        # LLMs often emit preamble ("Here is the synthesis:", "<think>…</think>",
        # "Based on the source…") before the requested format. Anchor parsing
        # at the first "# " line we see and discard everything before it.
        text = _strip_preamble(text)
        title = _extract_h1(text)
        if not title:
            raise OgmaParseError("missing # <title> heading")
        date_str = _extract_header_field(text, "Date")
        # Forgiving date parse: accept ISO dates, fall back to today for unknown/N/A/placeholders
        parsed_date = date.today()
        if date_str and date_str not in ("N/A", "Unknown", "YYYY-MM-DD", ""):
            try:
                parsed_date = date.fromisoformat(date_str)
            except ValueError:
                pass  # keep today() as fallback
        sections = _extract_sections(text)
        gap_block = _require_section(sections, "Animus gap")
        gap_status_match = re.search(r"\*\*Status:\*\*\s*(NONE|PARTIAL|FULL)", gap_block)
        if not gap_status_match:
            raise OgmaParseError("Animus gap: missing **Status:** NONE|PARTIAL|FULL")
        gap_status = gap_status_match.group(1)
        gap_notes = re.sub(
            r"\*\*Status:\*\*\s*(NONE|PARTIAL|FULL)\s*\n?", "", gap_block, count=1
        ).strip()
        roi_block = _require_section(sections, "ROI")
        roi_value = _extract_bold_field(roi_block, "Value")
        roi_effort = _extract_bold_field(roi_block, "Effort")
        roi_priority = _extract_bold_field(roi_block, "Priority")
        # Normalize roi_effort: case-insensitive, strip trailing prose after keyword
        _raw_effort = roi_effort.lower()
        for keyword in ("trivial", "moderate", "substantial"):
            if _raw_effort.startswith(keyword):
                roi_effort = keyword
                break
        if roi_effort not in ("trivial", "moderate", "substantial"):
            raise OgmaParseError(
                f"ROI Effort must be trivial|moderate|substantial, got {roi_effort!r}"
            )
        conf_block = _require_section(sections, "Confidence")
        conf_match = re.match(r"\s*([0-9]*\.?[0-9]+)\s*[—-]\s*(.+)", conf_block, re.DOTALL)
        if not conf_match:
            raise OgmaParseError("Confidence: expected '<float> — <justification>'")
        confidence = float(conf_match.group(1))
        cited_block = _require_section(sections, "Sources cited")
        cited = [line[2:].strip() for line in cited_block.splitlines() if line.startswith("- ")]
        if not cited:
            raise OgmaParseError("Sources cited: must list at least one '- ' entry")
        return cls(
            title=title,
            source_id=source_id,
            item_id=item_id,
            date=parsed_date,
            concept=_require_section(sections, "Concept"),
            novelty=_require_section(sections, "Novelty"),
            animus_gap=gap_status,  # type: ignore[arg-type]
            animus_gap_notes=gap_notes or "(no notes)",
            weaknesses=_require_section(sections, "Weaknesses in the source"),
            proposal=_require_section(sections, "Proposal — how we build it better"),
            roi_value=roi_value,
            roi_effort=roi_effort,  # type: ignore[arg-type]
            roi_priority=roi_priority,
            risks=_require_section(sections, "Risks"),
            confidence=confidence,
            confidence_justification=conf_match.group(2).strip(),
            sources_cited=cited,
        )


def _make_slug(title: str, item_id: str) -> str:
    """Lowercase, hyphen-join, strip non-alnum, ASCII-only, truncate ≤60.

    Empty/whitespace title falls back to ``item_id``. Non-ASCII titles get
    stripped via the stdlib-only ``encode('ascii', 'ignore')`` path so we
    don't add an ``unidecode`` dep.
    """
    base = (title or "").strip()
    if not base:
        base = item_id
    base = base.encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if not base:
        base = item_id.lower()
    if len(base) > SLUG_MAX_CHARS:
        base = base[:SLUG_MAX_CHARS].rstrip("-")
    return base or "ogma-output"


def _extract_h1(text: str) -> str:
    m = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _strip_preamble(text: str) -> str:
    """Trim everything before the first ``# <title>`` line.

    Robust to the common LLM failure pattern of emitting a paragraph of
    prose ("Here is the synthesis:", "Based on the source…") before the
    requested markdown. If no ``# `` line exists, returns the original text
    so the caller's ``OgmaParseError("missing # <title> heading")`` still
    fires with the same message.
    """
    m = re.search(r"^#\s+\S", text, re.MULTILINE)
    return text[m.start() :] if m else text


def _extract_header_field(text: str, name: str) -> str:
    m = re.search(rf"\*\*{re.escape(name)}:\*\*\s*([^\n•]+)", text)
    return m.group(1).strip() if m else ""


def _extract_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE))
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[body_start:body_end].strip()
    return sections


def _require_section(sections: dict[str, str], name: str) -> str:
    if name not in sections or not sections[name].strip():
        raise OgmaParseError(f"missing section: {name}")
    return sections[name].strip()


def _extract_bold_field(block: str, name: str) -> str:
    m = re.search(rf"\*\*{re.escape(name)}:\*\*\s*([^\n]+)", block)
    if not m:
        raise OgmaParseError(f"ROI block missing **{name}:**")
    return m.group(1).strip()

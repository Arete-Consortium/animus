"""Deterministic mobile card renderer for Hunter OS.

The renderer uses programmatic text layout so Discord cards remain crisp and
auditable. It deliberately raises on overflow rather than shrinking text below
the mobile readability floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import (
    GuideRecord,
    HunterRecord,
    MonsterRecord,
    SpecialEncounterRecord,
    WeaponTypeRecord,
)

CARD_WIDTH = 1440
CARD_HEIGHT = 2160

_BG = "#06110d"
_PANEL = "#071712"
_HERO = "#0d201c"
_GOLD = "#e1b950"
_WHITE = "#f4f4ef"
_MUTED = "#c3cbc5"
_GREEN = "#77d89a"
_RED = "#ed746f"
_BLUE = "#78b8e8"


class CardRendererUnavailable(RuntimeError):
    """Raised when Pillow is not installed."""


class CardOverflowError(ValueError):
    """Raised when content cannot fit without violating readability rules."""


@dataclass(frozen=True)
class CardPanel:
    """One visual information panel."""

    title: str
    lines: tuple[str, ...]
    accent: str = _GOLD


class HunterCardRenderer:
    """Render canonical Hunter OS records as 2:3 portrait PNG cards."""

    def __init__(self, width: int = CARD_WIDTH, height: int = CARD_HEIGHT) -> None:
        self.width = width
        self.height = height
        self.scale = width / CARD_WIDTH

    def render(self, record: HunterRecord, output_path: Path | str) -> Path:
        Image, ImageDraw, ImageFont = _pillow()

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        image = Image.new("RGB", (self.width, self.height), _BG)
        draw = ImageDraw.Draw(image)
        fonts = _fonts(ImageFont, self.scale)

        self._draw_frame(draw)
        self._draw_header(draw, record, fonts)
        panels = _record_panels(record)
        self._draw_panels(draw, panels, fonts)
        self._draw_footer(draw, record, fonts)

        image.save(path, format="PNG", optimize=True)
        return path

    def _draw_frame(self, draw: Any) -> None:
        border = int(10 * self.scale)
        inset = int(11 * self.scale)
        draw.rectangle(
            (inset, inset, self.width - inset, self.height - inset),
            outline=_GOLD,
            width=border,
        )

    def _draw_header(self, draw: Any, record: HunterRecord, fonts: dict[str, Any]) -> None:
        x = int(42 * self.scale)
        y = int(44 * self.scale)
        right = self.width - x
        hero_bottom = int(620 * self.scale)

        draw.rectangle((x, y, right, hero_bottom), fill=_HERO, outline=_GOLD, width=int(4 * self.scale))

        eyebrow = _eyebrow(record)
        draw.text((x + int(28 * self.scale), y + int(26 * self.scale)), eyebrow, font=fonts["eyebrow"], fill=_GOLD)

        title_y = y + int(84 * self.scale)
        title = record.name.upper()
        title_font = _fit_font(
            draw,
            title,
            fonts["title_path"],
            int(88 * self.scale),
            int(60 * self.scale),
            right - x - int(56 * self.scale),
        )
        draw.text((x + int(28 * self.scale), title_y), title, font=title_font, fill=_WHITE)

        status = record.status.value.upper()
        subtitle = f"MONSTER HUNTER WILDS  •  {status} FIELD DATA"
        draw.text(
            (x + int(28 * self.scale), title_y + int(112 * self.scale)),
            subtitle,
            font=fonts["subhead"],
            fill=_MUTED,
        )

        # Abstract hero silhouette preserves a game-card feel without embedding
        # copyrighted game art or essential information in imagery.
        cx = self.width // 2
        top = y + int(220 * self.scale)
        points = [
            (x + int(20 * self.scale), hero_bottom),
            (x + int(85 * self.scale), top + int(90 * self.scale)),
            (x + int(165 * self.scale), hero_bottom),
            (cx - int(220 * self.scale), hero_bottom),
            (cx - int(65 * self.scale), top),
            (cx + int(60 * self.scale), hero_bottom),
            (right - int(70 * self.scale), hero_bottom),
            (right - int(5 * self.scale), top + int(70 * self.scale)),
            (right, hero_bottom),
        ]
        draw.polygon(points, fill="#0b1917")

        motto = _motto(record)
        draw.text(
            (x + int(34 * self.scale), hero_bottom - int(88 * self.scale)),
            motto,
            font=fonts["motto"],
            fill="#f0dca0",
        )

    def _draw_panels(
        self,
        draw: Any,
        panels: tuple[CardPanel, ...],
        fonts: dict[str, Any],
    ) -> None:
        margin = int(40 * self.scale)
        gutter = int(24 * self.scale)
        top = int(660 * self.scale)
        footer_top = int(1875 * self.scale)
        col_w = (self.width - margin * 2 - gutter) // 2
        row_h = int(335 * self.scale)

        short = panels[:4]
        for index, panel in enumerate(short):
            row = index // 2
            col = index % 2
            x1 = margin + col * (col_w + gutter)
            y1 = top + row * (row_h + gutter)
            self._draw_panel(
                draw,
                panel,
                (x1, y1, x1 + col_w, y1 + row_h),
                fonts,
            )

        remaining = panels[4:]
        y = top + 2 * (row_h + gutter)
        for panel in remaining:
            available = footer_top - y
            if available < int(220 * self.scale):
                raise CardOverflowError(
                    f"Record has too much card content: {panel.title}. Split into multiple cards."
                )
            height = min(int(330 * self.scale), available)
            self._draw_panel(
                draw,
                panel,
                (margin, y, self.width - margin, y + height),
                fonts,
            )
            y += height + gutter

    def _draw_panel(
        self,
        draw: Any,
        panel: CardPanel,
        box: tuple[int, int, int, int],
        fonts: dict[str, Any],
    ) -> None:
        x1, y1, x2, y2 = box
        radius = int(22 * self.scale)
        draw.rounded_rectangle(
            box,
            radius=radius,
            fill=_PANEL,
            outline=panel.accent,
            width=int(4 * self.scale),
        )

        pad = int(22 * self.scale)
        draw.text((x1 + pad, y1 + pad), panel.title.upper(), font=fonts["panel_title"], fill=panel.accent)

        cursor_y = y1 + int(82 * self.scale)
        max_width = x2 - x1 - pad * 2
        bottom = y2 - pad

        for raw_line in panel.lines:
            wrapped = _wrap_text(draw, raw_line, fonts["body"], max_width)
            if not wrapped:
                wrapped = [""]
            for line in wrapped:
                if cursor_y + fonts["body_height"] > bottom:
                    raise CardOverflowError(
                        f"Panel {panel.title!r} overflowed. Split content; do not shrink mobile text."
                    )
                draw.text((x1 + pad, cursor_y), line, font=fonts["body"], fill=_WHITE)
                cursor_y += fonts["body_height"]
            cursor_y += int(8 * self.scale)

    def _draw_footer(self, draw: Any, record: HunterRecord, fonts: dict[str, Any]) -> None:
        x = int(56 * self.scale)
        y = int(1920 * self.scale)
        draw.text((x, y), "HUNTER OS", font=fonts["footer_title"], fill=_GOLD)
        draw.text(
            (x, y + int(76 * self.scale)),
            "PREPARE • HUNT • ADAPT • OVERCOME",
            font=fonts["footer"],
            fill="#e6cf8b",
        )
        draw.text(
            (x, y + int(135 * self.scale)),
            f"WILDS ONLY • {record.status.value.upper()} • {record.verified_date}",
            font=fonts["small"],
            fill=_MUTED,
        )


def _record_panels(record: HunterRecord) -> tuple[CardPanel, ...]:
    if isinstance(record, MonsterRecord):
        weakness = record.weakness_primary
        if record.weakness_secondary:
            weakness += f" primary; {', '.join(record.weakness_secondary)} secondary"
        targets = _mapping_lines(record.targets)
        return (
            CardPanel("Weakness / Target", tuple([weakness, *targets])),
            CardPanel(
                "Control / Prep",
                tuple([*record.control_prep, *record.status_prep]) or ("No generic prep recorded.",),
            ),
            CardPanel("Hunt Flow", record.fight_plan or ("No fight plan recorded.",)),
            CardPanel(
                "Record Status",
                (
                    f"Variant: {record.variant}",
                    f"Status: {record.status.value}",
                    f"Verified: {record.verified_date}",
                ),
                _GREEN,
            ),
            CardPanel(
                "Field Notes",
                tuple(record.notes)
                or (
                    "Weapon-specific targets remain separate from generic targets.",
                    "Variant mechanics are never silently inherited.",
                ),
                _GREEN,
            ),
        )

    if isinstance(record, WeaponTypeRecord):
        controls = []
        for action, bindings in record.controls.items():
            label = action.replace("_", " ").title()
            xbox = bindings.get("xbox", "")
            ps5 = bindings.get("ps5", "")
            pc = bindings.get("pc", "")
            controls.append(f"{label}: Xbox {xbox} | PS5 {ps5} | PC {pc}")
        midpoint = max(1, (len(controls) + 1) // 2)
        return (
            CardPanel("Controls I", tuple(controls[:midpoint]), _BLUE),
            CardPanel("Controls II", tuple(controls[midpoint:]) or ("See Controls I.",), _BLUE),
            CardPanel("Core Loop", record.core_loop or ("No core loop recorded.",)),
            CardPanel("Critical Rules", record.rules or ("No special rules recorded.",), _GREEN),
            CardPanel("Avoid", record.failure_modes or ("No failure modes recorded.",), _RED),
        )

    if isinstance(record, GuideRecord):
        panels = []
        accents = (_GOLD, _BLUE, _GREEN, _GOLD, _BLUE)
        for index, (section, lines) in enumerate(record.sections.items()):
            panels.append(
                CardPanel(section.replace("_", " "), lines, accents[index % len(accents)])
            )
        return tuple(panels)

    if isinstance(record, SpecialEncounterRecord):
        targets = _mapping_lines(record.targets)
        return (
            CardPanel(
                "Weakness / Target",
                tuple([record.weakness_primary, *targets]),
            ),
            CardPanel("Mechanics", record.mechanics or ("No mechanics recorded.",), _RED),
            CardPanel("Capture", (record.capture_rule or "No capture rule recorded.",)),
            CardPanel(
                "Timeline",
                (
                    "Complete" if record.timeline_complete else "Quick reference only — timeline pending.",
                    *record.phase_notes,
                ),
                _GREEN if record.timeline_complete else _RED,
            ),
            CardPanel(
                "Field Notes",
                record.notes or ("Special encounters remain separate from normal monster cards.",),
                _GREEN,
            ),
        )

    raise TypeError(f"Unsupported Hunter OS record type: {type(record).__name__}")


def _mapping_lines(mapping: dict[str, tuple[str, ...]]) -> list[str]:
    return [
        f"{key.replace('_', ' ').title()}: {', '.join(values)}"
        for key, values in mapping.items()
        if values
    ]


def _eyebrow(record: HunterRecord) -> str:
    labels = {
        "monster": "MONSTER HUNT CARD",
        "weapon_type": "WEAPON FIELD CARD",
        "guide": "HUNTER GUIDE CARD",
        "special_encounter": "SPECIAL ENCOUNTER CARD",
    }
    return labels.get(record.record_type, "HUNTER OS CARD")


def _motto(record: HunterRecord) -> str:
    if record.record_type == "monster":
        return "KNOW THE HUNT. HUNT SMARTER."
    if record.record_type == "weapon_type":
        return "KNOW THE TOOL. CONTROL THE FIGHT."
    if record.record_type == "special_encounter":
        return "MECHANICS BEFORE GREED."
    return "PREPARE WITH PURPOSE."


def _pillow() -> tuple[Any, Any, Any]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise CardRendererUnavailable(
            "Hunter OS card rendering requires Pillow. Install animus-core[hunter-os]."
        ) from exc
    return Image, ImageDraw, ImageFont


def _fonts(ImageFont: Any, scale: float) -> dict[str, Any]:
    regular = _font_path(bold=False)
    bold = _font_path(bold=True)

    def font(path: str, size: int) -> Any:
        return ImageFont.truetype(path, max(12, int(size * scale)))

    body = font(regular, 40)
    bbox = body.getbbox("Ag")
    body_height = int((bbox[3] - bbox[1]) * 1.45)
    return {
        "eyebrow": font(bold, 34),
        "title_path": bold,
        "subhead": font(bold, 28),
        "motto": font(bold, 34),
        "panel_title": font(bold, 34),
        "body": body,
        "body_height": body_height,
        "footer_title": font(bold, 50),
        "footer": font(bold, 27),
        "small": font(regular, 24),
    }


def _font_path(*, bold: bool) -> str:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    # Pillow ships/falls back to this commonly resolvable family name.
    return "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"


def _fit_font(
    draw: Any,
    text: str,
    font_path: str,
    start_size: int,
    min_size: int,
    max_width: int,
) -> Any:
    from PIL import ImageFont

    size = start_size
    while size >= min_size:
        font = ImageFont.truetype(font_path, size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
        size -= 2
    raise CardOverflowError(f"Title is too wide for the card at minimum size: {text!r}")


def _wrap_text(draw: Any, text: str, font: Any, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        box = draw.textbbox((0, 0), candidate, font=font)
        if box[2] - box[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines

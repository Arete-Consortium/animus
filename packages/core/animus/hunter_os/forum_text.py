"""Text-first Forum content helpers for Hunter OS."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

DISCORD_SAFE_LIMIT = 1900
_FORUM_DIR = Path(__file__).resolve().parent / "forum"


@dataclass(frozen=True)
class ForumBlock:
    """Stable publish unit for one Hunter OS Forum thread."""

    key: str
    title: str
    content: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def load_forum_blocks(name: str, *, limit: int = DISCORD_SAFE_LIMIT) -> tuple[ForumBlock, ...]:
    """Load one forum markdown document and split it into stable Discord messages."""

    path = _FORUM_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8").strip()
    sections = _parse_sections(text)
    blocks: list[ForumBlock] = []

    for section_key, title, body in sections:
        chunks = _chunk_markdown(body, limit=limit)
        for index, chunk in enumerate(chunks, 1):
            suffix = "" if len(chunks) == 1 else f".part{index}"
            blocks.append(
                ForumBlock(
                    key=f"{section_key}{suffix}",
                    title=title,
                    content=chunk,
                )
            )

    return tuple(blocks)


def build_index_blocks(
    name: str,
    blocks: tuple[ForumBlock, ...],
    *,
    limit: int = DISCORD_SAFE_LIMIT,
) -> tuple[ForumBlock, ...]:
    """Build a searchable text index for the start of a Forum thread."""

    seen: set[str] = set()
    titles: list[str] = []
    for block in blocks:
        base_key = block.key.split(".part", 1)[0]
        if base_key in seen:
            continue
        seen.add(base_key)
        titles.append(block.title)

    heading = f"**HUNTER OS — {name.replace('_', ' ').upper()} INDEX**\n"
    body = heading + "\n".join(f"• {title}" for title in titles)
    chunks = _chunk_markdown(body, limit=limit)

    return tuple(
        ForumBlock(
            key=f"__index__.part{index}",
            title=f"{name.title()} Index",
            content=chunk,
        )
        for index, chunk in enumerate(chunks, 1)
    )


def _parse_sections(text: str) -> list[tuple[str, str, str]]:
    """Split markdown by H2 while preserving the H1 preamble as an intro block."""

    lines = text.splitlines()
    sections: list[tuple[str, str, list[str]]] = []
    current_key = "__intro__"
    current_title = "Start Here"
    current: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current:
                sections.append((current_key, current_title, current))
            current_title = line[3:].strip()
            current_key = _slug(current_title)
            current = [f"**{current_title}**"]
        else:
            current.append(line)

    if current:
        sections.append((current_key, current_title, current))

    return [(key, title, "\n".join(body).strip()) for key, title, body in sections]


def _chunk_markdown(text: str, *, limit: int) -> list[str]:
    """Split text under Discord's message limit without silently dropping content."""

    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in text.splitlines():
        line_parts = _split_long_line(line, limit)
        for part in line_parts:
            extra = len(part) + (1 if current else 0)
            if current and current_len + extra > limit:
                chunks.append("\n".join(current).strip())
                current = [part]
                current_len = len(part)
            else:
                current.append(part)
                current_len += extra

    if current:
        chunks.append("\n".join(current).strip())

    if any(len(chunk) > limit for chunk in chunks):
        raise ValueError("Forum text chunking exceeded Discord safe limit.")

    return chunks


def _split_long_line(line: str, limit: int) -> list[str]:
    if len(line) <= limit:
        return [line]

    words = line.split()
    if not words:
        return [""]

    parts: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= limit:
            current = candidate
        else:
            parts.append(current)
            current = word
    parts.append(current)
    return parts


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "section"

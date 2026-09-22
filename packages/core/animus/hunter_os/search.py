"""Deterministic full-record search for Hunter OS."""

from __future__ import annotations

import re
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from .models import HunterRecord

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "we",
    "what",
    "with",
}


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in _TOKEN_RE.findall(text.casefold())
        if token not in _STOPWORDS
    )


def _flatten(value: Any) -> list[str]:
    """Flatten a record value into deterministic searchable strings."""

    if value is None:
        return []
    if isinstance(value, Enum):
        return [str(value.value)]
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            out.append(str(key))
            out.extend(_flatten(item))
        return out
    if isinstance(value, (tuple, list, set, frozenset)):
        out = []
        for item in value:
            out.extend(_flatten(item))
        return out
    if is_dataclass(value):
        out = []
        for field_info in fields(value):
            out.extend(_flatten(getattr(value, field_info.name)))
        return out
    return [str(value)]


def searchable_text(record: HunterRecord) -> str:
    """Return all non-secret canonical record text used for lookup."""

    return " ".join(_flatten(record)).casefold()


def score_record(record: HunterRecord, query: str) -> int:
    """Score a record for a natural-language Hunter OS query."""

    normalized = " ".join(_tokens(query))
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return 0

    name = record.name.casefold()
    record_id = record.id.casefold().replace("_", " ")
    tags = " ".join(record.tags).casefold()
    blob = searchable_text(record)
    blob_tokens = set(_tokens(blob))

    score = 0
    if normalized and normalized in name:
        score += 30
    if normalized and normalized in record_id:
        score += 25
    if normalized and normalized in tags:
        score += 20
    if normalized and normalized in blob:
        score += 12

    overlap = query_tokens.intersection(blob_tokens)
    score += len(overlap) * 3

    for token in query_tokens:
        if token in _tokens(name):
            score += 8
        if token in _tokens(record_id):
            score += 6
        if token in _tokens(tags):
            score += 4

    return score

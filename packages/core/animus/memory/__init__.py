"""
Animus Memory Layer — package facade.

Preserves the import surface of the previous single-file module so every
existing `from animus.memory import X` call site works unchanged. Internals
split into:

    types     — Memory / MemoryType / MemorySource / SemanticFact /
                Procedure / Message / Conversation
    stores/   — supported stores plus the legacy migration-only Chroma adapter
    fusion    — _rrf_fuse (Reciprocal Rank Fusion)
    layer     — MemoryLayer façade

Phase 1: Structured memory with types, tags, confidence, and export/import.
"""

from __future__ import annotations

from animus.memory.layer import MemoryLayer
from animus.memory.stores import ChromaMemoryStore, LocalMemoryStore, MemoryStore
from animus.memory.tier import TierManager
from animus.memory.types import (
    Conversation,
    Memory,
    MemorySource,
    MemoryTier,
    MemoryType,
    Message,
    Procedure,
    SemanticFact,
)

# Optional: DurableMemoryStore is gated by sqlalchemy availability.
try:
    from animus.memory.stores.durable import DurableMemoryStore
except ImportError:
    DurableMemoryStore = None  # type: ignore[misc,assignment]

__all__ = [
    "ChromaMemoryStore",
    "Conversation",
    "DurableMemoryStore",
    "LocalMemoryStore",
    "Memory",
    "MemoryLayer",
    "MemorySource",
    "MemoryStore",
    "MemoryTier",
    "MemoryType",
    "Message",
    "Procedure",
    "SemanticFact",
    "TierManager",
]

#!/usr/bin/env python3
"""
Animus Memory Sync — Claude Code → Animus ChromaDB

Parses Claude Code memory files and notes repo, deduplicates by content hash,
and pushes structured memories into Animus via direct MemoryLayer API.

Usage:
    python tools/animus_sync.py                  # Full sync
    python tools/animus_sync.py --dry-run        # Preview what would sync
    python tools/animus_sync.py --source cc      # Only Claude Code memory files
    python tools/animus_sync.py --source notes   # Only notes repo
    python tools/animus_sync.py --force           # Re-sync everything (ignore hashes)
    python tools/animus_sync.py --stats           # Show sync statistics
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Ensure animus core is importable when run standalone (e.g., from cron)
_CORE_DIR = os.path.join(os.path.dirname(__file__), "..", "packages", "core")
if os.path.isdir(_CORE_DIR) and _CORE_DIR not in sys.path:
    sys.path.insert(0, os.path.realpath(_CORE_DIR))

from animus.config import AnimusConfig  # noqa: E402 — local package path bootstrap above
from animus.memory import MemoryLayer, MemoryType  # noqa: E402 — local package path bootstrap above

# --- Paths ---

CC_MEMORY_DIR = Path.home() / ".claude/projects/-home-arete-projects/memory"
NOTES_DIR = Path.home() / "projects/notes"
SYNC_STATE_FILE = Path.home() / ".animus/sync_state.json"

# --- Type Mapping ---

# Claude Code memory type → Animus MemoryType
CC_TYPE_MAP: dict[str, MemoryType] = {
    "user": MemoryType.SEMANTIC,
    "feedback": MemoryType.PROCEDURAL,
    "project": MemoryType.SEMANTIC,
    "reference": MemoryType.SEMANTIC,
    "decision": MemoryType.EPISODIC,
    "todo": MemoryType.ACTIVE,
}

# Notes repo path patterns → (MemoryType, base_tags)
NOTES_RULES: list[tuple[str, MemoryType, list[str]]] = [
    ("decisions/", MemoryType.EPISODIC, ["decision"]),
    ("topics/harvest-", MemoryType.PROCEDURAL, ["harvest", "agent-patterns"]),
    ("topics/eve-", MemoryType.SEMANTIC, ["eve-frontier"]),
    ("topics/eve_", MemoryType.SEMANTIC, ["eve-frontier"]),
    ("topics/", MemoryType.PROCEDURAL, ["topic"]),
    ("PHILOSOPHIES.md", MemoryType.SEMANTIC, ["philosophy", "principles"]),
    ("PROFILE.md", MemoryType.SEMANTIC, ["profile", "career"]),
    ("CHECKLISTS.md", MemoryType.PROCEDURAL, ["checklist"]),
]

# Files to skip entirely
SKIP_FILES = {
    "MEMORY.md",  # Index file, not content
    "README.md",  # Meta
    "CLAUDE.md",  # Already loaded by Claude Code
    "TODO.md",  # Ephemeral
    "PROMPTS.md",  # Reference, not memory
    "lessons-learned-2026-01-25.md",  # One-off, already captured in patterns
}

SKIP_PREFIXES = [
    "todo-session-",  # Session-scoped, stale quickly
    "todo-vps-",  # Ephemeral deploy notes
    "sessions/",  # Ephemeral session logs
    "scripts/",  # Automation scripts, not knowledge
]

# Notes topics to include (whitelist — topics/ is too noisy otherwise)
# Only high-signal files that contain durable knowledge
NOTES_TOPICS_INCLUDE = {
    "harvest-agent-architecture.md",
    "harvest-agent-patterns.md",
    "harvest-multi-agent-orchestration.md",
    "harvest-scoring-systems.md",
    "harvest-slash-commands.md",
    "harvest-plugin-architecture.md",
    "eve-frontier-developer-reference.md",
    "eve_frontier_hackathon_intel.md",
    "competitive-intel.md",
    "ci-cd.md",
    "docker.md",
    "git.md",
    "python.md",
    "security.md",
    "todo-monetization.md",
    "animus-memory-gaps.md",
}

# Max content size per memory chunk (chars)
MAX_CHUNK_SIZE = 3000


@dataclass
class SyncMemory:
    """A memory prepared for sync to Animus."""

    content: str
    memory_type: MemoryType
    tags: list[str] = field(default_factory=list)
    source_file: str = ""
    chunk_index: int = 0
    subtype: str | None = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]


@dataclass
class SyncState:
    """Tracks what's been synced to avoid duplicates."""

    last_sync: str = ""
    synced: dict[str, dict] = field(default_factory=dict)  # hash → {animus_id, source, chunk}
    version: int = 1

    @classmethod
    def load(cls, path: Path) -> SyncState:
        if path.exists():
            data = json.loads(path.read_text())
            return cls(
                last_sync=data.get("last_sync", ""),
                synced=data.get("synced", {}),
                version=data.get("version", 1),
            )
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "last_sync": self.last_sync,
                    "synced": self.synced,
                    "version": self.version,
                },
                indent=2,
            )
        )


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-ish frontmatter from markdown. Returns (metadata, body)."""
    if not text.startswith("---"):
        return {}, text

    end = text.find("---", 3)
    if end == -1:
        return {}, text

    frontmatter_text = text[3:end].strip()
    body = text[end + 3 :].strip()

    metadata = {}
    for line in frontmatter_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()

    return metadata, body


def chunk_by_headers(text: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    """Split markdown text by ## headers, respecting max_size."""
    sections = re.split(r"\n(?=## )", text)
    chunks = []

    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= max_size:
            chunks.append(section)
        else:
            # Split long sections by bullet points or paragraphs
            lines = section.split("\n")
            current = []
            current_len = 0
            for line in lines:
                if current_len + len(line) > max_size and current:
                    chunks.append("\n".join(current))
                    current = []
                    current_len = 0
                current.append(line)
                current_len += len(line) + 1
            if current:
                chunks.append("\n".join(current))

    return chunks


def chunk_patterns(text: str) -> list[str]:
    """Split a patterns/gotchas section into individual pattern memories."""
    patterns = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- ") and len(line) > 20:
            patterns.append(line[2:])  # Strip "- " prefix
    return patterns if patterns else [text]


def parse_cc_memory_files() -> list[SyncMemory]:
    """Parse Claude Code memory/*.md files into SyncMemory objects."""
    memories = []

    if not CC_MEMORY_DIR.exists():
        print(f"  [skip] CC memory dir not found: {CC_MEMORY_DIR}")
        return memories

    for md_file in sorted(CC_MEMORY_DIR.glob("*.md")):
        if md_file.name in SKIP_FILES:
            continue
        if any(md_file.name.startswith(p) for p in SKIP_PREFIXES):
            continue

        text = md_file.read_text()
        if not text.strip():
            continue

        metadata, body = parse_frontmatter(text)
        cc_type = metadata.get("type", "reference")
        memory_type = CC_TYPE_MAP.get(cc_type, MemoryType.SEMANTIC)

        tags = ["claude-code", f"cc-type:{cc_type}"]
        name = metadata.get("name", md_file.stem)
        tags.append(f"source:{md_file.name}")

        # Chunk large files
        if len(body) > MAX_CHUNK_SIZE:
            chunks = chunk_by_headers(body)
            for i, chunk in enumerate(chunks):
                memories.append(
                    SyncMemory(
                        content=f"[{name}] {chunk}",
                        memory_type=memory_type,
                        tags=tags.copy(),
                        source_file=str(md_file),
                        chunk_index=i,
                        subtype=cc_type,
                    )
                )
        else:
            memories.append(
                SyncMemory(
                    content=f"[{name}] {body}" if body else f"[{name}] {text}",
                    memory_type=memory_type,
                    tags=tags,
                    source_file=str(md_file),
                    subtype=cc_type,
                )
            )

    return memories


def parse_memory_md_sections() -> list[SyncMemory]:
    """Parse MEMORY.md into structured sections (patterns, projects, etc.)."""
    memories = []
    memory_md = CC_MEMORY_DIR / "MEMORY.md"
    if not memory_md.exists():
        return memories

    text = memory_md.read_text()
    sections = re.split(r"\n(?=## )", text)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Extract section title
        title_match = re.match(r"^## (.+)", section)
        if not title_match:
            continue
        title = title_match.group(1).strip()

        # Route sections to appropriate types
        if "Pattern" in title or "Gotcha" in title:
            # Individual patterns are most useful as separate memories
            patterns = chunk_patterns(section)
            for i, pattern in enumerate(patterns):
                if len(pattern) < 20:
                    continue
                memories.append(
                    SyncMemory(
                        content=pattern,
                        memory_type=MemoryType.PROCEDURAL,
                        tags=["claude-code", "pattern", "gotcha"],
                        source_file=str(memory_md),
                        chunk_index=i,
                        subtype="pattern",
                    )
                )
        elif "Project" in title and "Index" in title:
            # Project table — one memory for the whole fleet
            memories.append(
                SyncMemory(
                    content=f"[Project Fleet Status] {section}",
                    memory_type=MemoryType.SEMANTIC,
                    tags=["claude-code", "fleet", "project-index"],
                    source_file=str(memory_md),
                    subtype="fleet",
                )
            )
        elif "Monetization" in title:
            memories.append(
                SyncMemory(
                    content=f"[Monetization] {section}",
                    memory_type=MemoryType.SEMANTIC,
                    tags=["claude-code", "monetization", "infrastructure"],
                    source_file=str(memory_md),
                    subtype="business",
                )
            )
        elif "User Profile" in title:
            memories.append(
                SyncMemory(
                    content=f"[User Profile] {section}",
                    memory_type=MemoryType.SEMANTIC,
                    tags=["claude-code", "user-profile", "arete"],
                    source_file=str(memory_md),
                    subtype="profile",
                )
            )
        elif "Frontier" in title or "EVE" in title or "Hackathon" in title:
            memories.append(
                SyncMemory(
                    content=section,
                    memory_type=MemoryType.SEMANTIC,
                    tags=["claude-code", "eve-frontier"],
                    source_file=str(memory_md),
                    subtype="project",
                )
            )
        elif "TODO" in title:
            # Skip ephemeral TODOs
            continue
        elif "Topic" in title:
            # Skip — just an index of file references
            continue
        elif "Feedback" in title:
            memories.append(
                SyncMemory(
                    content=section,
                    memory_type=MemoryType.PROCEDURAL,
                    tags=["claude-code", "feedback"],
                    source_file=str(memory_md),
                    subtype="feedback",
                )
            )
        else:
            # Catch-all for other sections
            if len(section) > 50:
                memories.append(
                    SyncMemory(
                        content=section,
                        memory_type=MemoryType.SEMANTIC,
                        tags=["claude-code", "context"],
                        source_file=str(memory_md),
                    )
                )

    return memories


def parse_notes_repo() -> list[SyncMemory]:
    """Parse notes repo files into SyncMemory objects."""
    memories = []

    if not NOTES_DIR.exists():
        print(f"  [skip] Notes dir not found: {NOTES_DIR}")
        return memories

    for md_file in sorted(NOTES_DIR.rglob("*.md")):
        rel_path = str(md_file.relative_to(NOTES_DIR))

        # Skip excluded files
        if md_file.name in SKIP_FILES:
            continue
        if any(rel_path.startswith(p) for p in SKIP_PREFIXES):
            continue
        # Skip ideas/ (not actionable)
        if rel_path.startswith("ideas/"):
            continue
        # Whitelist topics/ — only high-signal files
        if rel_path.startswith("topics/") and md_file.name not in NOTES_TOPICS_INCLUDE:
            continue
        # Decisions: skip the README
        if rel_path.startswith("decisions/") and md_file.name == "README.md":
            continue

        text = md_file.read_text()
        if not text.strip() or len(text) < 50:
            continue

        # Determine type and tags from path
        memory_type = MemoryType.SEMANTIC
        tags = ["claude-code", "notes-repo"]
        for pattern, mtype, base_tags in NOTES_RULES:
            if rel_path.startswith(pattern) or rel_path == pattern:
                memory_type = mtype
                tags.extend(base_tags)
                break

        tags.append(f"source:{rel_path}")

        # For large reference files (ci-cd, python, security, etc.),
        # store as max 3 chunks to avoid noise. Decisions get more granularity.
        is_reference = rel_path.startswith("topics/") and md_file.name not in {
            f for f in NOTES_TOPICS_INCLUDE if f.startswith("harvest-")
        }
        max_chunks = 3 if is_reference else 10

        if len(text) > MAX_CHUNK_SIZE:
            chunks = chunk_by_headers(text)[:max_chunks]
            for i, chunk in enumerate(chunks):
                if len(chunk) < 30:
                    continue
                memories.append(
                    SyncMemory(
                        content=f"[notes/{rel_path}] {chunk}",
                        memory_type=memory_type,
                        tags=tags.copy(),
                        source_file=str(md_file),
                        chunk_index=i,
                    )
                )
        else:
            memories.append(
                SyncMemory(
                    content=f"[notes/{rel_path}] {text}",
                    memory_type=memory_type,
                    tags=tags,
                    source_file=str(md_file),
                )
            )

    return memories


def sync(
    sources: list[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
    quiet: bool = False,
) -> dict:
    """Run the sync pipeline. Returns stats dict."""
    if sources is None:
        sources = ["cc", "notes"]

    state = SyncState.load(SYNC_STATE_FILE) if not force else SyncState()

    # Collect memories from sources
    all_memories: list[SyncMemory] = []

    if "cc" in sources:
        if not quiet:
            print("Parsing Claude Code memory files...")
        all_memories.extend(parse_cc_memory_files())
        all_memories.extend(parse_memory_md_sections())

    if "notes" in sources:
        if not quiet:
            print("Parsing notes repo...")
        all_memories.extend(parse_notes_repo())

    if not quiet:
        print(f"Found {len(all_memories)} memory candidates")

    # Deduplicate
    new_memories = []
    skipped = 0
    for mem in all_memories:
        h = mem.content_hash
        if h in state.synced and not force:
            skipped += 1
        else:
            new_memories.append(mem)

    if not quiet:
        print(f"New: {len(new_memories)}, Skipped (already synced): {skipped}")

    if dry_run:
        if not quiet:
            print("\n--- DRY RUN ---")
            for mem in new_memories:
                src = Path(mem.source_file).name if mem.source_file else "?"
                print(
                    f"  [{mem.memory_type.value:10}] "
                    f"[{','.join(mem.tags[:3]):30}] "
                    f"{src}#{mem.chunk_index}: "
                    f"{mem.content[:80]}..."
                )
        return {
            "total_candidates": len(all_memories),
            "new": len(new_memories),
            "skipped": skipped,
            "pushed": 0,
            "dry_run": True,
        }

    # Initialize Animus
    if not quiet:
        print("Connecting to Animus MemoryLayer...")
    config = AnimusConfig.load()
    memory_layer = MemoryLayer(data_dir=config.data_dir, backend=config.memory.backend)

    # Push new memories
    pushed = 0
    errors = 0
    for mem in new_memories:
        try:
            result = memory_layer.remember(
                content=mem.content,
                memory_type=mem.memory_type,
                tags=mem.tags,
                source="learned",  # Learned from Claude Code context
                confidence=0.9,  # High but not 1.0 (not directly stated to Animus)
                subtype=mem.subtype,
                provenance="sync",
            )
            state.synced[mem.content_hash] = {
                "animus_id": result.id,
                "source": mem.source_file,
                "chunk": mem.chunk_index,
                "synced_at": datetime.now().isoformat(),
            }
            pushed += 1
        except Exception as e:
            errors += 1
            if not quiet:
                print(f"  [error] {e}")

    # Save state
    state.last_sync = datetime.now().isoformat()
    state.save(SYNC_STATE_FILE)

    if not quiet:
        print(f"\nSync complete: {pushed} pushed, {errors} errors")

    return {
        "total_candidates": len(all_memories),
        "new": len(new_memories),
        "skipped": skipped,
        "pushed": pushed,
        "errors": errors,
        "dry_run": False,
    }


def show_stats() -> None:
    """Show sync state statistics."""
    state = SyncState.load(SYNC_STATE_FILE)
    print(f"Last sync: {state.last_sync or 'never'}")
    print(f"Total synced memories: {len(state.synced)}")

    if state.synced:
        sources: dict[str, int] = {}
        for entry in state.synced.values():
            src = Path(entry.get("source", "unknown")).name
            sources[src] = sources.get(src, 0) + 1
        print("\nBy source file:")
        for src, count in sorted(sources.items(), key=lambda x: -x[1]):
            print(f"  {src}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Claude Code context → Animus memory")
    parser.add_argument("--dry-run", action="store_true", help="Preview without pushing")
    parser.add_argument("--force", action="store_true", help="Re-sync everything")
    parser.add_argument("--source", choices=["cc", "notes"], help="Sync only one source")
    parser.add_argument("--stats", action="store_true", help="Show sync statistics")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    sources = [args.source] if args.source else None
    result = sync(sources=sources, dry_run=args.dry_run, force=args.force, quiet=args.quiet)

    if not args.quiet:
        print(f"\nResult: {json.dumps(result, indent=2)}")

    # Exit code: 0 if no errors, 1 if errors
    sys.exit(1 if result.get("errors", 0) > 0 else 0)


if __name__ == "__main__":
    main()

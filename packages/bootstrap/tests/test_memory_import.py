"""Tests for the explicit, dry-run-first bootstrap memory importer."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from animus_bootstrap.intelligence.memory_import import import_candidates_sync, load_candidate


def test_load_candidate_records_hash_and_deterministic_fingerprint(tmp_path: Path) -> None:
    source = tmp_path / "handoff.md"
    source.write_text("# approved handoff\n", encoding="utf-8")
    candidate = load_candidate(source, "procedural")
    assert candidate.source_name == "handoff.md"
    assert len(candidate.source_sha256) == 64
    assert candidate.fingerprint == load_candidate(source, "procedural").fingerprint
    assert candidate.metadata["importer"] == "bootstrap_memory_import_v1"


@pytest.mark.parametrize("memory_type", ["bad", "", "all"])
def test_load_candidate_rejects_invalid_type(tmp_path: Path, memory_type: str) -> None:
    source = tmp_path / "handoff.md"
    source.write_text("content", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid memory type"):
        load_candidate(source, memory_type)


def test_load_candidate_rejects_symlink_and_non_utf8(tmp_path: Path) -> None:
    real = tmp_path / "real.md"
    real.write_bytes(b"\xff")
    link = tmp_path / "link.md"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="regular non-symlink"):
        load_candidate(link, "semantic")
    with pytest.raises(ValueError, match="not UTF-8"):
        load_candidate(real, "semantic")


def test_dry_run_does_not_create_database(tmp_path: Path) -> None:
    source = tmp_path / "handoff.md"
    source.write_text("one approved handoff", encoding="utf-8")
    db = tmp_path / "new.db"
    result = import_candidates_sync(db, [load_candidate(source, "episodic")])
    assert result[0].action == "planned"
    assert not db.exists()


def test_apply_imports_and_skips_exact_duplicates(tmp_path: Path) -> None:
    source = tmp_path / "handoff.md"
    source.write_text("one approved handoff", encoding="utf-8")
    db = tmp_path / "memory.db"
    candidate = load_candidate(source, "episodic")
    first = import_candidates_sync(db, [candidate], apply=True)
    second = import_candidates_sync(db, [candidate], apply=True)
    assert first[0].action == "imported"
    assert second[0].action == "duplicate"
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1


def test_duplicate_within_one_plan_is_reported(tmp_path: Path) -> None:
    source = tmp_path / "handoff.md"
    source.write_text("same content", encoding="utf-8")
    candidate = load_candidate(source, "semantic")
    result = import_candidates_sync(tmp_path / "memory.db", [candidate, candidate])
    assert [item.action for item in result] == ["planned", "duplicate"]

"""Tests for database schema definitions and Alembic migrations.

These tests do NOT require a running PostgreSQL instance.
They verify that migration scripts are syntactically valid, that
upgrade/downgrade are idempotent, and that table definitions match
expected shapes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from alembic import command
from alembic import config as alembic_config
from sqlalchemy import create_engine, inspect

MIGRATION_DIR = Path(__file__).parent.parent / "migrations" / "versions"
INI_PATH = Path(__file__).parent.parent / "alembic.ini"


def _load_migration_tree():
    """Parse the initial migration file into an AST."""
    mig_file = next(MIGRATION_DIR.glob("001_*.py"))
    return ast.parse(mig_file.read_text())


class TestMigrationSyntax:
    def test_initial_migration_syntax(self):
        """The 001 migration must be valid Python with upgrade/downgrade."""
        tree = _load_migration_tree()
        funcs = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name in ("upgrade", "downgrade")
        }
        assert funcs == {"upgrade", "downgrade"}, "Migration must define upgrade() and downgrade()"

    def test_initial_migration_creates_three_tables(self):
        """001_initial_schema must create object_registry, event_ledger, traceability."""
        tree = _load_migration_tree()
        create_table_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_table"
        ]
        table_names = {
            node.args[0].value
            for node in create_table_calls
            if isinstance(node.args[0], ast.Constant)
        }
        assert table_names == {"object_registry", "event_ledger", "traceability"}, (
            f"Expected exactly 3 tables, got {table_names}"
        )

    def test_object_registry_has_bitemporal_columns(self):
        """object_registry must contain valid_from, valid_to, recorded_at, superseded_at."""
        mig_file = next(MIGRATION_DIR.glob("001_*.py"))
        source = mig_file.read_text()
        for col in ("valid_from", "valid_to", "recorded_at", "superseded_at"):
            assert col in source, f"Column {col!r} missing from object_registry migration"

    def test_event_ledger_is_append_only_no_update(self):
        """event_ledger has no update/delete triggers in initial migration."""
        mig_file = next(MIGRATION_DIR.glob("001_*.py"))
        source = mig_file.read_text()
        assert "event_ledger" in source
        # No UPDATE/DELETE triggers should exist yet (append-only table)
        assert "CREATE TRIGGER" not in source.upper()


class TestMigrationExecution:
    """Run migrations against SQLite in-memory to verify they execute cleanly."""

    @pytest.fixture(scope="class")
    def sqlite_engine(self):
        """Provide a fresh SQLite file-backed engine for migration persistence."""
        # Use a temp file so tables survive across connections (Alembic env.py creates its own)
        import tempfile

        fd, path = tempfile.mkstemp(suffix=".db")
        import os

        os.close(fd)
        engine = create_engine(f"sqlite:///{path}")
        yield engine
        engine.dispose()
        os.unlink(path)

    @pytest.fixture
    def alembic_cfg(self, sqlite_engine):
        """Configure Alembic to use the SQLite engine."""
        cfg = alembic_config.Config(str(INI_PATH))
        cfg.set_main_option("sqlalchemy.url", str(sqlite_engine.url))
        return cfg

    def test_upgrade_creates_tables(self, sqlite_engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(sqlite_engine)
        tables = inspector.get_table_names()
        assert "object_registry" in tables
        assert "event_ledger" in tables
        assert "traceability" in tables

    def test_downgrade_removes_tables(self, sqlite_engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        command.downgrade(alembic_cfg, "base")
        inspector = inspect(sqlite_engine)
        tables = inspector.get_table_names()
        assert "object_registry" not in tables
        assert "event_ledger" not in tables
        assert "traceability" not in tables

    def test_upgrade_downgrade_upgrade_idempotent(self, sqlite_engine, alembic_cfg):
        """Upgrade → downgrade → upgrade must result in the same schema."""
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(sqlite_engine)
        first_tables = set(inspector.get_table_names())
        first_columns = {t: {c["name"] for c in inspector.get_columns(t)} for t in first_tables}

        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")

        inspector = inspect(sqlite_engine)
        second_tables = set(inspector.get_table_names())
        second_columns = {t: {c["name"] for c in inspector.get_columns(t)} for t in second_tables}

        assert first_tables == second_tables
        assert first_columns == second_columns

    def test_object_registry_indexes_exist(self, sqlite_engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(sqlite_engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("object_registry")}
        expected = {
            "idx_object_id_version",
            "idx_artifact_type",
            "idx_subject_domain",
            "idx_valid_from",
            "idx_recorded_at",
            "idx_trace_id",
        }
        assert expected.issubset(indexes), f"Missing indexes: {expected - indexes}"

    def test_event_ledger_indexes_exist(self, sqlite_engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(sqlite_engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("event_ledger")}
        expected = {
            "idx_event_kind",
            "idx_occurred_at",
            "idx_idempotency_key",
        }
        assert expected.issubset(indexes), f"Missing indexes: {expected - indexes}"

    def test_traceability_indexes_exist(self, sqlite_engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(sqlite_engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("traceability")}
        assert "idx_req_id" in indexes

    def test_object_registry_column_types(self, sqlite_engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(sqlite_engine)
        columns = {
            c["name"]: c["type"].__class__.__name__
            for c in inspector.get_columns("object_registry")
        }
        # Migration 002 uses SQLite's INTEGER PRIMARY KEY for generated IDs.
        assert columns["id"] == "INTEGER"
        assert columns["object_id"] == "VARCHAR"
        assert columns["payload"] == "JSON"
        assert columns["valid_from"] == "DATETIME"
        assert columns["recorded_at"] == "DATETIME"

    def test_event_ledger_has_append_only_shape(self, sqlite_engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(sqlite_engine)
        columns = {c["name"] for c in inspector.get_columns("event_ledger")}
        assert "event_kind" in columns
        assert "occurred_at" in columns
        assert "actor_refs" in columns
        assert "object_refs" in columns
        assert "event_data" in columns

    def test_object_registry_unique_constraint(self, sqlite_engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(sqlite_engine)
        indexes = inspector.get_indexes("object_registry")
        unique_indexes = [idx for idx in indexes if idx.get("unique")]
        names = {idx["name"] for idx in unique_indexes}
        assert "idx_object_id_version" in names

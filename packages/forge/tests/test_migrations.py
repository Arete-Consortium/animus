"""Tests for database migrations module."""

import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, "src")

from animus_forge.state.migrations import (
    _adapt_sql_for_postgres,
    _get_applied_migrations,
    _get_migration_files,
    get_migration_status,
    run_migrations,
)


class TestAdaptSqlForPostgres:
    """Tests for SQL adaptation function."""

    def test_converts_autoincrement(self):
        """Converts INTEGER PRIMARY KEY AUTOINCREMENT to SERIAL."""
        sql = "CREATE TABLE test (id INTEGER PRIMARY KEY AUTOINCREMENT);"
        result = _adapt_sql_for_postgres(sql)
        assert "SERIAL PRIMARY KEY" in result
        assert "AUTOINCREMENT" not in result

    def test_case_insensitive(self):
        """Handles different cases."""
        sql = "id integer primary key autoincrement"
        result = _adapt_sql_for_postgres(sql)
        assert "SERIAL PRIMARY KEY" in result

    def test_preserves_other_sql(self):
        """Preserves SQL that doesn't need adaptation."""
        sql = "CREATE TABLE test (name TEXT NOT NULL);"
        result = _adapt_sql_for_postgres(sql)
        assert result == sql

    def test_multiple_tables(self):
        """Handles multiple table definitions."""
        sql = """
        CREATE TABLE t1 (id INTEGER PRIMARY KEY AUTOINCREMENT);
        CREATE TABLE t2 (id INTEGER PRIMARY KEY AUTOINCREMENT);
        """
        result = _adapt_sql_for_postgres(sql)
        assert result.count("SERIAL PRIMARY KEY") == 2
        assert "AUTOINCREMENT" not in result


class TestGetAppliedMigrations:
    """Tests for getting applied migrations."""

    def test_returns_empty_set_when_no_table(self):
        """Returns empty set when schema_migrations table doesn't exist."""
        mock_backend = MagicMock()
        mock_backend.fetchall.side_effect = Exception("table not found")

        result = _get_applied_migrations(mock_backend)
        assert result == set()

    def test_returns_applied_versions(self):
        """Returns set of applied migration versions."""
        mock_backend = MagicMock()
        mock_backend.fetchall.return_value = [
            {"version": "001"},
            {"version": "002"},
            {"version": "003"},
        ]

        result = _get_applied_migrations(mock_backend)
        assert result == {"001", "002", "003"}

    def test_postgres_checks_table_exists(self):
        """PostgreSQL backend checks if table exists first."""
        from animus_forge.state.backends import PostgresBackend

        mock_backend = MagicMock(spec=PostgresBackend)
        mock_backend.fetchone.return_value = {"exists": False}

        result = _get_applied_migrations(mock_backend)
        assert result == set()

    def test_postgres_table_exists(self):
        """PostgreSQL fetches migrations when table exists."""
        from animus_forge.state.backends import PostgresBackend

        mock_backend = MagicMock(spec=PostgresBackend)
        mock_backend.fetchone.return_value = {"exists": True}
        mock_backend.fetchall.return_value = [{"version": "001"}]

        result = _get_applied_migrations(mock_backend)
        assert result == {"001"}


class TestGetMigrationFiles:
    """Tests for finding migration files."""

    def test_returns_empty_when_no_dir(self):
        """Returns empty list when migrations directory doesn't exist."""
        with patch("animus_forge.state.migrations.MIGRATIONS_DIR") as mock_dir:
            mock_dir.exists.return_value = False
            result = _get_migration_files()
            assert result == []

    def test_finds_sql_files(self):
        """Finds and sorts SQL migration files."""
        mock_files = [
            MagicMock(name="003_third.sql"),
            MagicMock(name="001_first.sql"),
            MagicMock(name="002_second.sql"),
        ]
        for f, name in zip(mock_files, ["003_third.sql", "001_first.sql", "002_second.sql"]):
            f.name = name

        with patch("animus_forge.state.migrations.MIGRATIONS_DIR") as mock_dir:
            mock_dir.exists.return_value = True
            mock_dir.glob.return_value = mock_files

            result = _get_migration_files()

            # Should be sorted by version
            versions = [v for v, _ in result]
            assert versions == ["001", "002", "003"]

    def test_ignores_non_versioned_files(self):
        """Ignores files without version prefix."""
        mock_files = [
            MagicMock(name="001_valid.sql"),
            MagicMock(name="readme.sql"),
            MagicMock(name="notes.sql"),
        ]
        for f, name in zip(mock_files, ["001_valid.sql", "readme.sql", "notes.sql"]):
            f.name = name

        with patch("animus_forge.state.migrations.MIGRATIONS_DIR") as mock_dir:
            mock_dir.exists.return_value = True
            mock_dir.glob.return_value = mock_files

            result = _get_migration_files()
            assert len(result) == 1
            assert result[0][0] == "001"


class TestRunMigrations:
    """Tests for running migrations."""

    def test_returns_empty_when_no_files(self):
        """Returns empty list when no migration files exist."""
        mock_backend = MagicMock()

        with patch("animus_forge.state.migrations._get_migration_files", return_value=[]):
            result = run_migrations(mock_backend)
            assert result == []

    def test_skips_already_applied(self):
        """Skips migrations that are already applied."""
        mock_backend = MagicMock()
        mock_file = MagicMock()
        mock_file.read_text.return_value = "CREATE TABLE test;"
        mock_file.stem = "001_initial"

        with patch("animus_forge.state.migrations._get_applied_migrations", return_value={"001"}):
            with patch(
                "animus_forge.state.migrations._get_migration_files",
                return_value=[("001", mock_file)],
            ):
                result = run_migrations(mock_backend)
                assert result == []

    def test_applies_pending_migration(self):
        """Applies pending migrations."""
        mock_backend = MagicMock()
        mock_backend.transaction.return_value.__enter__ = MagicMock()
        mock_backend.transaction.return_value.__exit__ = MagicMock(return_value=False)

        mock_file = MagicMock()
        mock_file.read_text.return_value = "CREATE TABLE test;"
        mock_file.stem = "001_initial"
        mock_file.name = "001_initial.sql"

        with patch("animus_forge.state.migrations._get_applied_migrations", return_value=set()):
            with patch(
                "animus_forge.state.migrations._get_migration_files",
                return_value=[("001", mock_file)],
            ):
                result = run_migrations(mock_backend)

                assert result == ["001"]
                mock_backend.executescript.assert_called_once()
                mock_backend.execute.assert_called_once()

    def test_raises_on_failure(self):
        """Raises RuntimeError when migration fails."""
        mock_backend = MagicMock()
        mock_backend.transaction.return_value.__enter__ = MagicMock()
        mock_backend.transaction.return_value.__exit__ = MagicMock(return_value=False)
        mock_backend.executescript.side_effect = Exception("SQL error")

        mock_file = MagicMock()
        mock_file.read_text.return_value = "INVALID SQL;"
        mock_file.stem = "001_bad"
        mock_file.name = "001_bad.sql"

        with patch("animus_forge.state.migrations._get_applied_migrations", return_value=set()):
            with patch(
                "animus_forge.state.migrations._get_migration_files",
                return_value=[("001", mock_file)],
            ):
                with pytest.raises(RuntimeError, match="Migration 001 failed"):
                    run_migrations(mock_backend)


class TestGetMigrationStatus:
    """Tests for migration status checking."""

    def test_up_to_date(self):
        """Returns up_to_date True when all migrations applied."""
        mock_backend = MagicMock()
        mock_file = MagicMock()

        with patch(
            "animus_forge.state.migrations._get_applied_migrations",
            return_value={"001", "002"},
        ):
            with patch(
                "animus_forge.state.migrations._get_migration_files",
                return_value=[("001", mock_file), ("002", mock_file)],
            ):
                result = get_migration_status(mock_backend)

                assert result["up_to_date"] is True
                assert result["pending"] == []
                assert sorted(result["applied"]) == ["001", "002"]

    def test_pending_migrations(self):
        """Returns pending migrations list."""
        mock_backend = MagicMock()
        mock_file = MagicMock()

        with patch("animus_forge.state.migrations._get_applied_migrations", return_value={"001"}):
            with patch(
                "animus_forge.state.migrations._get_migration_files",
                return_value=[
                    ("001", mock_file),
                    ("002", mock_file),
                    ("003", mock_file),
                ],
            ):
                result = get_migration_status(mock_backend)

                assert result["up_to_date"] is False
                assert result["pending"] == ["002", "003"]
                assert result["applied"] == ["001"]

    def test_no_migrations(self):
        """Handles case with no migrations."""
        mock_backend = MagicMock()

        with patch("animus_forge.state.migrations._get_applied_migrations", return_value=set()):
            with patch("animus_forge.state.migrations._get_migration_files", return_value=[]):
                result = get_migration_status(mock_backend)

                assert result["up_to_date"] is True
                assert result["pending"] == []
                assert result["applied"] == []


def test_cost_reservations_survive_migration_and_restart(tmp_path):
    """Real migration 022 must preserve outstanding holds across manager restarts."""
    from decimal import Decimal

    from animus_forge.scheduler.cost_enforcer import CostEnforcer
    from animus_forge.state.backends import SQLiteBackend

    backend = SQLiteBackend(str(tmp_path / "migrated.db"))
    try:
        assert "022" in run_migrations(backend)
        cost = CostEnforcer(backend)
        assert cost.reserve("attempt", "mission", Decimal("0.60"), mission_cap=Decimal("1"))[0]
        backend.close()
        assert run_migrations(backend) == []
        restarted = CostEnforcer(backend)
        assert restarted.reserved("mission") == Decimal("0.60")
        assert not restarted.reserve(
            "second", "mission", Decimal("0.60"), mission_cap=Decimal("1")
        )[0]
    finally:
        backend.close()

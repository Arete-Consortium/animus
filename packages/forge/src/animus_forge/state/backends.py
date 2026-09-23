"""Database backend abstraction for state persistence."""

from __future__ import annotations

import sqlite3
import threading
from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class DatabaseBackend(ABC):
    """Abstract base class for database backends."""

    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute a query and return cursor."""
        pass

    @abstractmethod
    def executemany(self, query: str, params_list: list[tuple]) -> Any:
        """Execute a query with multiple parameter sets."""
        pass

    @abstractmethod
    def executescript(self, script: str) -> None:
        """Execute multiple SQL statements."""
        pass

    @abstractmethod
    def fetchone(self, query: str, params: tuple = ()) -> dict | None:
        """Execute query and fetch one row as dict."""
        pass

    @abstractmethod
    def fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        """Execute query and fetch all rows as dicts."""
        pass

    @abstractmethod
    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Context manager for transactions."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close database connection."""
        pass

    @property
    @abstractmethod
    def placeholder(self) -> str:
        """Parameter placeholder style ('?' for SQLite, '%s' for PostgreSQL)."""
        pass

    def adapt_query(self, query: str) -> str:
        """Adapt query placeholders for this backend."""
        if self.placeholder == "?":
            return query
        return query.replace("?", self.placeholder)


class SQLiteBackend(DatabaseBackend):
    """SQLite database backend."""

    def __init__(self, db_path: str = "animus-forge-state.db"):
        """Initialize SQLite backend.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA foreign_keys = ON")
        return self._local.conn

    @property
    def placeholder(self) -> str:
        return "?"

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query and return cursor."""
        conn = self._get_conn()
        return conn.execute(query, params)

    def executemany(self, query: str, params_list: list[tuple]) -> sqlite3.Cursor:
        """Execute a query with multiple parameter sets."""
        conn = self._get_conn()
        return conn.executemany(query, params_list)

    def executescript(self, script: str) -> None:
        """Execute multiple SQL statements."""
        conn = self._get_conn()
        conn.executescript(script)
        conn.commit()

    def fetchone(self, query: str, params: tuple = ()) -> dict | None:
        """Execute query and fetch one row as dict."""
        cursor = self.execute(query, params)
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        """Execute query and fetch all rows as dicts."""
        cursor = self.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Context manager for transactions.

        Supports nested calls via SAVEPOINT so multiple manager operations can
        be composed inside a single outer transaction. Top-level calls commit
        or rollback the real transaction; nested calls release or roll back to
        the savepoint.
        """
        conn = self._get_conn()
        depth = getattr(self._local, "tx_depth", 0)
        self._local.tx_depth = depth + 1
        savepoint = f"sp_{depth}"
        try:
            if depth == 0:
                conn.execute("BEGIN")
            else:
                conn.execute(f"SAVEPOINT {savepoint}")
            yield
            if depth == 0:
                conn.commit()
            else:
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            if depth == 0:
                conn.rollback()
            else:
                try:
                    conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                except Exception:
                    pass
            raise
        finally:
            self._local.tx_depth -= 1

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


class PostgresBackend(DatabaseBackend):
    """PostgreSQL database backend."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "animus_forge",
        user: str = "animus_forge",
        password: str = "",
        connection_string: str | None = None,
    ):
        """Initialize PostgreSQL backend.

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            connection_string: Optional connection string (overrides other params)
        """
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor

            self._psycopg2 = psycopg2
            self._RealDictCursor = RealDictCursor
        except ImportError:
            raise ImportError(
                "psycopg2 is required for PostgreSQL backend. "
                "Install with: pip install psycopg2-binary"
            )

        if connection_string:
            parsed = urlparse(connection_string)
            self._conn_params = {
                "host": parsed.hostname or "localhost",
                "port": parsed.port or 5432,
                "database": parsed.path.lstrip("/") or "animus_forge",
                "user": parsed.username or "animus_forge",
                "password": parsed.password or "",
            }
        else:
            self._conn_params = {
                "host": host,
                "port": port,
                "database": database,
                "user": user,
                "password": password,
            }

        self._local = threading.local()

    def _get_conn(self):
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = self._psycopg2.connect(**self._conn_params)
        return self._local.conn

    @property
    def placeholder(self) -> str:
        return "%s"

    def execute(self, query: str, params: tuple = ()):
        """Execute a query and return cursor."""
        conn = self._get_conn()
        cursor = conn.cursor(cursor_factory=self._RealDictCursor)
        cursor.execute(self.adapt_query(query), params)
        return cursor

    def executemany(self, query: str, params_list: list[tuple]):
        """Execute a query with multiple parameter sets."""
        conn = self._get_conn()
        cursor = conn.cursor(cursor_factory=self._RealDictCursor)
        cursor.executemany(self.adapt_query(query), params_list)
        return cursor

    def executescript(self, script: str) -> None:
        """Execute multiple SQL statements."""
        import re

        # Adapt SQLite-specific syntax for PostgreSQL
        script = self._adapt_schema(script)

        # Remove SQL comments
        script = re.sub(r"--.*$", "", script, flags=re.MULTILINE)

        # Split on semicolon followed by whitespace/newline
        statements = re.split(r";\s*\n", script)
        statements = [s.strip() for s in statements if s.strip()]

        conn = self._get_conn()
        cursor = conn.cursor()

        for stmt in statements:
            if stmt:
                cursor.execute(stmt)

    def _adapt_schema(self, script: str) -> str:
        """Adapt SQLite schema syntax for PostgreSQL."""
        # Replace AUTOINCREMENT with SERIAL
        script = script.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        # Replace TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        script = script.replace(
            "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        )
        return script

    def fetchone(self, query: str, params: tuple = ()) -> dict | None:
        """Execute query and fetch one row as dict."""
        cursor = self.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        """Execute query and fetch all rows as dicts."""
        cursor = self.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Context manager for transactions.

        Supports nested calls via SAVEPOINT so multiple manager operations can
        be composed inside a single outer transaction. Top-level calls commit
        or rollback the real transaction; nested calls release or roll back to
        the savepoint.
        """
        conn = self._get_conn()
        depth = getattr(self._local, "tx_depth", 0)
        self._local.tx_depth = depth + 1
        savepoint = f"sp_{depth}"
        try:
            if depth == 0:
                conn.execute("BEGIN")
            else:
                conn.execute(f"SAVEPOINT {savepoint}")
            yield
            if depth == 0:
                conn.commit()
            else:
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            if depth == 0:
                conn.rollback()
            else:
                try:
                    conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                except Exception:
                    pass
            raise
        finally:
            self._local.tx_depth -= 1

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


def create_backend(url: str | None = None, **kwargs) -> DatabaseBackend:
    """Create a database backend from URL or kwargs.

    Args:
        url: Database URL (sqlite:///path.db or postgresql://user:pass@host/db)
        **kwargs: Backend-specific parameters

    Returns:
        Configured DatabaseBackend instance

    Examples:
        >>> backend = create_backend("sqlite:///animus-forge.db")
        >>> backend = create_backend("postgresql://user:pass@localhost/animus_forge")
        >>> backend = create_backend(db_path="animus-forge.db")  # SQLite default
    """
    if url:
        parsed = urlparse(url)
        scheme = parsed.scheme

        if scheme in ("sqlite", "sqlite3"):
            path = parsed.path
            if path.startswith("///"):
                path = path[3:]
            elif path.startswith("/"):
                path = path[1:]
            return SQLiteBackend(db_path=path or "animus-forge-state.db")

        elif scheme in ("postgres", "postgresql"):
            return PostgresBackend(connection_string=url)

        else:
            raise ValueError(f"Unsupported database scheme: {scheme}")

    # Default to SQLite
    return SQLiteBackend(**kwargs)

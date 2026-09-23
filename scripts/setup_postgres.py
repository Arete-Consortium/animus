#!/usr/bin/env python3
"""PostgreSQL setup script for Animus durable core.

Checks connectivity, creates the DB if missing, runs Alembic migrations,
and prints a health summary.

Usage::

    export ANIMUS_DATABASE_URL="postgres..."
    python scripts/setup_postgres.py

Or set component env vars (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB,
POSTGRES_HOST, POSTGRES_PORT) and the script will compose the URL.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def _compose_url() -> str | None:
    """Build connection string from env vars."""
    url = os.getenv("ANIMUS_DATABASE_URL")
    if url:
        return url

    user = os.getenv("POSTGRES_USER")
    pw = os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("POSTGRES_DB")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")

    if user and pw and db:
        return f"postgresql://{user}:{pw}@{host}:{port}/{db}"
    return None


def _check_sqlalchemy(url: str) -> bool:
    try:
        from sqlalchemy import create_engine, text

        eng = create_engine(url, connect_args={"connect_timeout": 5})
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        print(f"  ✗ Connection failed: {exc}")
        return False


def _create_db(url: str) -> bool:
    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/") or parsed.path
    if not db_name:
        print("  ✗ Could not extract DB name from URL")
        return False

    base = (
        f"{parsed.scheme}://{parsed.username}:{parsed.password}"
        f"@{parsed.hostname}:{parsed.port or 5432}/postgres"
    )
    try:
        import psycopg2

        conn = psycopg2.connect(base, connect_timeout=5)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        exists = cur.fetchone() is not None
        if not exists:
            cur.execute(f"CREATE DATABASE {db_name}")
            print(f"  ✓ Created DB '{db_name}'")
        else:
            print(f"  • DB '{db_name}' already exists")
        cur.close()
        conn.close()
        return True
    except Exception as exc:
        print(f"  ✗ Failed to create DB: {exc}")
        return False


def _run_migrations() -> bool:
    db_dir = Path(__file__).resolve().parent.parent / "database"
    if not (db_dir / "alembic.ini").exists():
        print(f"  ✗ alembic.ini not found in {db_dir}")
        return False

    try:
        subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=db_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        print("  ✓ Migrations applied")
        return True
    except subprocess.CalledProcessError as exc:
        print(f"  ✗ Migration failed: {exc.stderr.strip()}")
        return False
    except FileNotFoundError:
        print("  ✗ alembic not found — pip install alembic")
        return False


def main() -> int:
    print("=" * 50)
    print("Animus PostgreSQL Setup")
    print("=" * 50)

    url = _compose_url()
    if not url:
        print(
            "\n  ✗ No DB URL configured.\n"
            "     Set ANIMUS_DATABASE_URL or POSTGRES_USER + POSTGRES_PASSWORD + POSTGRES_DB\n"
        )
        return 1

    safe_url = url.replace(urlparse(url).password or "", "***")
    print(f"\nURL: {safe_url}")

    print("\n1. Checking connectivity ...")
    if _check_sqlalchemy(url):
        print("  ✓ Reachable")
    else:
        print("\n  Attempting to create DB ...")
        if not _create_db(url):
            return 1
        if not _check_sqlalchemy(url):
            return 1
        print("  ✓ Reachable after create")

    print("\n2. Running migrations ...")
    if not _run_migrations():
        return 1

    print("\n3. Health check ...")
    try:
        from sqlalchemy import create_engine, text

        eng = create_engine(url)
        with eng.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            result = conn.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
            )
            table_count = result.scalar()
        print(f"  ✓ Version: {version.split()[1] if version else 'unknown'}")
        print(f"  ✓ Public tables: {table_count}")
    except Exception as exc:
        print(f"  ✗ Health query failed: {exc}")
        return 1

    print("\n" + "=" * 50)
    print("Setup complete.")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Native PostgreSQL backup and restore for a dedicated Animus registry."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from animus.durability.export import DurabilityError

_EMPTY_DATABASE = """
SELECT NOT (
    EXISTS (SELECT FROM pg_namespace
            WHERE nspname <> 'public' AND nspname <> 'information_schema'
              AND nspname !~ '^pg_')
    OR EXISTS (SELECT FROM pg_class WHERE relnamespace = to_regnamespace('public'))
    OR EXISTS (SELECT FROM pg_proc WHERE pronamespace = to_regnamespace('public'))
    OR EXISTS (SELECT FROM pg_type WHERE typnamespace = to_regnamespace('public'))
    OR EXISTS (SELECT FROM pg_extension WHERE extname <> 'plpgsql')
)
"""


@contextmanager
def _service(url: str) -> Iterator[dict[str, str]]:
    """Pass connection settings in a private libpq service file."""
    from psycopg.conninfo import conninfo_to_dict
    from sqlalchemy.engine import make_url

    database_url = make_url(url)
    if database_url.get_backend_name() != "postgresql" or not database_url.database:
        raise DurabilityError("Configure an explicit PostgreSQL database URL.")
    params = conninfo_to_dict(
        database_url.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    if "service" in params or any(
        value != value.strip() or "\r" in value or "\n" in value for value in params.values()
    ):
        raise DurabilityError("Unsupported PostgreSQL service or connection parameter.")
    with TemporaryDirectory(prefix="animus-registry-") as directory:
        service_file = Path(directory) / "pg_service.conf"
        with open(service_file, "x", encoding="utf-8", opener=_private_file) as file:
            file.write("[animus_registry]\n")
            for key, value in params.items():
                file.write(f"{key}={value}\n")
        env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
        yield {**env, "PGSERVICEFILE": str(service_file)}


def _private_file(path: str, flags: int) -> int:
    return os.open(path, flags, 0o600)


def _run(command: list[str], env: dict[str, str]) -> bytes:
    try:
        return subprocess.run(
            command,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        ).stdout
    except FileNotFoundError as exc:
        raise DurabilityError(f"{command[0]} is required on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise DurabilityError(
            f"{command[0]} failed (exit {exc.returncode}). "
            "Check PostgreSQL client compatibility, permissions, and connectivity."
        ) from exc


def export_registry(url: str, archive: Path) -> None:
    """Create a custom-format snapshot without overwriting an existing archive."""
    if archive.exists():
        raise DurabilityError("Backup destination already exists.")
    with _service(url) as env, TemporaryDirectory(dir=archive.parent) as directory:
        snapshot = Path(directory) / "registry.dump"
        # The directory is private, and the published archive keeps mode 0600.
        snapshot.touch(mode=0o600)
        _run(
            [
                "pg_dump",
                "--no-password",
                "--format=custom",
                f"--file={snapshot}",
                "--dbname=service=animus_registry",
            ],
            env,
        )
        try:
            os.link(snapshot, archive)
        except FileExistsError as exc:
            raise DurabilityError("Backup destination already exists.") from exc


def restore_registry(url: str, archive: Path) -> None:
    """Restore a trusted archive to a dedicated empty database in one transaction."""
    with archive.open("rb") as file:
        if file.read(5) != b"PGDMP":
            raise DurabilityError("Expected a PostgreSQL custom-format backup archive.")

    with _service(url) as env:
        empty = _run(
            [
                "psql",
                "--no-psqlrc",
                "--no-password",
                "--tuples-only",
                "--no-align",
                "--set=ON_ERROR_STOP=1",
                "--dbname=service=animus_registry",
                f"--command={_EMPTY_DATABASE}",
            ],
            env,
        )
        if empty.strip() != b"t":
            raise DurabilityError("Restore target must be a dedicated empty database.")
        _run(
            [
                "pg_restore",
                "--no-password",
                "--single-transaction",
                "--no-owner",
                "--no-privileges",
                "--dbname=service=animus_registry",
                str(archive.resolve()),
            ],
            env,
        )

"""Read-only schema compatibility preflight. Never repairs a database at boot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class SchemaCompatibilityError(RuntimeError):
    """The database needs an explicit operator migration before use."""


@dataclass(frozen=True)
class SchemaReport:
    """Metadata-only result, safe to log without a connection URL or row payloads."""

    compatible: bool
    problems: tuple[str, ...]


def inspect_schema(engine: Any, metadata: Any) -> SchemaReport:
    """Check required columns and uniqueness in the existing schema."""
    from sqlalchemy import inspect

    inspector = inspect(engine)
    problems = []
    tables = set(inspector.get_table_names())
    for name, table in metadata.tables.items():
        if name not in tables:
            problems.append(f"Missing table: {name}")
            continue
        columns = {column["name"] for column in inspector.get_columns(name)}
        missing = set(table.columns.keys()) - columns
        if missing:
            problems.append(f"Missing columns in {name}: {', '.join(sorted(missing))}")
        if name == "event_ledger" and "event_type" in columns:
            problems.append(
                "Legacy Core ledger requires an explicit conversion; refusing mixed layouts."
            )
    if "object_registry" in tables:
        indexes = {index["name"]: index for index in inspector.get_indexes("object_registry")}
        for name, index_columns in (
            ("idx_object_id_version", ["object_id", "object_version"]),
            ("idx_object_current", ["object_id"]),
        ):
            index = indexes.get(name, {})
            if not index.get("unique") or index.get("column_names") != index_columns:
                problems.append(f"Missing unique index: {name}")
            elif name == "idx_object_current":
                predicate = index.get("dialect_options", {}).get(f"{engine.dialect.name}_where")
                normalized = (
                    "".join(str(predicate).lower().split()).replace("(", "").replace(")", "")
                )
                if normalized != "superseded_atisnull":
                    problems.append("Current-version index has an unexpected predicate.")
    return SchemaReport(not problems, tuple(problems))

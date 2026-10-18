"""Align the canonical registry with Core while preserving the Kernel ledger.

Revision ID: 002
Revises: 001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade migration-001 layouts only; fail before DDL for unknown state."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    registry_columns = {c["name"] for c in inspector.get_columns("object_registry")}
    ledger_columns = {c["name"] for c in inspector.get_columns("event_ledger")}
    expected_ledger = {
        "id",
        "event_kind",
        "occurred_at",
        "actor_refs",
        "object_refs",
        "event_data",
        "idempotency_key",
        "valid_from",
        "valid_to",
        "recorded_at",
    }
    expected_registry = {
        "id",
        "object_id",
        "object_version",
        "schema_id",
        "schema_version",
        "owner_id",
        "workspace_id",
        "subject_domain",
        "artifact_type",
        "cognitive_role",
        "workflow_status",
        "epistemic_status",
        "lifecycle_status",
        "storage_tier",
        "presentation",
        "security_class",
        "valid_from",
        "valid_to",
        "recorded_at",
        "superseded_at",
        "created_by",
        "trace_id",
        "content_sha256",
        "payload",
    }
    if ledger_columns != expected_ledger or registry_columns != expected_registry:
        raise RuntimeError(
            "Unknown or legacy Core schema. Back up and reconcile before migration 002."
        )
    if "outbox_entries" in inspector.get_table_names():
        raise RuntimeError("Unexpected existing outbox. Refusing to alter a mixed schema.")
    duplicates = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM (SELECT object_id FROM object_registry "
            "WHERE superseded_at IS NULL GROUP BY object_id HAVING COUNT(*) > 1) AS duplicates"
        )
    ).scalar_one()
    if duplicates:
        raise RuntimeError(
            "Duplicate current objects found. Resolve through reviewed recovery first."
        )

    # PostgreSQL already uses BIGSERIAL. SQLite only auto-generates IDs for
    # exactly INTEGER PRIMARY KEY; 001's BIGINT makes real inserts fail there.
    if bind.dialect.name == "sqlite":
        for name in ("object_registry", "event_ledger"):
            with op.batch_alter_table(name) as batch:
                batch.alter_column("id", existing_type=sa.BigInteger(), type_=sa.Integer())
    op.add_column(
        "object_registry", sa.Column("tags", sa.JSON(), nullable=False, server_default="[]")
    )
    op.create_index(
        "idx_object_current",
        "object_registry",
        ["object_id"],
        unique=True,
        sqlite_where=sa.text("superseded_at IS NULL"),
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_table(
        "outbox_entries",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True),
        sa.Column("entry_id", sa.String(128), nullable=False, unique=True),
        sa.Column("topic", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("claimed_by", sa.String(128)),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.String(512)),
    )


def downgrade() -> None:
    """Reverse only unused additions. Preserve populated evidence on refusal."""
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM outbox_entries")).scalar_one():
        raise RuntimeError("Outbox contains evidence; archive it before a reviewed downgrade.")
    registry = sa.table("object_registry", sa.column("tags", sa.JSON))
    if any(tags != [] for tags in bind.execute(sa.select(registry.c.tags)).scalars()):
        raise RuntimeError("Registry tags contain data; downgrade would lose metadata.")
    op.drop_table("outbox_entries")
    op.drop_index("idx_object_current", table_name="object_registry")
    with op.batch_alter_table("object_registry") as batch:
        batch.drop_column("tags")
    if bind.dialect.name == "sqlite":
        for name in ("object_registry", "event_ledger"):
            with op.batch_alter_table(name) as batch:
                batch.alter_column("id", existing_type=sa.Integer(), type_=sa.BigInteger())

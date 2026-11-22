"""Add the typed knowledge-edge table beside the canonical registry.

Revision ID: 003
Revises: 002
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_PREDICATES = (
    "DEPENDS_ON",
    "IMPLEMENTS",
    "MODIFIES",
    "CAUSED_BY",
    "RESOLVES",
    "VERIFIED_BY",
    "SUPERSEDES",
    "CONTRADICTS",
    "OWNED_BY",
    "RELATED_TO",
    "DERIVED_FROM",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "knowledge_edges" in inspector.get_table_names():
        return

    op.create_table(
        "knowledge_edges",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("edge_id", sa.String(128), nullable=False),
        sa.Column("edge_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("subject_id", sa.String(256), nullable=False),
        sa.Column("predicate", sa.String(64), nullable=False),
        sa.Column("object_id", sa.String(256), nullable=False),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("workspace_id", sa.String(128), nullable=False),
        sa.Column("subject_domain", sa.String(32), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False, server_default="knowledge_edge"),
        sa.Column("schema_id", sa.String(256), nullable=False, server_default="knowledge_edge"),
        sa.Column("schema_version", sa.String(32), nullable=False, server_default="1.0.0"),
        sa.Column("source_ref", sa.String(512), nullable=True),
        sa.Column("provenance", sa.String(64), nullable=False),
        sa.Column("evidence_grade", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("epistemic_status", sa.String(32), nullable=False),
        sa.Column("lifecycle_status", sa.String(32), nullable=False),
        sa.Column("security_class", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(256), nullable=False),
        sa.Column("metadata_json", sa.JSON, nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "predicate IN (" + ",".join("'" + value + "'" for value in _PREDICATES) + ")",
            name="ck_knowledge_edges_predicate",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_knowledge_edges_confidence",
        ),
    )
    op.create_index(
        "idx_edge_id_version",
        "knowledge_edges",
        ["edge_id", "edge_version"],
        unique=True,
    )
    op.create_index(
        "idx_edge_current",
        "knowledge_edges",
        ["edge_id"],
        unique=True,
        sqlite_where=sa.text("superseded_at IS NULL"),
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_index(
        "idx_edge_subject_predicate",
        "knowledge_edges",
        ["subject_id", "predicate", "superseded_at"],
    )
    op.create_index(
        "idx_edge_object_predicate",
        "knowledge_edges",
        ["object_id", "predicate", "superseded_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "knowledge_edges" not in inspector.get_table_names():
        return
    count = bind.execute(sa.text("SELECT COUNT(*) FROM knowledge_edges")).scalar_one()
    if count:
        raise RuntimeError("Knowledge edges contain evidence; archive before downgrade.")
    op.drop_index("idx_edge_object_predicate", table_name="knowledge_edges")
    op.drop_index("idx_edge_subject_predicate", table_name="knowledge_edges")
    op.drop_index("idx_edge_current", table_name="knowledge_edges")
    op.drop_index("idx_edge_id_version", table_name="knowledge_edges")
    op.drop_table("knowledge_edges")

"""Explicit capabilities for access to a shared object registry."""

from __future__ import annotations

from dataclasses import dataclass

HUNTER_ARTIFACT_TYPES = frozenset(
    {
        "monster",
        "special_encounter",
        "weapon_type",
        "exact_weapon",
        "hunting_horn_tree",
        "guide",
        "farm_route",
        "item_reference",
        "skill_reference",
    }
)


@dataclass(frozen=True, kw_only=True)
class ObjectScope:
    """Server-selected scope; never construct this from a chat request.

    Scope checks protect the application boundary, not against a process with
    direct database credentials. Only active current objects are visible;
    history additionally admits superseded versions of currently visible objects.
    """

    owner_id: str
    workspace_id: str
    subject_domain: str
    security_class: str
    schema_id: str
    artifact_types: frozenset[str]

    def __post_init__(self) -> None:
        for name in ("owner_id", "workspace_id", "subject_domain", "security_class", "schema_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"ObjectScope requires {name}.")
        object.__setattr__(self, "artifact_types", frozenset(self.artifact_types))
        if not self.artifact_types or any(
            not isinstance(v, str) or not v for v in self.artifact_types
        ):
            raise ValueError("ObjectScope requires explicit artifact types.")

    @classmethod
    def hunter(cls, owner_id: str) -> ObjectScope:
        """Fixed public Hunter domain, with deployment-selected owner identity."""
        return cls(
            owner_id=owner_id,
            workspace_id="hunter-os",
            subject_domain="monster_hunter_wilds",
            security_class="public",
            schema_id="hunter_os",
            artifact_types=HUNTER_ARTIFACT_TYPES,
        )

    def permits(self, record: object) -> bool:
        """Check a proposed write without coercing or repairing its metadata."""
        return (
            all(
                getattr(record, key) == getattr(self, key)
                for key in (
                    "owner_id",
                    "workspace_id",
                    "subject_domain",
                    "security_class",
                    "schema_id",
                )
            )
            and getattr(record, "artifact_type") in self.artifact_types
            and getattr(record, "lifecycle_status") == "active"
        )

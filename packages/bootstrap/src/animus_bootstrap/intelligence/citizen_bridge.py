"""Citizen Bridge — adapter exposing core citizen data to the bootstrap dashboard.

Uses lazy imports so bootstrap can run without the core package installed.
All core dependencies are imported inside methods, never at module level.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CitizenStatus:
    """Operational status of a single citizen."""

    name: str
    display_name: str
    state: str  # "idle" | "observing" | "proposing" | "error" | "unavailable"
    last_scan_at: str | None = None
    recent_proposals: int = 0
    total_proposals: int = 0
    description: str = ""


@dataclass
class CitizenProposalView:
    """Lightweight view of an ImprovementProposal for dashboard display."""

    id: str
    title: str
    problem: str = ""
    recommendation: str = ""
    confidence_score: float = 0.0
    confidence_label: str = ""
    estimated_effort_hours: float = 0.0
    affected_components: list[str] = field(default_factory=list)
    status: str = "draft"
    source_citizen: str = ""
    created_at: str = ""
    evidence_count: int = 0


class CitizenBridge:
    """Bridge between core Animus citizens and the bootstrap dashboard.

    Responsibilities:
    - Query core memory for citizen proposals
    - Surface citizen operational status
    - Provide approve / reject / commission hooks
    - Gracefully degrade when core is not installed

    Usage::

        bridge = CitizenBridge(runtime)
        proposals = bridge.list_proposals(limit=20)
        statuses = bridge.get_citizen_statuses()
    """

    _CITIZEN_REGISTRY: list[dict[str, str]] = [
        {
            "name": "architect",
            "display_name": "Architect",
            "description": (
                "Observes codebase, conversations, and evaluations to produce "
                "evidence-backed improvement proposals."
            ),
        },
        {
            "name": "conversation_designer",
            "display_name": "Conversation Designer",
            "description": (
                "Detects correction loops, vague requests, and repeated prompts "
                "in conversation logs."
            ),
        },
        {
            "name": "knowledge_curator",
            "display_name": "Knowledge Curator",
            "description": "Scans memory for stale references, contradictions, and orphan topics.",
        },
        {
            "name": "test_oracle",
            "display_name": "Test Oracle",
            "description": "Analyzes test suite health, coverage trends, and eval results.",
        },
        {
            "name": "session_steward",
            "display_name": "Session Steward",
            "description": "Audits session telemetry for policy inefficiencies and timer waste.",
        },
    ]

    def __init__(self, runtime: Any | None = None) -> None:
        self._runtime = runtime
        self._core_memory: Any | None = None
        self._core_available: bool | None = None
        self._proposal_cache: dict[str, CitizenProposalView] = {}
        self._cache_timestamp: float = 0.0
        self._cache_ttl_seconds: float = 30.0

    # ------------------------------------------------------------------
    # Core availability probe
    # ------------------------------------------------------------------

    def _check_core(self) -> bool:
        """Return True if animus-core is importable and memory is reachable."""
        if self._core_available is not None:
            return self._core_available
        try:
            import animus.memory  # noqa: F401

            self._core_available = True
        except ImportError:
            self._core_available = False
            logger.debug("animus-core not installed — citizen bridge in degraded mode")
        return self._core_available

    def _get_core_memory(self) -> Any | None:
        """Resolve the core MemoryLayer via the runtime or direct instantiation."""
        if self._core_memory is not None:
            return self._core_memory
        if not self._check_core():
            return None

        # Path A: runtime.memory_manager._backend is AnimusMemoryBackend
        if self._runtime is not None:
            mm = getattr(self._runtime, "memory_manager", None)
            if mm is not None:
                backend = getattr(mm, "_backend", None)
                if backend is not None:
                    # AnimusMemoryBackend exposes _core (MemoryLayer)
                    core = getattr(backend, "_core", None)
                    if core is not None:
                        self._core_memory = core
                        return core

        # Path B: direct instantiation from default data dir
        try:
            from animus.memory import MemoryLayer

            data_dir = Path.home() / ".local" / "share" / "animus" / "animus_memory"
            if data_dir.is_dir():
                self._core_memory = MemoryLayer(data_dir=data_dir, backend="auto")
                return self._core_memory
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_citizen_statuses(self) -> list[CitizenStatus]:
        """Return operational status for all registered citizens."""
        if not self._check_core():
            return [
                CitizenStatus(
                    name=c["name"],
                    display_name=c["display_name"],
                    state="unavailable",
                    description=c["description"],
                )
                for c in self._CITIZEN_REGISTRY
            ]

        # Query memory for recent citizen activity
        core = self._get_core_memory()
        statuses: list[CitizenStatus] = []

        for citizen_def in self._CITIZEN_REGISTRY:
            name = citizen_def["name"]
            display = citizen_def["display_name"]
            desc = citizen_def["description"]

            # Count proposals in memory for this citizen
            total = 0
            recent = 0
            last_scan: str | None = None

            if core is not None:
                try:
                    results = core.recall(
                        query=f"{name} proposal",
                        memory_type=self._resolve_memory_type("procedural"),
                        tags=[name, "proposal"],
                        limit=100,
                    )
                    total = len(results)
                    # Count proposals created in last 24h
                    now = datetime.now(UTC)
                    for mem in results:
                        meta = getattr(mem, "metadata", {}) or {}
                        created = meta.get("created_at", "")
                        if created:
                            try:
                                dt = datetime.fromisoformat(created)
                                if (now - dt).total_seconds() < 86400:
                                    recent += 1
                            except Exception:
                                pass
                        # Extract last scan timestamp from evidence
                        evidence = meta.get("evidence", [])
                        if evidence:
                            ts = evidence[-1].get("timestamp", "")
                            if ts and (last_scan is None or ts > last_scan):
                                last_scan = ts
                except Exception as e:
                    logger.debug("Citizen %s memory query failed: %s", name, e)

            # Determine state
            if total == 0:
                state = "idle"
            elif recent > 0:
                state = "proposing"
            else:
                state = "observing"

            statuses.append(
                CitizenStatus(
                    name=name,
                    display_name=display,
                    state=state,
                    last_scan_at=last_scan,
                    recent_proposals=recent,
                    total_proposals=total,
                    description=desc,
                )
            )

        return statuses

    def list_proposals(
        self,
        citizen_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[CitizenProposalView]:
        """Query core memory for citizen proposals.

        Args:
            citizen_name: Filter to a specific citizen (e.g. "architect").
            status: Filter by proposal status (e.g. "draft", "approved").
            limit: Maximum proposals to return.

        Returns:
            List of proposal views. Empty if core is unavailable.
        """
        if not self._check_core():
            return []

        core = self._get_core_memory()
        if core is None:
            return []

        # Build query
        tags = ["proposal"]
        if citizen_name:
            tags.append(citizen_name)

        try:
            results = core.recall(
                query="improvement proposal architect citizen",
                memory_type=self._resolve_memory_type("procedural"),
                tags=tags,
                limit=limit,
            )
        except Exception as e:
            logger.warning("Proposal query failed: %s", e)
            return []

        proposals: list[CitizenProposalView] = []
        for mem in results:
            meta = getattr(mem, "metadata", {}) or {}
            if not meta or not meta.get("id"):
                continue
            try:
                view = self._meta_to_proposal_view(meta)
                if status and view.status != status:
                    continue
                proposals.append(view)
            except Exception as e:
                logger.debug("Skipping malformed proposal memory: %s", e)
                continue

        # Sort by created_at desc
        proposals.sort(key=lambda p: p.created_at or "", reverse=True)
        return proposals

    def get_proposal(self, proposal_id: str) -> CitizenProposalView | None:
        """Fetch a single proposal by ID."""
        proposals = self.list_proposals(limit=500)
        for p in proposals:
            if p.id == proposal_id:
                return p
        return None

    def approve(self, proposal_id: str, actor: str = "dashboard") -> dict[str, Any]:
        """Mark a proposal as approved.

        Returns a dict with ``success``, ``proposal_id``, and ``timestamp``.
        This records the action but does not mutate core memory directly
        (memory entries are append-only). The event ledger becomes the
        source of truth for approval state.
        """
        return {
            "success": True,
            "proposal_id": proposal_id,
            "action": "approved",
            "actor": actor,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def reject(self, proposal_id: str, actor: str = "dashboard") -> dict[str, Any]:
        """Mark a proposal as rejected."""
        return {
            "success": True,
            "proposal_id": proposal_id,
            "action": "rejected",
            "actor": actor,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def commission(
        self,
        proposal_id: str,
        actor: str = "dashboard",
    ) -> dict[str, Any]:
        """Commission an approved proposal to Forge.

        If animus-core and Forge are available, delegates to
        ForgeCommissioner. Otherwise returns a simulated result.
        """
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            return {"success": False, "error": "Proposal not found"}

        if proposal.status != "approved":
            return {
                "success": False,
                "error": (
                    f"Proposal status is '{proposal.status}', must be 'approved' to commission"
                ),
            }

        if not self._check_core():
            return {
                "success": False,
                "error": "animus-core not available — cannot commission",
            }

        # Try to delegate to ForgeCommissioner
        try:
            from animus.citizens.commissioner import ForgeCommissioner
            from animus.citizens.proposal import ProposalStatus

            # Rebuild the full proposal from the view
            full_proposal = self._rebuild_proposal(proposal_id)
            if full_proposal is None:
                return {"success": False, "error": "Could not rebuild full proposal from memory"}

            # Must be approved
            full_proposal.status = ProposalStatus.APPROVED

            commissioner = ForgeCommissioner()
            result = commissioner.commission(full_proposal, auto_approve=False)

            return {
                "success": result.success,
                "proposal_id": proposal_id,
                "stage_reached": result.stage_reached,
                "tests_passed": result.tests_passed,
                "timestamp": datetime.now(UTC).isoformat(),
                "simulated": result.stage_reached == "simulated",
            }
        except Exception as e:
            logger.exception("Commission failed for proposal %s", proposal_id)
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_memory_type(self, type_str: str) -> Any:
        """Resolve a string memory type to the core MemoryType enum."""
        try:
            from animus.memory.types import MemoryType

            return MemoryType(type_str.upper())
        except Exception:
            return None

    @staticmethod
    def _meta_to_proposal_view(meta: dict[str, Any]) -> CitizenProposalView:
        """Convert proposal metadata dict to a lightweight view."""
        # The metadata may be the full proposal dict (from to_dict())
        # or a simpler dict depending on how it was stored.
        return CitizenProposalView(
            id=meta.get("id", "unknown"),
            title=meta.get("title", "Untitled Proposal"),
            problem=meta.get("problem", "")[:200],
            recommendation=meta.get("recommendation", "")[:200],
            confidence_score=meta.get("confidence_score", 0.0),
            confidence_label=meta.get("confidence_label", ""),
            estimated_effort_hours=meta.get("estimated_effort_hours", 0.0),
            affected_components=meta.get("affected_components", []),
            status=meta.get("status", "draft"),
            source_citizen=meta.get("source_citizen", ""),
            created_at=meta.get("created_at", ""),
            evidence_count=len(meta.get("evidence", [])),
        )

    def _rebuild_proposal(self, proposal_id: str) -> Any | None:
        """Fetch full proposal metadata from memory and rebuild the core dataclass."""
        core = self._get_core_memory()
        if core is None:
            return None
        try:
            results = core.recall(
                query=proposal_id,
                memory_type=self._resolve_memory_type("procedural"),
                tags=["proposal"],
                limit=10,
            )
            for mem in results:
                meta = getattr(mem, "metadata", {}) or {}
                if meta.get("id") == proposal_id:
                    from animus.citizens.proposal import ImprovementProposal

                    return ImprovementProposal.from_dict(meta)
        except Exception as e:
            logger.warning("Failed to rebuild proposal %s: %s", proposal_id, e)
        return None

    def summary(self) -> dict[str, Any]:
        """Return a summary of citizen activity for the dashboard home page."""
        statuses = self.get_citizen_statuses()
        proposals = self.list_proposals(limit=100)

        pending = [p for p in proposals if p.status in ("draft", "submitted", "pending_review")]
        approved = [p for p in proposals if p.status == "approved"]
        completed = [p for p in proposals if p.status in ("complete", "implemented")]

        return {
            "citizens_total": len(self._CITIZEN_REGISTRY),
            "citizens_active": sum(1 for s in statuses if s.state in ("observing", "proposing")),
            "proposals_total": len(proposals),
            "proposals_pending": len(pending),
            "proposals_approved": len(approved),
            "proposals_completed": len(completed),
            "core_available": self._check_core(),
        }

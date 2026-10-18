"""Citizen Commissioner — API-facing orchestrator for research missions.

The commissioner is a thin layer that exposes ``ResearchCitizen``
operations behind a stable interface.  It is instantiated in the FastAPI
lifespan and attached to ``api_state``.
"""

from __future__ import annotations

import logging
from typing import Any

from animus_forge.citizens.mission import MissionConfig, MissionRecord, MissionState
from animus_forge.citizens.research_citizen import ResearchCitizen

logger = logging.getLogger(__name__)


class CitizenCommissioner:
    """Orchestrates research missions via a ``ResearchCitizen``.

    Args:
        citizen: The underlying ResearchCitizen instance.
    """

    def __init__(self, citizen: ResearchCitizen):
        self.citizen = citizen

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def commission(self, config: MissionConfig) -> str:
        """Commission a new mission.

        Returns:
            Mission id.
        """
        return self.citizen.commission(config)

    def status(self, mission_id: str) -> dict[str, Any] | None:
        """Get mission status and latest evidence summary."""
        mission = self.citizen.get_mission(mission_id)
        if mission is None:
            return None
        return {
            "id": mission.id,
            "state": mission.state.value,
            "objective": mission.config.objective,
            "current_iteration": mission.current_iteration,
            "max_iterations": mission.config.max_iterations,
            "last_pass_rate": mission.last_pass_rate,
            "last_score_variance": mission.last_score_variance,
            "last_eval_run_id": mission.last_eval_run_id,
            "error": mission.error,
            "created_at": mission.created_at.isoformat(),
            "updated_at": mission.updated_at.isoformat(),
        }

    def run(self, mission_id: str) -> dict[str, Any]:
        """Run a single iteration of a mission.

        Returns:
            Status dict after the iteration.
        """
        mission = self.citizen.run_iteration(mission_id)
        return self._summarise(mission)

    def run_to_completion(self, mission_id: str) -> dict[str, Any]:
        """Run a mission until it reaches a terminal state.

        Returns:
            Final status dict.
        """
        mission = self.citizen.run_mission(mission_id)
        return self._summarise(mission)

    def list(self, state: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """List missions with optional state filter."""
        mission_state = MissionState(state) if state else None
        missions = self.citizen.list_missions(state=mission_state, limit=limit)
        return [self._summarise(m) for m in missions]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _summarise(self, mission: MissionRecord) -> dict[str, Any]:
        return {
            "id": mission.id,
            "state": mission.state.value,
            "current_iteration": mission.current_iteration,
            "max_iterations": mission.config.max_iterations,
            "last_pass_rate": mission.last_pass_rate,
            "last_score_variance": mission.last_score_variance,
            "error": mission.error,
        }

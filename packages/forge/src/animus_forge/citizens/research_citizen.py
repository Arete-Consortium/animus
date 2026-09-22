"""Research Citizen — bounded eval-gated autonomous mission runner.

A ResearchCitizen commissions missions, executes workflows, evaluates
results, and iterates until quality gates pass or max_iterations is
reached.  It NEVER modifies source code; it only mutates workflow
variables and retries.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from animus_forge.citizens.mission import MissionConfig, MissionRecord, MissionState
from animus_forge.citizens.store import MissionStore
from animus_forge.evaluation.loader import SuiteLoader
from animus_forge.evaluation.runner import EvalRunner
from animus_forge.intelligence.evidence_bridge import EvidenceBridge

logger = logging.getLogger(__name__)


class ResearchCitizen:
    """Executes research missions with eval-gated iteration.

    Args:
        mission_store: Persistent mission storage.
        workflow_engine: Object with ``load_workflow(name)`` and
            ``execute_workflow(workflow)`` methods.
        eval_runner: EvalRunner for running eval suites.
        eval_loader: SuiteLoader for loading eval suites by name.
        evidence_bridge: Bridge that closes eval → memory loop.
    """

    def __init__(
        self,
        mission_store: MissionStore,
        workflow_engine: Any,
        eval_runner: EvalRunner,
        eval_loader: SuiteLoader,
        evidence_bridge: EvidenceBridge,
        arete_guard: Any | None = None,
    ):
        self.mission_store = mission_store
        self.workflow_engine = workflow_engine
        self.eval_runner = eval_runner
        self.eval_loader = eval_loader
        self.evidence_bridge = evidence_bridge
        self.arete_guard = arete_guard

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def commission(self, config: MissionConfig) -> str:
        """Create a new mission and persist it.

        Returns:
            The mission id.
        """
        mission_id = str(uuid.uuid4())
        mission = MissionRecord(
            id=mission_id,
            config=config,
            state=MissionState.PENDING,
        )
        self.mission_store.create(mission)
        logger.info("Commissioned mission %s: %s", mission_id[:8], config.objective)
        return mission_id

    def run_iteration(self, mission_id: str) -> MissionRecord:
        """Execute a single iteration of the mission loop.

        1. Load mission and workflow.
        2. Execute workflow.
        3. Run eval suite.
        4. Bridge evidence.
        5. Update mission state.

        Returns:
            Updated mission record.
        """
        mission = self.mission_store.get(mission_id)
        if mission is None:
            raise ValueError(f"Mission {mission_id} not found")

        mission.state = MissionState.RUNNING
        mission.current_iteration += 1
        self.mission_store.update(mission)

        try:
            # 1. Load workflow and eval suite
            workflow = self.workflow_engine.load_workflow(mission.config.workflow_template)
            if workflow is None:
                raise FileNotFoundError(
                    f"Workflow template '{mission.config.workflow_template}' not found"
                )
            suite = self.eval_loader.load_suite(mission.config.eval_suite)

            # Inject mission variables into workflow
            workflow.variables["objective"] = mission.config.objective
            temp = mission.metadata.get("temperature", 0.7)
            workflow.variables["temperature"] = temp

            # Guard check before execution
            if self.arete_guard is not None:
                self.arete_guard.check(
                    workflow_name=mission.config.workflow_template,
                    mission_id=mission_id,
                )

            # 2. Execute workflow
            wf_result = self.workflow_engine.execute_workflow(workflow)
            workflow_id = wf_result.workflow_id

            # 3. Run evaluation
            eval_result = self.eval_runner.run(suite)

            # 4. Bridge evidence
            evidence = self.evidence_bridge.on_eval_complete(
                eval_result,
                workflow_id=workflow_id,
                mission_id=mission_id,
                agent_role="research_citizen",
                model=None,
                run_mode="live",
            )

            # 5. Update mission with results
            mission.last_eval_run_id = evidence.run_id
            mission.last_pass_rate = evidence.pass_rate
            mission.last_score_variance = evidence.score_variance

            if (
                evidence.pass_rate >= mission.config.min_pass_rate
                and evidence.score_variance <= mission.config.max_variance
            ):
                mission.state = MissionState.COMPLETED
                logger.info(
                    "Mission %s COMPLETED after %d iterations (pass_rate=%.2f, variance=%.3f)",
                    mission_id[:8],
                    mission.current_iteration,
                    evidence.pass_rate,
                    evidence.score_variance,
                )
            elif mission.current_iteration < mission.config.max_iterations:
                mission.state = MissionState.NEEDS_RETRY
                # Mutate workflow variables for next iteration
                mission.metadata["temperature"] = self._escalate_temperature(temp)
                logger.info(
                    "Mission %s needs retry (%d/%d): pass_rate=%.2f, variance=%.3f",
                    mission_id[:8],
                    mission.current_iteration,
                    mission.config.max_iterations,
                    evidence.pass_rate,
                    evidence.score_variance,
                )
            else:
                mission.state = MissionState.FAILED
                mission.error = (
                    f"Max iterations ({mission.config.max_iterations}) reached. "
                    f"Final pass_rate={evidence.pass_rate:.2f}, variance={evidence.score_variance:.3f}"
                )
                logger.warning("Mission %s FAILED: %s", mission_id[:8], mission.error)

        except Exception as e:
            mission.state = MissionState.FAILED
            mission.error = str(e)
            logger.exception("Mission %s iteration failed", mission_id[:8])

        self.mission_store.update(mission)
        return mission

    def run_mission(self, mission_id: str) -> MissionRecord:
        """Run the full mission loop until terminal state.

        Returns:
            Final mission record.
        """
        mission = self.mission_store.get(mission_id)
        if mission is None:
            raise ValueError(f"Mission {mission_id} not found")

        while mission.state not in (
            MissionState.COMPLETED,
            MissionState.FAILED,
        ):
            mission = self.run_iteration(mission_id)

        return mission

    def get_mission(self, mission_id: str) -> MissionRecord | None:
        """Fetch a mission record by id."""
        return self.mission_store.get(mission_id)

    def list_missions(
        self, state: MissionState | None = None, limit: int = 20
    ) -> list[MissionRecord]:
        """List missions, optionally filtered by state."""
        if state is not None:
            return self.mission_store.list_by_state(state, limit)
        return self.mission_store.list_all(limit)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _escalate_temperature(current: float) -> float:
        """Escalate temperature on retry to increase output diversity."""
        # Cap at 1.0 to avoid excessive randomness
        return min(1.0, round(current + 0.1, 2))

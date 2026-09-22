"""End-to-end test: autonomous engineering mission on a fixture repository.

This test proves the Phase 4 pipeline:

    Mission → Planner → Tasks → Builder → Reviewer → Evidence

No real LLM provider is required.  The citizens use deterministic logic.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from animus_forge.citizens.builder import BuilderCitizen
from animus_forge.citizens.planner import PlannerCitizen
from animus_forge.citizens.reviewer import ReviewerCitizen
from animus_forge.missions.domain import (
    Mission,
    MissionStatus,
    Task,
    TaskContext,
    TaskStatus,
)
from animus_forge.missions.store import MissionLedger
from animus_forge.missions.transitions import TransitionError
from animus_forge.state.backends import SQLiteBackend


@pytest.fixture()
def ledger():
    backend = SQLiteBackend(":memory:")
    return MissionLedger(backend)


@pytest.fixture()
def sample_mission():
    return Mission(
        repository="eval_suites/autonomous_engineering/fixtures/python_service",
        objective="Fix off-by-one pagination bug",
        risk_class="medium",
        priority=80,
        max_cost_usd=Decimal("5.00"),
        max_runtime_seconds=1800,
        max_changed_files=4,
        allowed_paths=["src/**/*.py"],
        protected_paths=["tests/**", "pyproject.toml"],
        acceptance_criteria=[
            "regression test added",
            "original failure reproduced",
            "full suite passes",
        ],
    )


class TestE2EAutonomousEngineering:
    def test_mission_lifecycle(self, ledger, sample_mission):
        """Mission transitions through all valid states to completion."""
        # 1. Intake: create mission
        ledger.create_mission(sample_mission)
        m = ledger.get_mission(sample_mission.mission_id)
        assert m.status == MissionStatus.PROPOSED

        # 2. Transition to READY
        m = ledger.transition_mission(m.mission_id, MissionStatus.READY)
        assert m.status == MissionStatus.READY

        # 3. Planner decomposes
        planner = PlannerCitizen()
        plan_task = Task(
            mission_id=m.mission_id,
            citizen_role="planner",
            description=f"Plan: {m.objective}",
        )
        ctx = TaskContext(
            mission_objective=m.objective,
            task_description=plan_task.description,
            repository=m.repository,
            allowed_paths=m.allowed_paths,
            protected_paths=m.protected_paths,
        )
        plan_output = planner.run(plan_task, ctx)
        assert plan_output.status == "completed"
        assert len(plan_output.evidence) > 0

        # 4. Create tasks from plan
        plan_tasks = planner._decompose(m.objective)
        tasks = planner.create_task_graph(m.mission_id, plan_tasks)
        for t in tasks:
            ledger.create_task(t)

        # 5. Transition mission to RUNNING
        m = ledger.transition_mission(m.mission_id, MissionStatus.RUNNING)

        # 6. Builder executes
        builder_task = next(t for t in tasks if t.citizen_role == "builder")
        ledger.transition_task(builder_task.task_id, TaskStatus.READY)
        ledger.transition_task(builder_task.task_id, TaskStatus.LEASED)
        ledger.transition_task(builder_task.task_id, TaskStatus.RUNNING)

        builder = BuilderCitizen()
        build_ctx = TaskContext(
            mission_objective=m.objective,
            task_description=builder_task.description,
            repository=m.repository,
            allowed_paths=m.allowed_paths,
            protected_paths=m.protected_paths,
            relevant_files=["src/python_service/pagination.py"],
        )
        build_output = builder.run(builder_task, build_ctx)
        assert build_output.status == "completed"
        assert len(build_output.changed_files) > 0

        ledger.transition_task(builder_task.task_id, TaskStatus.COMPLETED)

        # 7. Reviewer evaluates
        reviewer_task = next(t for t in tasks if t.citizen_role == "reviewer")
        ledger.transition_task(reviewer_task.task_id, TaskStatus.READY)
        ledger.transition_task(reviewer_task.task_id, TaskStatus.LEASED)
        ledger.transition_task(reviewer_task.task_id, TaskStatus.RUNNING)

        reviewer = ReviewerCitizen()
        review_ctx = TaskContext(
            mission_objective=m.objective,
            task_description=reviewer_task.description,
            repository=m.repository,
            prior_attempts=build_output.evidence,
            protected_paths=m.protected_paths,
        )
        review_output = reviewer.run(reviewer_task, review_ctx)
        assert review_output.status in {"completed", "needs_repair"}

        if review_output.status == "completed":
            ledger.transition_task(reviewer_task.task_id, TaskStatus.COMPLETED)
            m = ledger.transition_mission(m.mission_id, MissionStatus.REVIEW)
            m = ledger.transition_mission(m.mission_id, MissionStatus.COMPLETED)
        else:
            # Repair loop: review rejected, go back to running via REVIEW
            ledger.transition_task(reviewer_task.task_id, TaskStatus.COMPLETED)
            m = ledger.transition_mission(m.mission_id, MissionStatus.REVIEW)
            m = ledger.transition_mission(m.mission_id, MissionStatus.RUNNING)
            repair_task = Task(
                mission_id=m.mission_id,
                citizen_role="builder",
                description=f"Repair: {review_output.risks[0]['description']}",
                dependencies=[reviewer_task.task_id],
            )
            ledger.create_task(repair_task)
            ledger.transition_task(repair_task.task_id, TaskStatus.READY)

        # 8. Verify final state
        final_mission = ledger.get_mission(sample_mission.mission_id)
        all_tasks = ledger.list_tasks_for_mission(final_mission.mission_id)
        completed_tasks = [t for t in all_tasks if t.status == TaskStatus.COMPLETED]

        # At least the builder task completed
        assert len(completed_tasks) >= 1
        # Mission never entered a forbidden state
        assert final_mission.status in {
            MissionStatus.COMPLETED,
            MissionStatus.RUNNING,
            MissionStatus.REVIEW,
        }

    def test_protected_path_violation_blocked(self, ledger, sample_mission):
        """Builder must fail when attempting to modify a protected path."""
        ledger.create_mission(sample_mission)
        m = ledger.get_mission(sample_mission.mission_id)
        m = ledger.transition_mission(m.mission_id, MissionStatus.READY)
        m = ledger.transition_mission(m.mission_id, MissionStatus.RUNNING)

        builder = BuilderCitizen()
        task = Task(
            mission_id=m.mission_id,
            citizen_role="builder",
            description="Fix bug",
        )
        ctx = TaskContext(
            mission_objective=m.objective,
            task_description=task.description,
            repository=m.repository,
            allowed_paths=["src/**/*.py"],
            protected_paths=["tests/**"],
            relevant_files=["tests/test_pagination.py"],  # protected
        )
        output = builder.run(task, ctx)
        assert output.status == "failed"
        assert "tests/test_pagination.py" in str(output.summary)

    def test_reviewer_detects_scope_creep(self, ledger, sample_mission):
        """Reviewer rejects when too many files are changed."""
        reviewer = ReviewerCitizen()
        task = Task(
            mission_id=sample_mission.mission_id,
            citizen_role="reviewer",
            description="Review",
        )
        files = [f"src/file_{i}.py" for i in range(20)]
        ctx = TaskContext(
            mission_objective="Fix bug",
            task_description="Review",
            repository="r",
            prior_attempts=[{"type": "build", "changed_files": files}],
            protected_paths=[],
        )
        output = reviewer.run(task, ctx)
        assert output.status == "needs_repair"
        assert any("Too many files" in r["description"] for r in output.risks)

    def test_invalid_transition_blocked(self, ledger, sample_mission):
        """State machine prevents illegal transitions."""
        ledger.create_mission(sample_mission)
        with pytest.raises(TransitionError):
            ledger.transition_mission(sample_mission.mission_id, MissionStatus.COMPLETED)

    def test_task_dependencies_enforced(self, ledger, sample_mission):
        """A task cannot start before its dependencies complete."""
        ledger.create_mission(sample_mission)
        dep = Task(
            mission_id=sample_mission.mission_id,
            citizen_role="builder",
            description="Dep",
        )
        task = Task(
            mission_id=sample_mission.mission_id,
            citizen_role="reviewer",
            description="Review",
            dependencies=[dep.task_id],
        )
        ledger.create_task(dep)
        ledger.create_task(task)
        ledger.transition_task(dep.task_id, TaskStatus.READY)
        ledger.transition_task(task.task_id, TaskStatus.READY)

        # dep is ready but not completed, so task should not be ready to start
        ready = ledger.get_ready_tasks(sample_mission.mission_id)
        assert len(ready) == 1
        assert ready[0].task_id == dep.task_id

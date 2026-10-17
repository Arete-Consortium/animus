"""Self-improvement tools — analyze behavior, propose and apply improvements."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from animus_bootstrap.gateway.cognitive import CognitiveBackend
    from animus_bootstrap.intelligence.tools.builtin.improvement_store import ImprovementStore
    from animus_bootstrap.intelligence.tools.builtin.sandbox import ImprovementSandbox
    from animus_bootstrap.intelligence.tools.executor import ToolExecutor

from animus_bootstrap.intelligence.tools.executor import ToolDefinition

logger = logging.getLogger(__name__)

# Log of improvement proposals for audit trail (in-memory fallback)
_improvement_log: list[dict] = []

# Persistent store (set at runtime)
_improvement_store: ImprovementStore | None = None

# Sandbox executor (set at runtime)
_sandbox: ImprovementSandbox | None = None

# Identity manager (set at runtime)
_identity_manager = None


def set_improvement_store(store: ImprovementStore | None) -> None:
    """Wire the persistent improvement store."""
    global _improvement_store  # noqa: PLW0603
    _improvement_store = store


def set_sandbox(sandbox: ImprovementSandbox | None) -> None:
    """Wire the improvement sandbox."""
    global _sandbox  # noqa: PLW0603
    _sandbox = sandbox


def set_self_improve_identity(identity_manager: object | None) -> None:
    """Wire the identity manager for identity file changes."""
    global _identity_manager  # noqa: PLW0603
    _identity_manager = identity_manager


def get_improvement_log() -> list[dict]:
    """Return the improvement log (for testing/inspection)."""
    if _improvement_store is not None:
        return _improvement_store.list_all()
    return list(_improvement_log)


def clear_improvement_log() -> None:
    """Clear the in-memory improvement log."""
    _improvement_log.clear()


# References set at runtime
_tool_executor: ToolExecutor | None = None
_cognitive_backend: CognitiveBackend | None = None


def set_self_improve_deps(
    tool_executor: ToolExecutor, cognitive_backend: CognitiveBackend | None
) -> None:
    """Wire live dependencies for self-improvement tools."""
    global _tool_executor, _cognitive_backend  # noqa: PLW0603
    _tool_executor = tool_executor
    _cognitive_backend = cognitive_backend


async def _analyze_behavior(focus: str = "all") -> str:
    """Analyze recent tool execution history to identify patterns and issues.

    ``focus`` can be: "all", "errors", "slow", "frequent".
    """
    if _tool_executor is None:
        return "No tool executor available — cannot analyze behavior"

    history = _tool_executor.get_history(limit=100)
    if not history:
        return "No tool execution history to analyze"

    total = len(history)
    failures = [r for r in history if not r.success]
    slow = [r for r in history if r.duration_ms > 5000]
    tool_counts: dict[str, int] = {}
    for r in history:
        tool_counts[r.tool_name] = tool_counts.get(r.tool_name, 0) + 1

    report_lines = [f"Behavior Analysis ({total} recent executions):"]

    if focus in ("all", "errors"):
        report_lines.append(f"\nErrors: {len(failures)}/{total}")
        for f in failures[:10]:
            report_lines.append(f"  - {f.tool_name}: {f.output[:100]}")

    if focus in ("all", "slow"):
        report_lines.append(f"\nSlow executions (>5s): {len(slow)}")
        for s in slow[:10]:
            report_lines.append(f"  - {s.tool_name}: {s.duration_ms:.0f}ms")

    if focus in ("all", "frequent"):
        sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)
        report_lines.append("\nTool usage frequency:")
        for name, count in sorted_tools[:10]:
            report_lines.append(f"  - {name}: {count} calls")

    avg_ms = sum(r.duration_ms for r in history) / total if total else 0
    report_lines.append(f"\nAverage execution time: {avg_ms:.0f}ms")
    report_lines.append(f"Success rate: {(total - len(failures)) / total * 100:.1f}%")

    return "\n".join(report_lines)


async def _propose_improvement(area: str, description: str) -> str:
    """Generate an improvement proposal using the cognitive backend.

    ``area`` identifies what to improve (e.g. "tool:web_search", "prompt",
    "workflow").  ``description`` explains the problem or desired enhancement.
    """
    proposal = {
        "area": area,
        "description": description,
        "status": "proposed",
        "timestamp": datetime.now(UTC).isoformat(),
        "analysis": None,
        "patch": None,
    }

    # Use cognitive backend if available to generate analysis
    if _cognitive_backend is not None:
        try:
            messages = [
                {
                    "role": "user",
                    "content": (
                        f"You are analyzing the Animus AI system for self-improvement.\n"
                        f"Area: {area}\n"
                        f"Issue: {description}\n\n"
                        f"Propose a specific, actionable improvement. "
                        f"Include what code to change and why. Be concise."
                    ),
                }
            ]
            response = await _cognitive_backend.generate_response(
                messages=messages,
                system_prompt="You are a code improvement analyst. Be specific and actionable.",
                max_tokens=1024,
            )
            proposal["analysis"] = response
        except (ConnectionError, TimeoutError, RuntimeError, ValueError) as exc:
            proposal["analysis"] = f"Cognitive analysis failed: {exc}"
            logger.warning("Self-improvement analysis failed: %s", exc)
    else:
        proposal["analysis"] = (
            f"No cognitive backend available. Manual review needed for: {area} — {description}"
        )

    # Persist to store or in-memory log
    if _improvement_store is not None:
        proposal["id"] = _improvement_store.save(proposal)
    else:
        proposal["id"] = len(_improvement_log) + 1
        _improvement_log.append(proposal)

    logger.info("Improvement proposal #%d: %s", proposal["id"], area)

    output = f"Improvement Proposal #{proposal['id']}\n"
    output += f"Area: {area}\n"
    output += "Status: proposed\n"
    output += f"Analysis:\n{proposal['analysis']}"
    return output


async def _apply_improvement(
    proposal_id: int,
    confirm: bool = False,
    yaml_path: str = "",
    value: str = "",
    identity_file: str = "",
    identity_section: str = "",
    identity_content: str = "",
) -> str:
    """Apply a previously proposed improvement.

    If ``confirm`` is False (default), shows what would be done.
    If ``confirm`` is True, executes the improvement via sandbox.

    Two execution modes:
    - Config change: provide yaml_path and value
    - Identity update: provide identity_file, identity_section, identity_content
    """
    # Look up proposal from store or in-memory log
    if _improvement_store is not None:
        proposal = _improvement_store.get(proposal_id)
    else:
        matching = [p for p in _improvement_log if p["id"] == proposal_id]
        proposal = matching[0] if matching else None

    if proposal is None:
        return f"Proposal #{proposal_id} not found"

    if proposal["status"] == "applied":
        return f"Proposal #{proposal_id} has already been applied"

    if not confirm:
        preview = (
            f"Proposal #{proposal_id} ready for application.\n"
            f"Area: {proposal['area']}\n"
            f"Analysis: {proposal['analysis']}\n\n"
        )
        if yaml_path:
            preview += f"Will change config: {yaml_path} = {value}\n"
        elif identity_file:
            preview += f"Will append to {identity_file} [{identity_section}]: {identity_content}\n"
        preview += "Call apply_improvement with confirm=true to execute."
        return preview

    # Capture baseline metrics before applying
    baseline = await _capture_metrics()
    if _improvement_store is not None and baseline:
        _improvement_store.set_baseline_metrics(proposal_id, json.dumps(baseline))

    # Execute via sandbox if available
    result_detail = ""
    if _sandbox is not None:
        if yaml_path and value:
            # Parse value from string
            parsed_value: object = value
            try:
                parsed_value = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                pass  # Keep as string
            result = _sandbox.apply_config_change(proposal_id, yaml_path, parsed_value)
            result_detail = f"Config change: {result}"
        elif identity_file and identity_content:
            result = _sandbox.apply_identity_append(
                proposal_id,
                identity_file,
                identity_section or "Self-Improvement",
                identity_content,
                identity_manager=_identity_manager,
            )
            result_detail = f"Identity update: {result}"
        else:
            result_detail = "No executable change specified (provide yaml_path or identity_file)"

    applied_at = datetime.now(UTC).isoformat()
    if _improvement_store is not None:
        _improvement_store.update_status(proposal_id, "applied", applied_at)
    else:
        proposal["status"] = "applied"
        proposal["applied_at"] = applied_at

    logger.info("Improvement proposal #%d applied", proposal_id)
    output = f"Proposal #{proposal_id} applied at {applied_at}.\n"
    if result_detail:
        output += f"{result_detail}\n"
    output += "Baseline metrics captured. Run measure_impact after some time to evaluate."
    return output


async def _list_improvements(status: str = "all") -> str:
    """List improvement proposals, optionally filtered by status."""
    if _improvement_store is not None:
        filtered = _improvement_store.list_all(status=status)
    else:
        filtered = _improvement_log
        if status != "all":
            filtered = [p for p in _improvement_log if p["status"] == status]

    if not filtered:
        if status == "all":
            return "No improvement proposals recorded"
        return f"No proposals with status '{status}'"

    lines = [f"Improvement Proposals ({len(filtered)}):"]
    for p in filtered:
        lines.append(f"  #{p['id']} [{p['status']}] {p['area']}: {p['description'][:80]}")

    return "\n".join(lines)


async def _capture_metrics() -> dict | None:
    """Capture current system metrics for before/after comparison."""
    if _tool_executor is None:
        return None

    history = _tool_executor.get_history(limit=100)
    if not history:
        return None

    total = len(history)
    failures = sum(1 for r in history if not r.success)
    avg_ms = sum(r.duration_ms for r in history) / total if total else 0

    # Per-tool breakdown
    tool_stats: dict[str, dict] = {}
    for r in history:
        if r.tool_name not in tool_stats:
            tool_stats[r.tool_name] = {"total": 0, "failures": 0, "total_ms": 0.0}
        s = tool_stats[r.tool_name]
        s["total"] += 1
        s["total_ms"] += r.duration_ms
        if not r.success:
            s["failures"] += 1

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_executions": total,
        "failure_count": failures,
        "failure_rate": failures / total if total else 0,
        "avg_duration_ms": avg_ms,
        "tool_stats": {
            name: {
                "failure_rate": s["failures"] / s["total"] if s["total"] else 0,
                "avg_ms": s["total_ms"] / s["total"] if s["total"] else 0,
            }
            for name, s in tool_stats.items()
        },
    }


async def _measure_impact(proposal_id: int) -> str:
    """Measure the impact of an applied improvement by comparing before/after metrics.

    Computes an impact score from -100 (regression) to +100 (major improvement).
    """
    if _improvement_store is None:
        return "No improvement store available"

    proposal = _improvement_store.get(proposal_id)
    if proposal is None:
        return f"Proposal #{proposal_id} not found"
    if proposal["status"] != "applied":
        return f"Proposal #{proposal_id} has not been applied yet (status: {proposal['status']})"

    # Capture current metrics
    post = await _capture_metrics()
    if post is None:
        return "Cannot capture metrics — no tool executor or history"

    # Load baseline
    baseline_raw = proposal.get("baseline_metrics")
    if not baseline_raw:
        # No baseline — just record post metrics with neutral score
        _improvement_store.set_post_metrics(proposal_id, json.dumps(post), 0.0)
        return (
            f"Proposal #{proposal_id}: no baseline metrics "
            f"(applied before measurement was added).\n"
            f"Current metrics recorded for future comparison."
        )

    try:
        baseline = json.loads(baseline_raw)
    except (json.JSONDecodeError, TypeError):
        _improvement_store.set_post_metrics(proposal_id, json.dumps(post), 0.0)
        return f"Proposal #{proposal_id}: baseline metrics corrupted. Current metrics recorded."

    # Compute impact score
    score = _compute_impact_score(baseline, post, proposal.get("area", ""))
    _improvement_store.set_post_metrics(proposal_id, json.dumps(post), score)

    # Format report
    lines = [f"Impact Report — Proposal #{proposal_id}"]
    lines.append(f"Area: {proposal['area']}")
    lines.append(f"Impact Score: {score:+.1f} / 100")
    lines.append("")

    # Failure rate comparison
    b_rate = baseline.get("failure_rate", 0)
    p_rate = post.get("failure_rate", 0)
    direction = "improved" if p_rate < b_rate else ("regressed" if p_rate > b_rate else "unchanged")
    lines.append(f"Failure rate: {b_rate:.1%} → {p_rate:.1%} ({direction})")

    # Latency comparison
    b_ms = baseline.get("avg_duration_ms", 0)
    p_ms = post.get("avg_duration_ms", 0)
    direction = "improved" if p_ms < b_ms else ("regressed" if p_ms > b_ms else "unchanged")
    lines.append(f"Avg latency: {b_ms:.0f}ms → {p_ms:.0f}ms ({direction})")

    if score < -10:
        lines.append("\n⚠ Regression detected. Consider rolling back this change.")
    elif score > 10:
        lines.append("\n✓ Improvement confirmed.")

    return "\n".join(lines)


def _compute_impact_score(baseline: dict, post: dict, area: str) -> float:
    """Compute impact score from -100 to +100.

    Weights:
    - Failure rate improvement: 60% weight
    - Latency improvement: 40% weight
    - Per-tool improvement for targeted area: bonus
    """
    score = 0.0

    # Overall failure rate (60% weight, max 60 points)
    b_rate = baseline.get("failure_rate", 0)
    p_rate = post.get("failure_rate", 0)
    if b_rate > 0:
        rate_change = (b_rate - p_rate) / b_rate  # positive = improvement
        score += rate_change * 60
    elif p_rate == 0:
        score += 10  # Both zero = stable, small positive

    # Latency improvement (40% weight, max 40 points)
    b_ms = baseline.get("avg_duration_ms", 1)
    p_ms = post.get("avg_duration_ms", 1)
    if b_ms > 0:
        latency_change = (b_ms - p_ms) / b_ms  # positive = faster
        score += latency_change * 40

    # Clamp to [-100, 100]
    return max(-100.0, min(100.0, score))


async def _rollback_improvement(proposal_id: int) -> str:
    """Rollback an applied improvement by restoring from backup."""
    if _sandbox is None:
        return "No sandbox available — cannot rollback"
    if _improvement_store is None:
        return "No improvement store available"

    proposal = _improvement_store.get(proposal_id)
    if proposal is None:
        return f"Proposal #{proposal_id} not found"
    if proposal["status"] != "applied":
        return f"Proposal #{proposal_id} is not applied (status: {proposal['status']})"

    backups = _sandbox.list_backups()
    matching = [b for b in backups if b["proposal_id"] == proposal_id]
    if not matching:
        return f"No backup found for proposal #{proposal_id}"

    results = []
    for backup in matching:
        # Determine the original file path from the backup name
        original_name = backup["filename"].replace(f"proposal_{proposal_id}_", "", 1)
        # Try config path first, then data dir

        if _sandbox._config_path and _sandbox._config_path.name == original_name:
            result = _sandbox.rollback(proposal_id, _sandbox._config_path)
        else:
            result = _sandbox.rollback(proposal_id, _sandbox._data_dir / original_name)
        results.append(result)

    _improvement_store.update_status(proposal_id, "rolled_back")
    return f"Proposal #{proposal_id} rolled back. {len(results)} file(s) restored."


async def _self_improve_loop(area: str, description: str) -> str:
    """Run a multi-turn self-improvement loop.

    Steps:
    1. Analyze recent behavior for context
    2. Propose an improvement using the cognitive backend
    3. Report findings for human review

    The loop does NOT auto-apply patches — it stops after proposal
    so a human can review and approve via apply_improvement.
    """
    steps: list[str] = []

    # Step 1: Analyze
    steps.append("=== Step 1: Behavior Analysis ===")
    analysis = await _analyze_behavior(focus="all")
    steps.append(analysis)

    # Step 2: Propose
    steps.append("\n=== Step 2: Improvement Proposal ===")
    proposal_result = await _propose_improvement(area, description)
    steps.append(proposal_result)

    # Step 3: Report
    steps.append("\n=== Step 3: Summary ===")
    log = get_improvement_log()
    if log:
        latest = log[-1]
        steps.append(f"Proposal #{latest['id']} created for area '{area}'.")
        steps.append(f"Status: {latest['status']}")
        if latest.get("analysis"):
            steps.append(f"Analysis preview: {latest['analysis'][:200]}...")
        steps.append(
            f"\nTo apply: call apply_improvement with proposal_id={latest['id']} and confirm=true."
        )
    else:
        steps.append("No proposal was created.")

    return "\n".join(steps)


def get_self_improve_tools() -> list[ToolDefinition]:
    """Return self-improvement tool definitions."""
    return [
        ToolDefinition(
            name="analyze_behavior",
            description=(
                "Analyze recent tool execution history to identify patterns, "
                "errors, slow operations, and usage frequency."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": "Focus area: 'all', 'errors', 'slow', 'frequent'.",
                        "default": "all",
                    },
                },
            },
            handler=_analyze_behavior,
            category="self_improvement",
        ),
        ToolDefinition(
            name="propose_improvement",
            description=(
                "Generate an improvement proposal for a specific area. "
                "Uses the cognitive backend to analyze the issue and suggest changes."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "area": {
                        "type": "string",
                        "description": (
                            "What to improve (e.g. 'tool:web_search', 'prompt', 'workflow')."
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of the problem or desired enhancement.",
                    },
                },
                "required": ["area", "description"],
            },
            handler=_propose_improvement,
            category="self_improvement",
            permission="approve",
        ),
        ToolDefinition(
            name="apply_improvement",
            description=(
                "Apply a previously proposed improvement via sandbox. "
                "Supports config changes (yaml_path+value) and identity updates "
                "(identity_file+identity_section+identity_content). "
                "Creates backups and captures baseline metrics."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "proposal_id": {
                        "type": "integer",
                        "description": "ID of the improvement proposal to apply.",
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "Set to true to execute the improvement.",
                        "default": False,
                    },
                    "yaml_path": {
                        "type": "string",
                        "description": (
                            "Dot-separated config path (e.g. 'intelligence.tool_timeout_seconds')."
                        ),
                        "default": "",
                    },
                    "value": {
                        "type": "string",
                        "description": "New value for the config key (JSON-parsed if possible).",
                        "default": "",
                    },
                    "identity_file": {
                        "type": "string",
                        "description": "Identity file to update (e.g. 'LEARNED.md').",
                        "default": "",
                    },
                    "identity_section": {
                        "type": "string",
                        "description": "Section heading for the identity entry.",
                        "default": "",
                    },
                    "identity_content": {
                        "type": "string",
                        "description": "Content to append to the identity file.",
                        "default": "",
                    },
                },
                "required": ["proposal_id"],
            },
            handler=_apply_improvement,
            category="self_improvement",
            permission="approve",
        ),
        ToolDefinition(
            name="measure_impact",
            description=(
                "Measure the impact of an applied improvement by comparing "
                "before/after metrics. Returns an impact score from -100 to +100."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "proposal_id": {
                        "type": "integer",
                        "description": "ID of the applied proposal to measure.",
                    },
                },
                "required": ["proposal_id"],
            },
            handler=_measure_impact,
            category="self_improvement",
        ),
        ToolDefinition(
            name="rollback_improvement",
            description=(
                "Rollback an applied improvement by restoring from backup. "
                "Use after measure_impact shows regression."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "proposal_id": {
                        "type": "integer",
                        "description": "ID of the applied proposal to rollback.",
                    },
                },
                "required": ["proposal_id"],
            },
            handler=_rollback_improvement,
            category="self_improvement",
            permission="approve",
        ),
        ToolDefinition(
            name="list_improvements",
            description="List improvement proposals, optionally filtered by status.",
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: 'all', 'proposed', 'applied'.",
                        "default": "all",
                    },
                },
            },
            handler=_list_improvements,
            category="self_improvement",
        ),
        ToolDefinition(
            name="self_improve_loop",
            description=(
                "Run a multi-turn self-improvement loop: analyze behavior, "
                "propose an improvement, and report findings. Does NOT auto-apply "
                "— stops after proposal for human review."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "area": {
                        "type": "string",
                        "description": ("What to improve (e.g. 'tool:web_search', 'prompt')."),
                    },
                    "description": {
                        "type": "string",
                        "description": "Problem description or desired enhancement.",
                    },
                },
                "required": ["area", "description"],
            },
            handler=_self_improve_loop,
            category="self_improvement",
            permission="approve",
        ),
    ]

"""Agent adapter for the animus-conversation-designer-v0 eval suite.

Wires the eval harness directly to Animus's real ``ConversationDesignerCitizen``.
The adapter writes synthetic Claude Code-style conversation logs to a temporary
directory, points the citizen at them, and returns either the detected patterns or
a generated improvement proposal as structured plain text.

Environment:
    ANIMUS_CORE_PATH: Optional override for the Animus Core package root.
        Defaults to ``~/projects/animus/packages/core`` so the adapter can
        import ``animus.citizens.conversation_designer``.

Usage:
    animus-forge eval run animus-conversation-designer-v0 \
      --adapter eval_suites.adapters.animus_conversation_designer_v0:run_analyze \
      --rubric personal-quality \
      --model claude-haiku-4-5 \
      --prompt-version v0-initial
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_DEFAULT_CORE_PATH = Path("~/projects/animus/packages/core").expanduser()


def _ensure_core_importable() -> None:
    """Insert Animus Core on sys.path once per process."""
    core_path = Path(os.getenv("ANIMUS_CORE_PATH", _DEFAULT_CORE_PATH))
    target = str(core_path)
    if target not in sys.path:
        sys.path.insert(0, target)


def _build_log_entry(
    prompt: str,
    *,
    session_id: str = "session-eval-001",
    entry_type: str = "user",
    origin_kind: str = "human",
) -> dict[str, Any]:
    """Build a Claude Code-style JSONL entry for a human user prompt."""
    return {
        "type": entry_type,
        "sessionId": session_id,
        "origin": {"kind": origin_kind},
        "message": {"role": "user", "content": prompt},
    }


def _render_patterns(patterns: list[Any], log_count: int = 0) -> str:
    """Render ConversationPattern objects as readable plain text."""
    header = (
        "Analysis scope: ConversationDesignerCitizen analyzed human user prompts "
        "for repeated prompts, vague requests, and correction loops."
    )

    if not patterns:
        body = (
            f"Reviewed {log_count} human user log entry(s). "
            "No actionable conversation patterns were detected in this sample. "
            "This is the expected result when user prompts are clear, varied, and "
            "do not require clarification or correction."
        )
        return f"{header}\n\n{body}"

    lines: list[str] = [
        header,
        "",
        f"Reviewed {log_count} human user log entry(s). Detected {len(patterns)} conversation pattern(s):",
        "",
    ]
    for i, p in enumerate(patterns, 1):
        lines.extend(
            [
                f"[{i}] {p.pattern_type} (severity={p.severity}, frequency={p.frequency})",
                f"    Description: {p.description}",
                f"    Example: {p.example}",
                f"    Suggestion: {p.suggestion}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _render_proposal(proposal: Any, log_count: int = 0) -> str:
    """Render an ImprovementProposal as readable plain text."""
    header = (
        "Analysis scope: ConversationDesignerCitizen generated an improvement "
        "proposal from detected conversation patterns."
    )

    if proposal is None:
        body = (
            f"Reviewed {log_count} human user log entry(s) for actionable "
            "conversation patterns (repeated prompts, vague requests, correction loops). "
            "None were found above the frequency or severity thresholds, so no "
            "improvement proposal was generated. Recommendation: maintain current "
            "conversation design; re-run analysis after collecting more user interactions."
        )
        return f"{header}\n\n{body}"

    lines = [
        header,
        "",
        f"Proposal ID: {proposal.id}",
        f"Title: {proposal.title}",
        f"Status: {proposal.status.value}",
        f"Confidence: {proposal.confidence_score}",
        "",
        f"Problem: {proposal.problem}",
        "",
        f"Recommendation: {proposal.recommendation}",
        "",
        f"Root cause: {proposal.root_cause}",
        "",
        "Evidence:",
    ]
    for ev in proposal.evidence:
        lines.append(f"  - {ev.description}")
    lines.extend(
        [
            "",
            f"Affected components: {', '.join(proposal.affected_components)}",
            "",
            "Expected benefits:",
            f"  {proposal.expected_benefits}",
            "",
            "Success metrics:",
        ]
    )
    for metric in proposal.success_metrics:
        lines.append(f"  - {metric}")
    return "\n".join(lines).strip()


def _write_temp_logs(entries: list[dict[str, Any]]) -> Path:
    """Write synthetic conversation entries to a temp *.jsonl file."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="animus-cd-eval-"))
    log_file = tmp_dir / "conversation.jsonl"
    with log_file.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return tmp_dir


def run_analyze(case_input: str | dict[str, Any]) -> str:
    """Eval adapter entry point for the Conversation Designer citizen.

    Args:
        case_input: Either a plain string (treated as a single user prompt
            for a minimal repeated-prompt case) or a dict with:

            - ``log_entries``: list of conversation entries (Claude Code JSONL
              shape). If omitted, a default repeated-prompt case is used.
            - ``mode``: ``"analyze"`` returns detected patterns (default);
              ``"proposal"`` returns an ImprovementProposal rendered as text.
            - ``focus_pattern``: optional pattern type passed to
              ``generate_proposal()`` when mode is ``"proposal"``.

    Returns:
        Structured plain-text representation of the citizen output for the
        rubric judge to score.
    """
    _ensure_core_importable()
    from animus.citizens.conversation_designer import ConversationDesignerCitizen

    if isinstance(case_input, str):
        entries = [_build_log_entry(case_input)]
        mode = "analyze"
        focus_pattern = None
    else:
        raw_entries = case_input.get("log_entries") or []
        # Allow callers to pass either full JSONL dicts or simple prompt strings.
        entries: list[dict[str, Any]] = []
        for item in raw_entries:
            if isinstance(item, str):
                entries.append(_build_log_entry(item))
            else:
                entries.append(dict(item))
        mode = case_input.get("mode", "analyze")
        focus_pattern = case_input.get("focus_pattern")

    tmp_dir = _write_temp_logs(entries)
    try:
        citizen = ConversationDesignerCitizen(conversation_log_dir=tmp_dir)
        log_count = sum(1 for e in entries if ConversationDesignerCitizen._is_human_user_entry(e))
        if mode == "proposal":
            proposal = citizen.generate_proposal(focus_pattern=focus_pattern)
            return _render_proposal(proposal, log_count=log_count)
        patterns = citizen.analyze()
        return _render_patterns(patterns, log_count=log_count)
    finally:
        # Best-effort cleanup; temp dir is harmless if left behind.
        try:
            for child in tmp_dir.iterdir():
                child.unlink()
            tmp_dir.rmdir()
        except OSError:
            pass


__all__ = ["run_analyze"]

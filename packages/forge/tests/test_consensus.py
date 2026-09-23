"""Tests for consensus voting system."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from animus_forge.skills.consensus import (
    VOTER_PROMPTS,
    ConsensusLevel,
    ConsensusVerdict,
    ConsensusVoter,
    Vote,
    VoteDecision,
    consensus_level_order,
)

# ---------------------------------------------------------------------------
# Vote parsing
# ---------------------------------------------------------------------------


class TestVoteParsing:
    def test_approve_with_reason(self):
        vote = ConsensusVoter._parse_vote(0, "APPROVE\nLooks safe")
        assert vote.decision == VoteDecision.APPROVE
        assert vote.reasoning == "Looks safe"

    def test_reject_with_reason(self):
        vote = ConsensusVoter._parse_vote(1, "REJECT\nToo risky")
        assert vote.decision == VoteDecision.REJECT
        assert vote.reasoning == "Too risky"

    def test_approve_no_reason(self):
        vote = ConsensusVoter._parse_vote(0, "APPROVE")
        assert vote.decision == VoteDecision.APPROVE
        assert vote.reasoning == ""

    def test_garbage_returns_abstain(self):
        vote = ConsensusVoter._parse_vote(2, "I think this is fine")
        assert vote.decision == VoteDecision.ABSTAIN

    def test_empty_returns_abstain(self):
        vote = ConsensusVoter._parse_vote(0, "")
        assert vote.decision == VoteDecision.ABSTAIN

    def test_case_insensitive(self):
        vote = ConsensusVoter._parse_vote(0, "approve\nok")
        assert vote.decision == VoteDecision.APPROVE


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _make_votes(decisions: list[VoteDecision]) -> list[Vote]:
    return [Vote(voter_id=i, decision=d) for i, d in enumerate(decisions)]


class TestAggregation:
    def test_any_one_approve(self):
        v = ConsensusVoter._aggregate(ConsensusLevel.ANY, _make_votes([VoteDecision.APPROVE]))
        assert v.approved is True

    def test_majority_two_approve(self):
        v = ConsensusVoter._aggregate(
            ConsensusLevel.MAJORITY,
            _make_votes([VoteDecision.APPROVE, VoteDecision.APPROVE, VoteDecision.REJECT]),
        )
        assert v.approved is True

    def test_majority_two_reject(self):
        v = ConsensusVoter._aggregate(
            ConsensusLevel.MAJORITY,
            _make_votes([VoteDecision.APPROVE, VoteDecision.REJECT, VoteDecision.REJECT]),
        )
        assert v.approved is False

    def test_unanimous_all_approve(self):
        v = ConsensusVoter._aggregate(
            ConsensusLevel.UNANIMOUS,
            _make_votes([VoteDecision.APPROVE] * 3),
        )
        assert v.approved is True

    def test_unanimous_one_reject(self):
        v = ConsensusVoter._aggregate(
            ConsensusLevel.UNANIMOUS,
            _make_votes([VoteDecision.APPROVE, VoteDecision.APPROVE, VoteDecision.REJECT]),
        )
        assert v.approved is False

    def test_unanimous_plus_user_approved(self):
        v = ConsensusVoter._aggregate(
            ConsensusLevel.UNANIMOUS_PLUS_USER,
            _make_votes([VoteDecision.APPROVE] * 3),
        )
        assert v.approved is True
        assert v.requires_user_confirmation is True

    def test_all_abstain_fail_open(self):
        v = ConsensusVoter._aggregate(
            ConsensusLevel.UNANIMOUS,
            _make_votes([VoteDecision.ABSTAIN] * 3),
        )
        assert v.approved is True

    def test_verdict_to_dict(self):
        v = ConsensusVoter._aggregate(
            ConsensusLevel.MAJORITY,
            _make_votes([VoteDecision.APPROVE, VoteDecision.REJECT, VoteDecision.APPROVE]),
        )
        d = v.to_dict()
        assert d["level"] == "majority"
        assert d["approved"] is True
        assert d["approve_count"] == 2
        assert d["reject_count"] == 1
        assert len(d["votes"]) == 3


# ---------------------------------------------------------------------------
# ConsensusVoter (mocked client)
# ---------------------------------------------------------------------------


class TestConsensusVoter:
    def _mock_client(self, output: str = "APPROVE\nok"):
        client = MagicMock()
        client.generate_completion.return_value = {"success": True, "output": output}
        return client

    def test_any_calls_one_voter(self):
        client = self._mock_client()
        voter = ConsensusVoter(client)
        verdict = voter.vote("do something", "any")
        assert client.generate_completion.call_count == 1
        assert verdict.approved is True

    def test_majority_calls_three_voters(self):
        client = self._mock_client()
        voter = ConsensusVoter(client)
        verdict = voter.vote("do something", "majority")
        assert client.generate_completion.call_count == 3
        assert verdict.approved is True

    def test_voter_error_becomes_abstain(self):
        client = MagicMock()
        client.generate_completion.side_effect = RuntimeError("boom")
        voter = ConsensusVoter(client)
        verdict = voter.vote("do something", "majority")
        # All abstain → fail-open → approved
        assert verdict.approved is True
        assert all(v.decision == VoteDecision.ABSTAIN for v in verdict.votes)

    async def test_async_vote_uses_generate_completion_async(self):
        """vote_async should call generate_completion_async, not generate_completion."""
        client = MagicMock()
        client.generate_completion_async = AsyncMock(
            return_value={"success": True, "output": "APPROVE\nok"}
        )
        voter = ConsensusVoter(client)
        verdict = await voter.vote_async("do something", "majority")
        assert verdict.approved is True
        assert len(verdict.votes) == 3
        assert client.generate_completion_async.call_count == 3
        # sync generate_completion should NOT be called
        client.generate_completion.assert_not_called()

    async def test_async_vote_any_calls_one(self):
        client = MagicMock()
        client.generate_completion_async = AsyncMock(
            return_value={"success": True, "output": "APPROVE\nok"}
        )
        voter = ConsensusVoter(client)
        await voter.vote_async("do something", "any")
        assert client.generate_completion_async.call_count == 1

    async def test_async_voter_error_becomes_abstain(self):
        client = MagicMock()
        client.generate_completion_async = AsyncMock(side_effect=RuntimeError("boom"))
        voter = ConsensusVoter(client)
        verdict = await voter.vote_async("do something", "majority")
        assert verdict.approved is True
        assert all(v.decision == VoteDecision.ABSTAIN for v in verdict.votes)


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


class TestAuditLogging:
    def test_vote_emits_audit_log(self, caplog):
        client = MagicMock()
        client.generate_completion.return_value = {
            "success": True,
            "output": "APPROVE\nok",
        }
        voter = ConsensusVoter(client)
        with caplog.at_level(logging.INFO, logger="animus_forge.skills.consensus.audit"):
            voter.vote("delete /tmp/foo", "majority", role="builder")
        assert len(caplog.records) == 1
        rec = caplog.records[0]
        assert rec.consensus["role"] == "builder"
        assert rec.consensus["level"] == "majority"
        assert rec.consensus["approved"] is True
        assert rec.consensus["approve_count"] == 3
        assert "elapsed_seconds" in rec.consensus
        assert "timestamp" in rec.consensus

    def test_audit_log_truncates_long_operation(self, caplog):
        client = MagicMock()
        client.generate_completion.return_value = {
            "success": True,
            "output": "REJECT\nbad",
        }
        voter = ConsensusVoter(client)
        long_op = "x" * 500
        with caplog.at_level(logging.INFO, logger="animus_forge.skills.consensus.audit"):
            voter.vote(long_op, "majority")
        rec = caplog.records[0]
        assert len(rec.consensus["operation"]) == 200

    async def test_async_vote_emits_audit_log(self, caplog):
        client = MagicMock()
        client.generate_completion_async = AsyncMock(
            return_value={"success": True, "output": "APPROVE\nok"}
        )
        voter = ConsensusVoter(client)
        with caplog.at_level(logging.INFO, logger="animus_forge.skills.consensus.audit"):
            await voter.vote_async("test op", "unanimous", role="reviewer")
        assert len(caplog.records) == 1
        assert caplog.records[0].consensus["level"] == "unanimous"


# ---------------------------------------------------------------------------
# Client integration
# ---------------------------------------------------------------------------


class TestClientConsensusIntegration:
    @pytest.fixture
    def mock_settings(self, tmp_path):
        settings = MagicMock()
        settings.claude_mode = "api"
        settings.anthropic_api_key = None
        settings.claude_cli_path = "claude"
        settings.base_dir = tmp_path
        (tmp_path / "config").mkdir()
        return settings

    def _make_client(self, mock_settings):
        with (
            patch(
                "animus_forge.api_clients.claude_code_client.get_settings",
                return_value=mock_settings,
            ),
            patch("animus_forge.api_clients.claude_code_client.anthropic", None),
        ):
            from animus_forge.api_clients.claude_code_client import ClaudeCodeClient

            return ClaudeCodeClient()

    def test_consensus_included_when_level_above_any(self, mock_settings):
        client = self._make_client(mock_settings)
        mock_verdict = ConsensusVerdict(
            level=ConsensusLevel.MAJORITY,
            approved=True,
            votes=_make_votes([VoteDecision.APPROVE] * 3),
        )
        with (
            patch.object(client, "is_configured", return_value=True),
            patch.object(client, "_execute_via_cli", return_value="output"),
            patch.object(client, "_check_consensus", return_value=mock_verdict.to_dict()),
        ):
            client.mode = "cli"
            result = client.execute_agent("builder", "write tests")
        assert "consensus" in result
        assert result["consensus"]["approved"] is True
        assert result["success"] is True

    def test_blocked_enforcement_skips_consensus(self, mock_settings):
        client = self._make_client(mock_settings)
        with (
            patch.object(client, "is_configured", return_value=True),
            patch.object(client, "_execute_via_cli", return_value="output"),
            patch.object(
                client,
                "_check_enforcement",
                return_value={"action": "block", "passed": False, "violations": []},
            ),
        ):
            client.mode = "cli"
            result = client.execute_agent("builder", "write tests")
        assert "consensus" not in result

    def test_rejected_consensus_sets_failure(self, mock_settings):
        client = self._make_client(mock_settings)
        mock_verdict = ConsensusVerdict(
            level=ConsensusLevel.UNANIMOUS,
            approved=False,
            votes=_make_votes([VoteDecision.APPROVE, VoteDecision.REJECT, VoteDecision.REJECT]),
        )
        with (
            patch.object(client, "is_configured", return_value=True),
            patch.object(client, "_execute_via_cli", return_value="output"),
            patch.object(client, "_check_consensus", return_value=mock_verdict.to_dict()),
        ):
            client.mode = "cli"
            result = client.execute_agent("builder", "write tests")
        assert result["success"] is False
        assert "rejected" in result["error"].lower()

    def test_voter_failure_doesnt_break_execution(self, mock_settings):
        client = self._make_client(mock_settings)
        with (
            patch.object(client, "is_configured", return_value=True),
            patch.object(client, "_execute_via_cli", return_value="output"),
            patch.object(client, "_check_consensus", return_value=None),
        ):
            client.mode = "cli"
            result = client.execute_agent("builder", "write tests")
        assert result["success"] is True
        assert "consensus" not in result


# ---------------------------------------------------------------------------
# Library helper
# ---------------------------------------------------------------------------


class TestGetHighestConsensusForRole:
    def test_returns_highest_level(self):
        from animus_forge.skills.library import SkillLibrary

        mock_cap_any = MagicMock()
        mock_cap_any.consensus_required = "any"
        mock_cap_majority = MagicMock()
        mock_cap_majority.consensus_required = "majority"

        mock_skill = MagicMock()
        mock_skill.capabilities = [mock_cap_any, mock_cap_majority]

        with patch.object(SkillLibrary, "__init__", return_value=None):
            lib = SkillLibrary()
            lib._registry = MagicMock()
            lib._registry.get_skills_for_agent = MagicMock(return_value=[mock_skill])

        result = lib.get_highest_consensus_for_role("builder", {"builder": ["system"]})
        assert result == "majority"

    def test_returns_none_for_unmapped_role(self):
        from animus_forge.skills.library import SkillLibrary

        with patch.object(SkillLibrary, "__init__", return_value=None):
            lib = SkillLibrary()
            lib._registry = MagicMock()

        result = lib.get_highest_consensus_for_role("unknown", {"builder": ["system"]})
        assert result is None


class TestConsensusLevelOrder:
    def test_ordering(self):
        assert consensus_level_order("any") < consensus_level_order("majority")
        assert consensus_level_order("majority") < consensus_level_order("unanimous")
        assert consensus_level_order("unanimous") < consensus_level_order("unanimous_plus_user")

    def test_invalid_returns_negative(self):
        assert consensus_level_order("bogus") == -1


# ---------------------------------------------------------------------------
# Cached library property (Task 1)
# ---------------------------------------------------------------------------


class TestCachedLibrary:
    @pytest.fixture
    def mock_settings(self, tmp_path):
        settings = MagicMock()
        settings.claude_mode = "api"
        settings.anthropic_api_key = None
        settings.claude_cli_path = "claude"
        settings.base_dir = tmp_path
        (tmp_path / "config").mkdir()
        return settings

    def _make_client(self, mock_settings):
        with (
            patch(
                "animus_forge.api_clients.claude_code_client.get_settings",
                return_value=mock_settings,
            ),
            patch("animus_forge.api_clients.claude_code_client.anthropic", None),
        ):
            from animus_forge.api_clients.claude_code_client import ClaudeCodeClient

            return ClaudeCodeClient()

    def test_library_property_caches(self, mock_settings):
        client = self._make_client(mock_settings)
        lib1 = client.library
        lib2 = client.library
        assert lib1 is lib2

    def test_library_failure_returns_none(self, mock_settings):
        client = self._make_client(mock_settings)
        with patch("animus_forge.skills.SkillLibrary", side_effect=RuntimeError("no skills")):
            client._library_init_attempted = False
            assert client.library is None


# ---------------------------------------------------------------------------
# Unanimous + user confirmation (Task 2)
# ---------------------------------------------------------------------------


class TestUserConfirmationFlow:
    @pytest.fixture
    def mock_settings(self, tmp_path):
        settings = MagicMock()
        settings.claude_mode = "api"
        settings.anthropic_api_key = None
        settings.claude_cli_path = "claude"
        settings.base_dir = tmp_path
        (tmp_path / "config").mkdir()
        return settings

    def _make_client(self, mock_settings):
        with (
            patch(
                "animus_forge.api_clients.claude_code_client.get_settings",
                return_value=mock_settings,
            ),
            patch("animus_forge.api_clients.claude_code_client.anthropic", None),
        ):
            from animus_forge.api_clients.claude_code_client import ClaudeCodeClient

            return ClaudeCodeClient()

    def test_unanimous_plus_user_sets_pending_flag(self, mock_settings):
        client = self._make_client(mock_settings)
        verdict = ConsensusVerdict(
            level=ConsensusLevel.UNANIMOUS_PLUS_USER,
            approved=True,
            votes=_make_votes([VoteDecision.APPROVE] * 3),
            requires_user_confirmation=True,
        )
        d = verdict.to_dict()
        d["pending_user_confirmation"] = True
        with (
            patch.object(client, "is_configured", return_value=True),
            patch.object(client, "_execute_via_cli", return_value="output"),
            patch.object(client, "_check_consensus", return_value=d),
        ):
            client.mode = "cli"
            result = client.execute_agent("builder", "delete directory")
        assert result["success"] is True
        assert result.get("pending_user_confirmation") is True
        assert result["consensus"]["requires_user_confirmation"] is True

    def test_non_user_confirmation_has_no_pending_flag(self, mock_settings):
        client = self._make_client(mock_settings)
        verdict = ConsensusVerdict(
            level=ConsensusLevel.MAJORITY,
            approved=True,
            votes=_make_votes([VoteDecision.APPROVE] * 3),
        )
        with (
            patch.object(client, "is_configured", return_value=True),
            patch.object(client, "_execute_via_cli", return_value="output"),
            patch.object(client, "_check_consensus", return_value=verdict.to_dict()),
        ):
            client.mode = "cli"
            result = client.execute_agent("builder", "update file")
        assert result.get("pending_user_confirmation") is None


# ---------------------------------------------------------------------------
# Capability-level consensus matching (Task 3)
# ---------------------------------------------------------------------------


class TestCapabilityLevelMatching:
    @pytest.fixture
    def mock_settings(self, tmp_path):
        settings = MagicMock()
        settings.claude_mode = "api"
        settings.anthropic_api_key = None
        settings.claude_cli_path = "claude"
        settings.base_dir = tmp_path
        (tmp_path / "config").mkdir()
        return settings

    def _make_client(self, mock_settings):
        with (
            patch(
                "animus_forge.api_clients.claude_code_client.get_settings",
                return_value=mock_settings,
            ),
            patch("animus_forge.api_clients.claude_code_client.anthropic", None),
        ):
            from animus_forge.api_clients.claude_code_client import ClaudeCodeClient

            return ClaudeCodeClient()

    def test_matches_capability_in_task(self, mock_settings):
        """Task mentioning 'delete_file' should match unanimous, not fallback."""
        from animus_forge.skills.models import SkillCapability, SkillDefinition

        cap_read = SkillCapability(name="read_file", consensus_required="any")
        cap_delete = SkillCapability(name="delete_file", consensus_required="unanimous")
        skill = SkillDefinition(
            name="file_operations",
            agent="system",
            capabilities=[cap_read, cap_delete],
        )

        client = self._make_client(mock_settings)
        mock_lib = MagicMock()
        mock_lib.get_skills_for_agent.return_value = [skill]
        mock_lib.get_highest_consensus_for_role.return_value = "unanimous"
        client._library = mock_lib
        client._library_init_attempted = True

        level = client._resolve_consensus_level("builder", "please delete_file /tmp/foo")
        assert level == "unanimous"

    def test_matches_capability_name_with_spaces(self, mock_settings):
        """Task mentioning 'read file' should match 'read_file' capability."""
        from animus_forge.skills.models import SkillCapability, SkillDefinition

        cap_read = SkillCapability(name="read_file", consensus_required="any")
        cap_delete = SkillCapability(name="delete_file", consensus_required="unanimous")
        skill = SkillDefinition(
            name="file_operations",
            agent="system",
            capabilities=[cap_read, cap_delete],
        )

        client = self._make_client(mock_settings)
        mock_lib = MagicMock()
        mock_lib.get_skills_for_agent.return_value = [skill]
        client._library = mock_lib
        client._library_init_attempted = True

        level = client._resolve_consensus_level("builder", "read file from /etc/config")
        assert level == "any"

    def test_falls_back_to_highest_when_no_match(self, mock_settings):
        """When no capability name appears in task, falls back to highest."""
        from animus_forge.skills.models import SkillCapability, SkillDefinition

        cap = SkillCapability(name="delete_file", consensus_required="unanimous")
        skill = SkillDefinition(
            name="file_operations",
            agent="system",
            capabilities=[cap],
        )

        client = self._make_client(mock_settings)
        mock_lib = MagicMock()
        mock_lib.get_skills_for_agent.return_value = [skill]
        mock_lib.get_highest_consensus_for_role.return_value = "unanimous"
        client._library = mock_lib
        client._library_init_attempted = True

        level = client._resolve_consensus_level("builder", "do something generic")
        assert level == "unanimous"

    def test_no_library_returns_none(self, mock_settings):
        client = self._make_client(mock_settings)
        client._library = None
        client._library_init_attempted = True
        assert client._resolve_consensus_level("builder", "anything") is None


# ---------------------------------------------------------------------------
# Integration tests with real skill YAML (Task 4)
# ---------------------------------------------------------------------------


class TestRealSkillYAMLIntegration:
    """Tests that load actual skill YAML from the skills/ directory."""

    @pytest.fixture
    def library(self):
        from pathlib import Path

        from animus_forge.skills.library import SkillLibrary

        skills_dir = Path(__file__).parent.parent / "skills"
        if not skills_dir.exists():
            pytest.skip("skills/ directory not found")
        return SkillLibrary(skills_dir)

    def test_file_operations_loaded(self, library):
        skill = library.get_skill("file_operations")
        assert skill is not None
        assert skill.agent == "system"

    def test_file_operations_has_consensus_levels(self, library):
        skill = library.get_skill("file_operations")
        assert skill is not None
        levels = {cap.name: cap.consensus_required for cap in skill.capabilities}
        assert levels["read_file"] == "any"
        assert levels["update_file"] == "majority"
        assert levels["delete_file"] == "unanimous"

    def test_highest_consensus_for_builder(self, library):
        """Builder role (system + browser agents) should have unanimous as highest."""
        level = library.get_highest_consensus_for_role(
            "builder", {"builder": ["system", "browser"]}
        )
        # file_operations has delete_file=unanimous and set_permissions=unanimous
        assert level == "unanimous"

    def test_highest_consensus_for_reviewer(self, library):
        """Reviewer role (system agent only) should still pick up unanimous."""
        level = library.get_highest_consensus_for_role("reviewer", {"reviewer": ["system"]})
        assert level == "unanimous"

    def test_consensus_level_for_specific_capability(self, library):
        """get_consensus_level returns correct per-capability level."""
        assert library.get_consensus_level("file_operations", "read_file") == "any"
        assert library.get_consensus_level("file_operations", "delete_file") == "unanimous"
        assert library.get_consensus_level("file_operations", "update_file") == "majority"

    def test_github_operations_loaded(self, library):
        skill = library.get_skill("github_operations")
        assert skill is not None
        cap_names = [c.name for c in skill.capabilities]
        assert "merge_pull_request" in cap_names

    def test_all_skills_have_consensus_on_capabilities(self, library):
        """Every capability across all skills should have a valid consensus_required."""
        valid = {"any", "majority", "unanimous", "unanimous_plus_user"}
        for skill in library.registry.skills:
            for cap in skill.capabilities:
                assert cap.consensus_required in valid, (
                    f"{skill.name}.{cap.name} has invalid consensus: {cap.consensus_required}"
                )


# ---------------------------------------------------------------------------
# Voter diversity (distinct evaluation lenses)
# ---------------------------------------------------------------------------


class TestVoterDiversity:
    def test_three_distinct_prompts(self):
        assert len(VOTER_PROMPTS) == 3
        assert len(set(VOTER_PROMPTS)) == 3  # all unique

    def test_prompts_cover_safety_correctness_alignment(self):
        assert "SAFETY" in VOTER_PROMPTS[0].upper()
        assert "CORRECTNESS" in VOTER_PROMPTS[1].upper()
        assert "ALIGNMENT" in VOTER_PROMPTS[2].upper()

    def test_each_voter_gets_different_prompt(self):
        """Sync voter calls should use per-voter prompts."""
        client = MagicMock()
        client.generate_completion.return_value = {
            "success": True,
            "output": "APPROVE\nok",
        }
        voter = ConsensusVoter(client)
        voter.vote("do something", "majority")

        prompts_used = [
            call.kwargs["system_prompt"] for call in client.generate_completion.call_args_list
        ]
        assert len(prompts_used) == 3
        assert prompts_used[0] != prompts_used[1]
        assert prompts_used[1] != prompts_used[2]
        assert prompts_used[0] == VOTER_PROMPTS[0]
        assert prompts_used[1] == VOTER_PROMPTS[1]
        assert prompts_used[2] == VOTER_PROMPTS[2]

    async def test_async_voters_get_different_prompts(self):
        client = MagicMock()
        client.generate_completion_async = AsyncMock(
            return_value={"success": True, "output": "APPROVE\nok"}
        )
        voter = ConsensusVoter(client)
        await voter.vote_async("do something", "unanimous")

        prompts_used = [
            call.kwargs["system_prompt"] for call in client.generate_completion_async.call_args_list
        ]
        assert len(prompts_used) == 3
        assert prompts_used == list(VOTER_PROMPTS)

    def test_voter_id_wraps_for_out_of_range(self):
        # voter_id 3 should wrap to prompt index 0
        prompt = ConsensusVoter._get_voter_prompt(3)
        assert prompt == VOTER_PROMPTS[0]


# ---------------------------------------------------------------------------
# Cost tracking for voter calls
# ---------------------------------------------------------------------------


class TestVoterCostTracking:
    def test_track_voter_cost_calls_tracker(self):
        from animus_forge.metrics.cost_tracker import Provider

        mock_tracker = MagicMock()
        with patch("animus_forge.metrics.cost_tracker.get_cost_tracker", return_value=mock_tracker):
            ConsensusVoter._track_voter_cost(0, "APPROVE\nLooks safe", "builder")

        mock_tracker.track.assert_called_once()
        kw = mock_tracker.track.call_args.kwargs
        assert kw["provider"] == Provider.ANTHROPIC
        assert kw["agent_role"] == "zorya_voter_0"
        assert kw["metadata"]["consensus_role"] == "builder"
        assert kw["input_tokens"] == 80
        assert kw["output_tokens"] > 0

    def test_cost_tracked_during_vote(self):
        client = MagicMock()
        client.generate_completion.return_value = {
            "success": True,
            "output": "APPROVE\nok",
        }
        voter = ConsensusVoter(client)

        mock_tracker = MagicMock()
        with patch("animus_forge.metrics.cost_tracker.get_cost_tracker", return_value=mock_tracker):
            voter.vote("test op", "majority", role="builder")

        assert mock_tracker.track.call_count == 3

    def test_cost_tracking_failure_does_not_break_vote(self):
        """If cost tracker raises, voting still works."""
        client = MagicMock()
        client.generate_completion.return_value = {
            "success": True,
            "output": "APPROVE\nok",
        }
        voter = ConsensusVoter(client)

        with patch(
            "animus_forge.metrics.cost_tracker.get_cost_tracker",
            side_effect=RuntimeError("no tracker"),
        ):
            verdict = voter.vote("do something", "majority", role="builder")

        assert verdict.approved is True
        assert len(verdict.votes) == 3


# ---------------------------------------------------------------------------
# Orchestrator consensus integration (executor + pipeline)
# ---------------------------------------------------------------------------


class TestOrchestratorConsensusIntegration:
    """Tests that consensus results propagate through executor and pipeline."""

    def test_executor_consensus_rejection_raises(self):
        """Consensus rejection (success=False) triggers RuntimeError in _execute_claude_code."""
        from animus_forge.workflow.executor import WorkflowExecutor

        executor = WorkflowExecutor.__new__(WorkflowExecutor)
        executor.memory_manager = None
        executor.dry_run = False

        step = MagicMock()
        step.id = "s1"
        step.params = {"role": "builder", "prompt": "do something"}
        step.executor_type = "claude_code"

        rejected_result = {
            "success": False,
            "error": "Consensus rejected: 1/3 approved",
            "consensus": {"approved": False, "level": "unanimous"},
        }

        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.execute_agent.return_value = rejected_result

        with patch(
            "animus_forge.workflow.executor_clients._get_claude_client", return_value=mock_client
        ):
            with pytest.raises(RuntimeError, match="Consensus rejected"):
                executor._execute_claude_code(step, {})

    def test_executor_pending_confirmation_in_output(self):
        """pending_user_confirmation propagates into step output dict."""
        from animus_forge.workflow.executor import WorkflowExecutor

        executor = WorkflowExecutor.__new__(WorkflowExecutor)
        executor.memory_manager = None
        executor.dry_run = False

        step = MagicMock()
        step.id = "s1"
        step.params = {"role": "builder", "prompt": "delete dir"}
        step.executor_type = "claude_code"

        confirmed_result = {
            "success": True,
            "output": "done",
            "pending_user_confirmation": True,
            "consensus": {
                "approved": True,
                "level": "unanimous_plus_user",
                "requires_user_confirmation": True,
            },
        }

        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.execute_agent.return_value = confirmed_result

        with patch(
            "animus_forge.workflow.executor_clients._get_claude_client", return_value=mock_client
        ):
            output = executor._execute_claude_code(step, {})

        assert output["pending_user_confirmation"] is True
        assert output["consensus"]["level"] == "unanimous_plus_user"

    def test_executor_consensus_metadata_in_output(self):
        """Consensus metadata appears in output when present."""
        from animus_forge.workflow.executor import WorkflowExecutor

        executor = WorkflowExecutor.__new__(WorkflowExecutor)
        executor.memory_manager = None
        executor.dry_run = False

        step = MagicMock()
        step.id = "s1"
        step.params = {"role": "builder", "prompt": "update file"}
        step.executor_type = "claude_code"

        result = {
            "success": True,
            "output": "updated",
            "consensus": {"approved": True, "level": "majority", "approve_count": 2},
        }

        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.execute_agent.return_value = result

        with patch(
            "animus_forge.workflow.executor_clients._get_claude_client", return_value=mock_client
        ):
            output = executor._execute_claude_code(step, {})

        assert output["consensus"]["approve_count"] == 2
        assert "pending_user_confirmation" not in output

    def test_pipeline_agent_handler_raises_on_failure(self):
        """Pipeline agent_handler raises RuntimeError when success=False."""
        from animus_forge.analytics.pipeline import AnalyticsPipeline

        mock_client = MagicMock()
        mock_client.execute_agent.return_value = {
            "success": False,
            "error": "Consensus rejected",
        }

        pipeline = AnalyticsPipeline.__new__(AnalyticsPipeline)
        pipeline._claude_client = mock_client
        pipeline._stages = []
        pipeline.pipeline_id = "test"

        pipeline.add_agent_stage("analyze", "analyst", "analyze {{context}}")

        _, handler, _ = pipeline._stages[0]
        with pytest.raises(RuntimeError, match="Consensus rejected"):
            handler("test context", {})

    def test_pipeline_agent_handler_wraps_pending_confirmation(self):
        """Pipeline agent_handler wraps output with confirmation metadata."""
        from animus_forge.analytics.pipeline import AnalyticsPipeline

        mock_client = MagicMock()
        mock_client.execute_agent.return_value = {
            "success": True,
            "output": "analysis result",
            "pending_user_confirmation": True,
            "consensus": {"approved": True, "level": "unanimous_plus_user"},
        }

        pipeline = AnalyticsPipeline.__new__(AnalyticsPipeline)
        pipeline._claude_client = mock_client
        pipeline._stages = []
        pipeline.pipeline_id = "test"

        pipeline.add_agent_stage("analyze", "analyst", "analyze {{context}}")

        _, handler, _ = pipeline._stages[0]
        result = handler("test context", {})

        assert result["pending_user_confirmation"] is True
        assert result["output"] == "analysis result"
        assert result["consensus"]["level"] == "unanimous_plus_user"

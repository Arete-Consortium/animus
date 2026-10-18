"""Tests for the Animus Citizens package (Mind Foundation layer)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from animus.citizens import (
    AbstractionCitizen,
    ArchitectCitizen,
    ArchitectureCitizen,
    CitizenCouncil,
    ConversationDesignerCitizen,
    FirstPrinciplesCitizen,
    ForgeCommissioner,
    HarvesterCitizen,
    ImprovementProposal,
    IntelligenceCitizen,
    KnowledgeCuratorCitizen,
    PatternCitizen,
    ProposalQueue,
    ProposalStatus,
    ResearchGuildOrchestrator,
    TestOracleCitizen,
)
from animus.citizens.commissioner import CommissionResult
from animus.citizens.proposal import EvidenceItem, ProposalConfidence, RiskAssessment
from animus.citizens.research_guild import GuildPipelineReport, StageResult

# ---------------------------------------------------------------------------
# ImprovementProposal tests
# ---------------------------------------------------------------------------


class TestImprovementProposal:
    def test_basic_creation(self):
        proposal = ImprovementProposal(
            id="ADL-20260705-001",
            title="Test Proposal",
            problem="Something is wrong",
        )
        assert proposal.id == "ADL-20260705-001"
        assert proposal.status == ProposalStatus.DRAFT
        assert proposal.confidence_score == 0.5

    def test_confidence_mapping(self):
        proposal = ImprovementProposal(id="1", title="T", problem="P", confidence_score=0.95)
        assert proposal.confidence == ProposalConfidence.VERY_HIGH

        proposal.confidence_score = 0.8
        assert proposal.confidence == ProposalConfidence.HIGH

        proposal.confidence_score = 0.6
        assert proposal.confidence == ProposalConfidence.MEDIUM

        proposal.confidence_score = 0.3
        assert proposal.confidence == ProposalConfidence.LOW

        proposal.confidence_score = 0.1
        assert proposal.confidence == ProposalConfidence.VERY_LOW

    def test_status_update(self):
        proposal = ImprovementProposal(id="1", title="T", problem="P")
        proposal.update_status(ProposalStatus.APPROVED, actor="human")
        assert proposal.status == ProposalStatus.APPROVED
        assert proposal.approved_by == "human"
        assert proposal.approved_at is not None

    def test_serialization_roundtrip(self):
        original = ImprovementProposal(
            id="ADL-20260705-001",
            title="Test Proposal",
            problem="Problem description",
            evidence=[EvidenceItem(source="codebase", description="Found issue in file.py")],
            potential_risks=[
                RiskAssessment(
                    description="Might break tests",
                    severity="medium",
                    mitigation="Run full suite",
                )
            ],
            confidence_score=0.75,
            affected_components=["Factory", "Kernel"],
        )

        data = original.to_dict()
        restored = ImprovementProposal.from_dict(data)

        assert restored.id == original.id
        assert restored.title == original.title
        assert len(restored.evidence) == 1
        assert restored.evidence[0].source == "codebase"
        assert len(restored.potential_risks) == 1
        assert restored.potential_risks[0].severity == "medium"
        assert restored.confidence_score == 0.75
        assert restored.affected_components == ["Factory", "Kernel"]


# ---------------------------------------------------------------------------
# ArchitectCitizen tests
# ---------------------------------------------------------------------------


class TestArchitectCitizen:
    def test_initialization(self):
        architect = ArchitectCitizen(codebase_path="/tmp/test")
        assert architect.codebase_path == Path("/tmp/test")
        assert architect._observations == []

    def test_map_priority_to_severity(self):
        assert ArchitectCitizen._map_priority_to_severity(1) == "critical"
        assert ArchitectCitizen._map_priority_to_severity(2) == "high"
        assert ArchitectCitizen._map_priority_to_severity(3) == "medium"
        assert ArchitectCitizen._map_priority_to_severity(4) == "low"
        assert ArchitectCitizen._map_priority_to_severity(5) == "info"
        assert ArchitectCitizen._map_priority_to_severity(99) == "medium"

    def test_observe_conversations_repeated_prompts(self, tmp_path):
        log_dir = tmp_path / "conversations"
        log_dir.mkdir()

        # Create conversation logs with repeated prompts
        for i in range(5):
            log_file = log_dir / f"session_{i}.jsonl"
            entries = [
                json.dumps({"prompt": "How do I configure the API?"}),
                json.dumps({"prompt": "Help me debug this error"}),
                json.dumps({"prompt": "How do I configure the API?"}),
            ]
            log_file.write_text("\n".join(entries))

        architect = ArchitectCitizen(
            codebase_path=tmp_path,
            conversation_log_dir=log_dir,
        )

        observations = architect.observe_conversations()
        assert len(observations) >= 1
        assert observations[0].source == "conversation"
        assert "Repeated prompt detected" in observations[0].description
        assert observations[0].context["count"] >= 3

    def test_observe_conversations_no_logs(self, tmp_path):
        architect = ArchitectCitizen(
            codebase_path=tmp_path,
            conversation_log_dir=tmp_path / "nonexistent",
        )
        observations = architect.observe_conversations()
        # No logs configured — gracefully returns empty, not a false-positive finding.
        assert len(observations) == 0

    def test_analyze_empty_observations(self, tmp_path):
        architect = ArchitectCitizen(codebase_path=tmp_path)
        # Patch auto-observe methods so they don't add default observations
        with (
            patch.object(architect, "observe_codebase", return_value=[]),
            patch.object(architect, "observe_conversations", return_value=[]),
            patch.object(architect, "observe_evaluations", return_value=[]),
        ):
            report = architect.analyze()
        assert report.findings == []
        assert report.technical_debt_items == []
        assert report.friction_points == []

    def test_analyze_with_observations(self, tmp_path):
        from animus.citizens.architect import Observation

        architect = ArchitectCitizen(codebase_path=tmp_path)
        architect._observations = [
            Observation(
                source="codebase", description="High complexity in parser.py", severity="high"
            ),
            Observation(
                source="conversation", description="Users confused by auth flow", severity="medium"
            ),
        ]

        report = architect.analyze()
        assert len(report.technical_debt_items) == 1
        assert "parser.py" in report.technical_debt_items[0]
        assert len(report.friction_points) == 1
        assert "auth" in report.friction_points[0]
        assert len(report.recommendations) == 2

    def test_generate_proposal_no_findings(self, tmp_path):
        architect = ArchitectCitizen(codebase_path=tmp_path)
        # Patch auto-observe methods so no default observations are added
        with (
            patch.object(architect, "observe_codebase", return_value=[]),
            patch.object(architect, "observe_conversations", return_value=[]),
            patch.object(architect, "observe_evaluations", return_value=[]),
        ):
            report = architect.analyze()
        proposal = architect.generate_proposal(report)
        assert proposal is None

    def test_generate_proposal_with_findings(self, tmp_path):
        from animus.citizens.architect import Observation

        architect = ArchitectCitizen(codebase_path=tmp_path)
        architect._observations = [
            Observation(
                source="codebase", description="High complexity in parser.py", severity="high"
            ),
        ]

        report = architect.analyze()
        proposal = architect.generate_proposal(report)
        assert proposal is not None
        assert proposal.status == ProposalStatus.DRAFT
        # Confidence is now dynamically scored from evidence quality
        assert 0.25 <= proposal.confidence_score <= 1.0
        assert "parser.py" in proposal.problem
        assert proposal.affected_components == ["Factory", "Kernel"]
        assert len(proposal.evidence) >= 1
        assert len(proposal.potential_risks) >= 2
        # Senior skillsets should enrich the recommendation
        assert (
            "Trade-off analysis" in proposal.recommendation
            or "Estimated effort" in proposal.recommendation
        )

    def test_store_proposal_without_memory(self, tmp_path):
        architect = ArchitectCitizen(codebase_path=tmp_path)
        proposal = ImprovementProposal(id="1", title="Test", problem="P")
        assert architect.store_proposal(proposal) is False

    def test_store_proposal_with_memory(self, tmp_path):
        mock_memory = MagicMock()
        architect = ArchitectCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        proposal = ImprovementProposal(id="1", title="Test", problem="P", recommendation="R")

        assert architect.store_proposal(proposal) is True
        mock_memory.remember.assert_called_once()
        call_kwargs = mock_memory.remember.call_args.kwargs
        assert "architect" in call_kwargs["tags"]
        assert "proposal" in call_kwargs["tags"]

    def test_list_pending_proposals(self, tmp_path):
        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            {
                "content": "Proposal 1",
                "metadata": {
                    "id": "1",
                    "title": "T1",
                    "status": "submitted",
                    "problem": "P1",
                    "recommendation": "R1",
                },
            },
            {
                "content": "Proposal 2",
                "metadata": {
                    "id": "2",
                    "title": "T2",
                    "status": "complete",
                    "problem": "P2",
                    "recommendation": "R2",
                },
            },
        ]

        architect = ArchitectCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        pending = architect.list_pending_proposals()
        assert len(pending) == 1
        assert pending[0].id == "1"

    def test_observe_codebase_with_analyzer(self, tmp_path):
        mock_analyzer = MagicMock()
        mock_suggestion = MagicMock()
        mock_suggestion.category = "code_quality"
        mock_suggestion.title = "Refactor long function"
        mock_suggestion.description = "Function is 200 lines"
        mock_suggestion.priority = 2
        mock_suggestion.estimated_lines = 50
        mock_suggestion.reasoning = "Too long"
        mock_suggestion.affected_files = ["main.py"]

        mock_analyzer.analyze.return_value = MagicMock(
            suggestions=[mock_suggestion],
        )

        architect = ArchitectCitizen(codebase_path=tmp_path)
        with patch.object(architect, "_get_analyzer", return_value=mock_analyzer):
            observations = architect.observe_codebase()

        assert len(observations) == 1
        assert observations[0].source == "codebase"
        assert "Refactor long function" in observations[0].description
        assert observations[0].severity == "high"

    def test_senior_dependency_analysis_tight_coupling(self, tmp_path):
        # Create a module that imports many others (>10 threshold)
        pkg = tmp_path / "core"
        pkg.mkdir()
        main = pkg / "main.py"
        main.write_text(
            "import os\nimport sys\nimport json\nimport re\nimport ast\n"
            "import typing\nimport collections\nimport itertools\nimport functools\n"
            "import pathlib\nimport datetime\nimport hashlib\nimport uuid\nimport logging\n"
            "\ndef hello(): pass\n"
        )
        architect = ArchitectCitizen(codebase_path=tmp_path)
        obs = architect._analyze_dependencies()
        assert len(obs) >= 1
        assert any(o.context.get("pattern_type") == "tight_coupling" for o in obs)

    def test_senior_dependency_analysis_circular_import(self, tmp_path):
        pkg = tmp_path / "core"
        pkg.mkdir()
        a = pkg / "a.py"
        b = pkg / "b.py"
        a.write_text("from . import b\n")
        b.write_text("from . import a\n")
        architect = ArchitectCitizen(codebase_path=tmp_path)
        obs = architect._analyze_dependencies()
        assert any(o.context.get("pattern_type") == "circular_import" for o in obs)

    def test_senior_detect_god_class(self, tmp_path):
        pkg = tmp_path / "core"
        pkg.mkdir()
        f = pkg / "big.py"
        methods = "\n".join(f"    def method_{i}(self): pass" for i in range(20))
        f.write_text(f"class GodClass:\n{methods}\n")
        architect = ArchitectCitizen(codebase_path=tmp_path)
        obs = architect._detect_architectural_patterns()
        assert any(o.context.get("pattern_type") == "god_class" for o in obs)

    def test_senior_detect_singleton_abuse(self, tmp_path):
        pkg = tmp_path / "core"
        pkg.mkdir()
        f = pkg / "singleton.py"
        f.write_text("class MySingleton:\n    def __new__(cls): pass\n")
        architect = ArchitectCitizen(codebase_path=tmp_path)
        obs = architect._detect_architectural_patterns()
        assert any(o.context.get("pattern_type") == "singleton_abuse" for o in obs)

    def test_senior_constraint_check_blocks_direct_modification(self, tmp_path):
        architect = ArchitectCitizen(codebase_path=tmp_path)
        proposal = ImprovementProposal(
            id="1",
            title="T",
            problem="P",
            recommendation="Modify directly the source code",
            evaluation_plan="Run tests",
            rollback_plan="Revert",
            affected_components=["Mind"],
        )
        violations = architect._check_architectural_constraints(proposal)
        assert any("modify directly" in v.lower() for v in violations)

    def test_senior_constraint_check_requires_evaluation_plan(self, tmp_path):
        architect = ArchitectCitizen(codebase_path=tmp_path)
        proposal = ImprovementProposal(
            id="1",
            title="T",
            problem="P",
            recommendation="Refactor parser",
            rollback_plan="Revert",
            affected_components=["Mind"],
        )
        violations = architect._check_architectural_constraints(proposal)
        assert any("evaluation plan" in v.lower() for v in violations)

    def test_senior_impact_estimation_empty(self, tmp_path):
        architect = ArchitectCitizen(codebase_path=tmp_path)
        impact = architect._estimate_impact([])
        assert impact["component_count"] == 0
        assert impact["impact_score"] == 0.0

    def test_senior_impact_estimation_with_files(self, tmp_path):
        architect = ArchitectCitizen(codebase_path=tmp_path)
        impact = architect._estimate_impact(["packages/core/animus/identity.py"])
        assert impact["component_count"] >= 1
        assert 0 < impact["impact_score"] <= 1.0

    def test_senior_evidence_quality_score_no_evidence(self, tmp_path):
        architect = ArchitectCitizen(codebase_path=tmp_path)
        score = architect._score_evidence_quality([])
        assert score == 0.3

    def test_senior_evidence_quality_score_with_evidence(self, tmp_path):
        from animus.citizens.proposal import EvidenceItem

        architect = ArchitectCitizen(codebase_path=tmp_path)
        evidence = [
            EvidenceItem(
                source="codebase", description="Issue in parser.py", data={"file": "parser.py"}
            ),
            EvidenceItem(source="evaluation", description="Low score", data={"score": 0.5}),
        ]
        score = architect._score_evidence_quality(evidence)
        assert 0.4 < score <= 1.0

    def test_senior_trade_off_analysis(self, tmp_path):
        from animus.citizens.proposal import RiskAssessment

        architect = ArchitectCitizen(codebase_path=tmp_path)
        proposal = ImprovementProposal(
            id="1",
            title="T",
            problem="P",
            estimated_effort_hours=6.0,
            affected_components=["Factory", "Kernel"],
            potential_risks=[
                RiskAssessment(
                    description="Might break tests",
                    severity="medium",
                    mitigation="Run suite",
                    probability=0.3,
                ),
            ],
            alternatives_considered=["Status quo"],
        )
        trade_offs = architect._build_trade_off_analysis(proposal)
        assert "6.0 hours" in trade_offs
        assert "Factory" in trade_offs
        assert "Status quo" in trade_offs

    # --- Indexed code memory integration tests ---

    def test_indexed_code_memory_no_memory_returns_empty(self, tmp_path):
        """When no memory layer is attached, indexed code observation is empty."""
        architect = ArchitectCitizen(codebase_path=tmp_path)
        obs = architect._observe_indexed_code_memory()
        assert obs == []

    def test_indexed_code_memory_no_chunks_returns_empty(self, tmp_path):
        """When memory returns no code_ingest chunks, observation is empty."""
        mock_memory = MagicMock()
        mock_memory.search.return_value = []
        architect = ArchitectCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        obs = architect._observe_indexed_code_memory()
        assert obs == []
        mock_memory.search.assert_called_once()
        call_kwargs = mock_memory.search.call_args.kwargs
        assert call_kwargs["source"] == "code_ingest"
        assert call_kwargs["memory_type"].value == "semantic"

    def test_indexed_code_memory_coverage_low(self, tmp_path):
        """Low coverage triggers a medium-severity observation via manifest summary."""
        manifest = {
            "version": "1.1",
            "summary": {"total_scanned_files": 3, "total_chunked_files": 1, "total_chunks": 2},
            "files": {"core/a.py": {"chunk_count": 2, "mtime": 1.0}},
        }
        manifest_path = tmp_path / ".animus_ingest_manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            MagicMock(
                metadata={"file_path": "core/a.py", "chunk_type": "function"},
                created_at=datetime.now(),
            ),
        ]

        architect = ArchitectCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        obs = architect._observe_indexed_code_memory()
        coverage_obs = [
            o for o in obs if o.context.get("pattern_type") == "indexed_memory_coverage"
        ]
        assert len(coverage_obs) == 1
        assert coverage_obs[0].severity == "medium"
        assert "33%" in coverage_obs[0].description

    def test_indexed_code_memory_coverage_high(self, tmp_path):
        """High coverage triggers an info-level observation via manifest summary."""
        manifest = {
            "version": "1.1",
            "summary": {"total_scanned_files": 2, "total_chunked_files": 2, "total_chunks": 2},
            "files": {
                "core/a.py": {"chunk_count": 1, "mtime": 1.0},
                "core/b.py": {"chunk_count": 1, "mtime": 1.0},
            },
        }
        manifest_path = tmp_path / ".animus_ingest_manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            MagicMock(
                metadata={"file_path": "core/a.py", "chunk_type": "function"},
                created_at=datetime.now(),
            ),
            MagicMock(
                metadata={"file_path": "core/b.py", "chunk_type": "function"},
                created_at=datetime.now(),
            ),
        ]

        architect = ArchitectCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        obs = architect._observe_indexed_code_memory()
        coverage_obs = [
            o for o in obs if o.context.get("pattern_type") == "indexed_memory_coverage"
        ]
        assert len(coverage_obs) == 1
        assert coverage_obs[0].severity == "info"
        assert "100%" in coverage_obs[0].description

    def test_indexed_code_memory_recency_hotspot(self, tmp_path):
        """Recently indexed chunks surface active-development info."""
        manifest = {
            "version": "1.1",
            "summary": {"total_scanned_files": 1, "total_chunked_files": 1, "total_chunks": 2},
            "files": {"core/a.py": {"chunk_count": 2, "mtime": 1.0}},
        }
        manifest_path = tmp_path / ".animus_ingest_manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            MagicMock(
                metadata={"file_path": "core/a.py", "chunk_type": "function"},
                created_at=datetime.now(),
            ),
            MagicMock(
                metadata={"file_path": "core/a.py", "chunk_type": "function"},
                created_at=datetime.now(),
            ),
        ]

        architect = ArchitectCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        obs = architect._observe_indexed_code_memory()
        recency_obs = [o for o in obs if o.context.get("pattern_type") == "indexed_memory_recency"]
        assert len(recency_obs) == 1
        assert recency_obs[0].severity == "info"
        assert "core/a.py" in recency_obs[0].description

    def test_indexed_code_memory_complexity_hotspot(self, tmp_path):
        """High-complexity functions surfaced from pre-computed metadata."""
        manifest = {
            "version": "1.1",
            "summary": {"total_scanned_files": 1, "total_chunked_files": 1, "total_chunks": 1},
            "files": {"core/a.py": {"chunk_count": 1, "mtime": 1.0}},
        }
        manifest_path = tmp_path / ".animus_ingest_manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            MagicMock(
                metadata={
                    "file_path": "core/a.py",
                    "chunk_type": "function",
                    "name": "big_func",
                    "source_path": "core/a.py",
                    "start_line": 5,
                    "complexity_score": "15",
                },
                created_at=datetime.now(),
            ),
        ]

        architect = ArchitectCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        obs = architect._observe_indexed_code_memory()
        complexity_obs = [
            o for o in obs if o.context.get("pattern_type") == "indexed_memory_complexity"
        ]
        assert len(complexity_obs) == 1
        assert complexity_obs[0].severity == "medium"
        assert "big_func" in complexity_obs[0].description
        assert complexity_obs[0].context["complex_function_count"] == 1

    def test_indexed_code_memory_stale_index(self, tmp_path):
        """Files newer on disk than manifest trigger stale observation."""
        old = tmp_path / "old.py"
        old.write_text("x = 1\n")
        # File has fresh mtime (now); manifest claims mtime=1.0 → stale
        manifest = {
            "version": "1.1",
            "summary": {"total_scanned_files": 1, "total_chunked_files": 1, "total_chunks": 1},
            "files": {"old.py": {"chunk_count": 1, "mtime": 1.0}},
        }
        manifest_path = tmp_path / ".animus_ingest_manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            MagicMock(
                metadata={"file_path": "old.py", "chunk_type": "function"},
                created_at=datetime.now(),
            ),
        ]

        architect = ArchitectCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        obs = architect._observe_indexed_code_memory()
        stale_obs = [o for o in obs if o.context.get("pattern_type") == "indexed_memory_stale"]
        assert len(stale_obs) == 1
        assert stale_obs[0].severity == "medium"
        assert "old.py" in stale_obs[0].description

    def test_indexed_code_memory_configurable_thresholds(self, tmp_path):
        """Constructor thresholds override defaults."""
        manifest = {
            "version": "1.1",
            "summary": {"total_scanned_files": 4, "total_chunked_files": 1, "total_chunks": 1},
            "files": {"core/a.py": {"chunk_count": 1, "mtime": 1.0}},
        }
        manifest_path = tmp_path / ".animus_ingest_manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            MagicMock(
                metadata={"file_path": "core/a.py", "chunk_type": "function"},
                created_at=datetime.now(),
            ),
        ]

        # coverage=1/4=25% < default 50% → medium
        architect_default = ArchitectCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        obs_default = architect_default._observe_indexed_code_memory()
        assert any(
            o.severity == "medium"
            for o in obs_default
            if o.context.get("pattern_type") == "indexed_memory_coverage"
        )

        # coverage=1/4=25% > custom 20% threshold → info (not triggered as low)
        architect_custom = ArchitectCitizen(
            codebase_path=tmp_path,
            memory_layer=mock_memory,
            coverage_threshold=0.20,
        )
        obs_custom = architect_custom._observe_indexed_code_memory()
        cov_custom = [
            o for o in obs_custom if o.context.get("pattern_type") == "indexed_memory_coverage"
        ]
        assert len(cov_custom) == 1
        assert cov_custom[0].severity == "info"

    def test_get_indexed_code_chunks_focus_filter(self, tmp_path):
        """Focus paths filter chunks to matching file paths."""
        mock_memory = MagicMock()
        from datetime import datetime

        mock_memory.search.return_value = [
            MagicMock(
                metadata={"file_path": "core/a.py"},
                created_at=datetime.now(),
            ),
            MagicMock(
                metadata={"file_path": "other/b.py"},
                created_at=datetime.now(),
            ),
        ]

        architect = ArchitectCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        chunks = architect._get_indexed_code_chunks(focus_paths=["core"])
        assert len(chunks) == 1
        assert chunks[0].metadata["file_path"] == "core/a.py"

    def test_observe_codebase_calls_indexed_memory_when_memory_present(self, tmp_path):
        """observe_codebase triggers indexed memory observation when memory is attached."""
        manifest = {
            "version": "1.1",
            "summary": {"total_scanned_files": 0, "total_chunked_files": 0, "total_chunks": 0},
            "files": {},
        }
        manifest_path = tmp_path / ".animus_ingest_manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        mock_memory = MagicMock()
        mock_memory.search.return_value = []

        architect = ArchitectCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        # Patch heuristics and analyzer so they return empty
        with (
            patch.object(architect, "_get_analyzer", return_value=None),
            patch.object(architect, "_observe_heuristics", return_value=[]),
        ):
            obs = architect.observe_codebase()

        # The memory search should have been called for code_ingest
        calls = [
            c for c in mock_memory.search.call_args_list if c.kwargs.get("source") == "code_ingest"
        ]
        assert len(calls) >= 1


# ---------------------------------------------------------------------------
# ForgeCommissioner tests
# ---------------------------------------------------------------------------


class TestForgeCommissioner:
    def test_initialization(self):
        commissioner = ForgeCommissioner(codebase_path="/tmp/test")
        assert commissioner.codebase_path == Path("/tmp/test")
        assert commissioner.forge_host == "localhost"
        assert commissioner.forge_port == 8000

    def test_commission_rejects_unapproved_proposal(self, tmp_path):
        commissioner = ForgeCommissioner(codebase_path=tmp_path)
        commissioner._forge_available = False  # Skip health check
        proposal = ImprovementProposal(id="1", title="T", problem="P", status=ProposalStatus.DRAFT)

        result = commissioner.commission(proposal)
        assert result.success is False
        assert "not approved" in result.error

    def test_commission_simulated_when_forge_unavailable(self, tmp_path):
        commissioner = ForgeCommissioner(codebase_path=tmp_path)
        # Force forge unavailable
        commissioner._forge_available = False

        proposal = ImprovementProposal(
            id="1",
            title="T",
            problem="P",
            status=ProposalStatus.APPROVED,
            affected_components=["Mind"],
        )

        result = commissioner.commission(proposal)
        assert result.success is False
        assert result.stage_reached == "simulated"
        assert result.evidence_bundle["simulated"] is True
        assert "Forge unavailable" in result.error

    def test_commission_auto_approve_blocked_without_env(self, tmp_path):
        commissioner = ForgeCommissioner(codebase_path=tmp_path)
        proposal = ImprovementProposal(id="1", title="T", problem="P")

        with pytest.raises(RuntimeError, match="auto_approve=True is blocked"):
            commissioner.commission(proposal, auto_approve=True)

    @patch.dict("os.environ", {"ANIMUS_FORGE_ALLOW_AUTO_APPROVE": "1"})
    def test_commission_auto_approve_with_env(self, tmp_path):
        commissioner = ForgeCommissioner(codebase_path=tmp_path)
        commissioner._forge_available = False

        proposal = ImprovementProposal(
            id="1",
            title="T",
            problem="P",
            status=ProposalStatus.DRAFT,
            affected_components=["Mind"],
        )

        # Should not raise — auto_approve is allowed with env
        result = commissioner.commission(proposal, auto_approve=True)
        assert result.proposal_id == "1"

    def test_create_workflow_config(self, tmp_path):
        commissioner = ForgeCommissioner(codebase_path=tmp_path)
        proposal = ImprovementProposal(
            id="ADL-001",
            title="Refactor parser",
            problem="Parser is too complex",
            recommendation="Split into smaller functions",
            affected_components=["Factory"],
            success_metrics=["Tests pass", "Coverage stable"],
        )

        config = commissioner._create_workflow_config(proposal)
        assert config["name"] == "architect-ADL-001"
        assert config["description"] == "Refactor parser"
        assert len(config["agents"]) == 3
        assert config["agents"][0]["name"] == "analyzer"
        assert config["agents"][1]["name"] == "implementer"
        assert config["agents"][2]["name"] == "evaluator"
        assert config["budget"]["total_tokens"] == 200_000
        assert config["budget"]["max_cost_usd"] == 0.0

    def test_update_proposal_with_evidence_success(self, tmp_path):
        commissioner = ForgeCommissioner(codebase_path=tmp_path)
        proposal = ImprovementProposal(
            id="1", title="T", problem="P", status=ProposalStatus.APPROVED
        )
        result = CommissionResult(
            success=True,
            proposal_id="1",
            stage_reached="complete",
            tests_passed=True,
        )

        updated = commissioner.update_proposal_with_evidence(proposal, result)
        assert updated.status == ProposalStatus.COMPLETE
        assert updated.evidence_bundle["success"] is True

    def test_update_proposal_with_evidence_failure(self, tmp_path):
        commissioner = ForgeCommissioner(codebase_path=tmp_path)
        proposal = ImprovementProposal(
            id="1", title="T", problem="P", status=ProposalStatus.APPROVED
        )
        result = CommissionResult(
            success=False,
            proposal_id="1",
            stage_reached="testing",
            tests_passed=False,
            error="Tests failed",
        )

        updated = commissioner.update_proposal_with_evidence(proposal, result)
        assert updated.status == ProposalStatus.EVALUATING
        assert updated.evidence_bundle["success"] is False

    @patch("httpx.get")
    def test_check_forge_health(self, mock_get, tmp_path):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        commissioner = ForgeCommissioner(codebase_path=tmp_path)
        assert commissioner._check_forge() is True

    @patch("httpx.get")
    def test_check_forge_unhealthy(self, mock_get, tmp_path):
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_get.return_value = mock_response

        commissioner = ForgeCommissioner(codebase_path=tmp_path)
        assert commissioner._check_forge() is False

    def test_commission_local_engine_bypasses_http(self, tmp_path):
        commissioner = ForgeCommissioner(codebase_path=tmp_path, use_local_engine=True)

        # Mock _execute_local to avoid import errors
        mock_result = CommissionResult(
            success=True,
            proposal_id="1",
            stage_reached="complete",
            tests_passed=True,
        )
        commissioner._execute_local = MagicMock(return_value=mock_result)

        proposal = ImprovementProposal(
            id="1",
            title="T",
            problem="P",
            status=ProposalStatus.APPROVED,
            affected_components=["Mind"],
        )

        result = commissioner.commission(proposal)
        assert result.success is True
        assert result.stage_reached == "complete"
        commissioner._execute_local.assert_called_once_with(proposal)

    def test_execute_local_engine_unavailable(self, tmp_path):
        commissioner = ForgeCommissioner(codebase_path=tmp_path, use_local_engine=True)
        commissioner._get_local_engine = MagicMock(return_value=None)

        proposal = ImprovementProposal(
            id="1",
            title="T",
            problem="P",
            status=ProposalStatus.APPROVED,
            affected_components=["Mind"],
        )

        result = commissioner._execute_local(proposal)
        assert result.success is False
        assert "Local ForgeEngine not available" in result.error

    def test_execute_local_success(self, tmp_path):
        commissioner = ForgeCommissioner(codebase_path=tmp_path, use_local_engine=True)

        mock_engine = MagicMock()
        mock_engine.run.return_value = {
            "status": "success",
            "metrics": {"tokens_used": 1500},
        }
        commissioner._get_local_engine = MagicMock(return_value=mock_engine)

        proposal = ImprovementProposal(
            id="ADL-001",
            title="Refactor parser",
            problem="Parser is too complex",
            status=ProposalStatus.APPROVED,
            affected_components=["Factory"],
        )

        result = commissioner._execute_local(proposal)
        assert result.success is True
        assert result.stage_reached == "success"
        assert result.tests_passed is True
        assert result.benchmark_results == {"tokens_used": 1500}
        mock_engine.run.assert_called_once()


# ---------------------------------------------------------------------------
# ConversationDesignerCitizen tests
# ---------------------------------------------------------------------------


class TestConversationDesignerCitizen:
    def test_observe_repeated_prompts(self, tmp_path):
        log_dir = tmp_path / "conversations"
        log_dir.mkdir()
        log_file = log_dir / "session.jsonl"
        entries = [
            json.dumps({"prompt": "How do I configure the API?"}),
            json.dumps({"prompt": "Help me debug this error"}),
            json.dumps({"prompt": "How do I configure the API?"}),
            json.dumps({"prompt": "How do I configure the API?"}),
        ]
        log_file.write_text("\n".join(entries))

        designer = ConversationDesignerCitizen(conversation_log_dir=log_dir)
        observations = designer.observe_repeated_prompts()
        assert len(observations) >= 1
        assert observations[0].source == "conversation"
        assert "Repeated prompt detected" in observations[0].description
        assert observations[0].context["count"] >= 3

    def test_observe_vague_requests(self, tmp_path):
        log_dir = tmp_path / "conversations"
        log_dir.mkdir()
        log_file = log_dir / "session.jsonl"
        entries = [
            json.dumps({"prompt": "do something here"}),
            json.dumps({"prompt": "do something here"}),
            json.dumps({"prompt": "fix this"}),
        ]
        log_file.write_text("\n".join(entries))

        designer = ConversationDesignerCitizen(conversation_log_dir=log_dir)
        observations = designer.observe_vague_requests()
        assert len(observations) >= 1
        assert observations[0].source == "conversation"
        assert "Vague request detected" in observations[0].description
        assert observations[0].context["pattern_type"] == "vague_request"

    def test_observe_correction_loops(self, tmp_path):
        log_dir = tmp_path / "conversations"
        log_dir.mkdir()
        log_file = log_dir / "session.jsonl"
        entries = [
            json.dumps({"prompt": "no, that's wrong"}),
            json.dumps({"prompt": "actually, I meant something else"}),
            json.dumps({"prompt": "not quite right"}),
        ]
        log_file.write_text("\n".join(entries))

        designer = ConversationDesignerCitizen(conversation_log_dir=log_dir)
        observations = designer.observe_correction_loops()
        assert len(observations) >= 1
        assert observations[0].source == "conversation"
        assert "Correction loop detected" in observations[0].description
        assert observations[0].context["pattern_type"] == "correction_loop"

    def test_generate_proposal(self, tmp_path):
        log_dir = tmp_path / "conversations"
        log_dir.mkdir()
        log_file = log_dir / "session.jsonl"
        entries = [
            json.dumps({"prompt": "How do I configure the API?"}),
            json.dumps({"prompt": "How do I configure the API?"}),
            json.dumps({"prompt": "How do I configure the API?"}),
        ]
        log_file.write_text("\n".join(entries))

        designer = ConversationDesignerCitizen(conversation_log_dir=log_dir)
        proposal = designer.generate_proposal()
        assert proposal is not None
        assert isinstance(proposal, ImprovementProposal)
        assert proposal.status == ProposalStatus.DRAFT
        assert len(proposal.evidence) >= 1

    def test_generate_proposal_no_findings(self, tmp_path):
        designer = ConversationDesignerCitizen(conversation_log_dir=tmp_path / "empty")
        proposal = designer.generate_proposal()
        assert proposal is None

    def test_generate_proposal_focus_pattern(self, tmp_path):
        log_dir = tmp_path / "conversations"
        log_dir.mkdir()
        log_file = log_dir / "session.jsonl"
        # Mix of repeated prompts (low severity, freq=3) and vague requests (medium, freq=2)
        entries = [
            json.dumps({"prompt": "commit and push"}),
            json.dumps({"prompt": "commit and push"}),
            json.dumps({"prompt": "commit and push"}),
            json.dumps({"prompt": "do something here"}),
            json.dumps({"prompt": "do something here"}),
        ]
        log_file.write_text("\n".join(entries))

        designer = ConversationDesignerCitizen(conversation_log_dir=log_dir)
        # Default should pick vague_request (medium severity > low severity)
        default_proposal = designer.generate_proposal()
        assert default_proposal is not None

        # Focused should pick repeated_prompt regardless of severity
        focused_proposal = designer.generate_proposal(focus_pattern="repeated_prompt")
        assert focused_proposal is not None
        assert "commit and push" in focused_proposal.problem.lower()

    def test_store_proposal_with_memory(self, tmp_path):
        mock_memory = MagicMock()
        designer = ConversationDesignerCitizen(memory_layer=mock_memory)
        proposal = ImprovementProposal(id="1", title="Test", problem="P", recommendation="R")
        assert designer.store_proposal(proposal) is True
        mock_memory.remember.assert_called_once()

    def test_store_proposal_without_memory(self, tmp_path):
        designer = ConversationDesignerCitizen()
        proposal = ImprovementProposal(id="1", title="Test", problem="P", recommendation="R")
        assert designer.store_proposal(proposal) is False


# ---------------------------------------------------------------------------
# KnowledgeCuratorCitizen tests
# ---------------------------------------------------------------------------


class TestKnowledgeCuratorCitizen:
    def test_observe_stale_references_no_memory(self, tmp_path):
        curator = KnowledgeCuratorCitizen(codebase_path=tmp_path)
        observations = curator.observe_stale_references()
        assert len(observations) == 1
        assert "Memory layer not available" in observations[0].description

    def test_observe_stale_references_with_mock(self, tmp_path):
        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            {"content": "See main.py for details", "id": "mem1"},
        ]
        curator = KnowledgeCuratorCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        observations = curator.observe_stale_references()
        assert len(observations) >= 1
        assert observations[0].source == "knowledge"
        assert observations[0].context["pattern_type"] == "stale_reference"

    def test_observe_contradictions(self, tmp_path):
        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            {"content": "ModuleA is fast and improves performance", "id": "mem1"},
            {"content": "ModuleA is slow and breaks things", "id": "mem2"},
        ]
        curator = KnowledgeCuratorCitizen(memory_layer=mock_memory)
        observations = curator.observe_contradictions()
        assert len(observations) >= 1
        assert observations[0].source == "knowledge"
        assert "Contradictory claims" in observations[0].description
        assert observations[0].context["pattern_type"] == "contradiction"

    def test_observe_outdated_claims(self, tmp_path):
        mock_memory = MagicMock()
        old_date = (datetime.now() - timedelta(days=100)).isoformat()
        mock_memory.search.return_value = [
            {
                "content": "CCP recently changed the SSO scopes",
                "id": "mem1",
                "created_at": old_date,
            },
        ]
        curator = KnowledgeCuratorCitizen(memory_layer=mock_memory)
        observations = curator.observe_outdated_claims()
        assert len(observations) >= 1
        assert observations[0].source == "knowledge"
        assert observations[0].context["pattern_type"] == "outdated_claim"

    def test_observe_orphan_topics(self, tmp_path):
        topics_dir = tmp_path / "topics"
        topics_dir.mkdir()
        orphan = topics_dir / "orphan.md"
        linked = topics_dir / "linked.md"
        index = topics_dir / "index.md"
        orphan.write_text("# Orphan Topic\n")
        linked.write_text("# Linked Topic\n[index](index.md)\n")
        index.write_text("[Linked Topic](linked.md)\n")

        curator = KnowledgeCuratorCitizen(codebase_path=tmp_path)
        observations = curator.observe_orphan_topics()
        assert len(observations) == 1
        assert observations[0].context["pattern_type"] == "orphan_topic"
        assert "orphan.md" in observations[0].description

    def test_generate_proposal(self, tmp_path):
        mock_memory = MagicMock()
        old_date = (datetime.now() - timedelta(days=100)).isoformat()
        mock_memory.search.return_value = [
            {
                "content": "CCP recently changed the SSO scopes",
                "id": "mem1",
                "created_at": old_date,
            },
        ]
        curator = KnowledgeCuratorCitizen(memory_layer=mock_memory)
        proposal = curator.generate_proposal()
        assert proposal is not None
        assert isinstance(proposal, ImprovementProposal)
        assert proposal.status == ProposalStatus.DRAFT
        assert len(proposal.evidence) >= 1

    def test_generate_proposal_no_findings(self, tmp_path):
        mock_memory = MagicMock()
        mock_memory.search.return_value = []
        curator = KnowledgeCuratorCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        proposal = curator.generate_proposal()
        assert proposal is None

    def test_store_proposal_with_memory(self, tmp_path):
        mock_memory = MagicMock()
        curator = KnowledgeCuratorCitizen(memory_layer=mock_memory)
        proposal = ImprovementProposal(id="1", title="Test", problem="P", recommendation="R")
        assert curator.store_proposal(proposal) is True
        mock_memory.remember.assert_called_once()

    def test_store_proposal_without_memory(self, tmp_path):
        curator = KnowledgeCuratorCitizen()
        proposal = ImprovementProposal(id="1", title="Test", problem="P", recommendation="R")
        assert curator.store_proposal(proposal) is False


# ---------------------------------------------------------------------------
# TestOracleCitizen tests
# ---------------------------------------------------------------------------


class TestTestOracleCitizen:
    def test_observe_test_failures(self, tmp_path):
        pytest_output = (
            "test_foo.py::test_a PASSED\n"
            "FAILED test_foo.py::test_b\n"
            "FAILED test_bar.py::test_c\n"
            "2 failed, 1 passed in 0.5s\n"
        )
        oracle = TestOracleCitizen(codebase_path=tmp_path)
        observations = oracle.observe_test_failures(pytest_output=pytest_output)
        assert len(observations) >= 1
        assert any(o.context.get("pattern_type") == "test_failure" for o in observations)

    def test_observe_coverage_gaps(self, tmp_path):
        coverage_report = (
            "Name         Stmts   Miss  Cover\n"
            "--------------------------------\n"
            "main.py         10      0     0%\n"
            "utils.py         5      0   100%\n"
            "--------------------------------\n"
            "TOTAL           15     10    33%\n"
        )
        oracle = TestOracleCitizen(codebase_path=tmp_path)
        observations = oracle.observe_coverage_gaps(coverage_report=coverage_report)
        assert len(observations) >= 1
        assert any(
            o.context.get("pattern_type") in ("coverage_drop", "missing_coverage")
            for o in observations
        )

    def test_observe_eval_drift(self, tmp_path):
        eval_results = [
            {"suite": "suite_a", "score": 0.9, "timestamp": "2026-01-01T00:00:00Z"},
            {"suite": "suite_a", "score": 0.7, "timestamp": "2026-01-02T00:00:00Z"},
        ]
        oracle = TestOracleCitizen(codebase_path=tmp_path)
        observations = oracle.observe_eval_drift(eval_results=eval_results)
        assert len(observations) == 1
        assert observations[0].context["pattern_type"] == "eval_drift"
        assert observations[0].context["delta"] == pytest.approx(-0.2)

    def test_generate_proposal(self, tmp_path):
        (tmp_path / "pytest-output.txt").write_text(
            "test_foo.py::test_a FAILED\n1 failed, 0 passed in 0.5s\n"
        )
        (tmp_path / "coverage.txt").write_text(
            "Name         Stmts   Miss  Cover\n"
            "--------------------------------\n"
            "main.py         10      0     0%\n"
            "--------------------------------\n"
            "TOTAL           15     10    33%\n"
        )
        oracle = TestOracleCitizen(codebase_path=tmp_path)
        proposal = oracle.generate_proposal()
        assert proposal is not None
        assert isinstance(proposal, ImprovementProposal)
        assert proposal.status == ProposalStatus.DRAFT

    def test_generate_proposal_no_findings(self, tmp_path):
        oracle = TestOracleCitizen(codebase_path=tmp_path)
        proposal = oracle.generate_proposal()
        assert proposal is None

    def test_store_proposal_with_memory(self, tmp_path):
        mock_memory = MagicMock()
        oracle = TestOracleCitizen(codebase_path=tmp_path, memory_layer=mock_memory)
        proposal = ImprovementProposal(id="1", title="Test", problem="P", recommendation="R")
        assert oracle.store_proposal(proposal) is True
        mock_memory.remember.assert_called_once()

    def test_store_proposal_without_memory(self, tmp_path):
        oracle = TestOracleCitizen(codebase_path=tmp_path)
        proposal = ImprovementProposal(id="1", title="Test", problem="P", recommendation="R")
        assert oracle.store_proposal(proposal) is False


# ---------------------------------------------------------------------------
# ProposalQueue tests
# ---------------------------------------------------------------------------


class TestProposalQueue:
    def test_submit_approve_commission_complete_lifecycle(self, tmp_path):
        queue = ProposalQueue(storage_path=str(tmp_path / "queue.json"))
        proposal = ImprovementProposal(id="ADL-001", title="T", problem="P")

        qp = queue.submit(proposal)
        assert qp.current_status == ProposalStatus.SUBMITTED
        assert queue.stats()["total"] == 1

        approved = queue.approve("ADL-001", actor="human", reason="LGTM")
        assert approved.current_status == ProposalStatus.APPROVED
        assert approved.proposal.approved_by == "human"

        commissioned = queue.commission("ADL-001", actor="forge")
        assert commissioned.current_status == ProposalStatus.COMMISSIONED

        completed = queue.complete("ADL-001", actor="forge")
        assert completed.current_status == ProposalStatus.COMPLETE
        assert queue.stats()["complete"] == 1

    def test_reject_path(self, tmp_path):
        queue = ProposalQueue(storage_path=str(tmp_path / "queue.json"))
        proposal = ImprovementProposal(id="ADL-002", title="T", problem="P")
        queue.submit(proposal)

        rejected = queue.reject("ADL-002", actor="human", reason="Not now")
        assert rejected.current_status == ProposalStatus.REJECTED
        assert queue.stats()["rejected"] == 1

        # Rejecting again should be no-op
        rejected_again = queue.reject("ADL-002", actor="human", reason="Still no")
        assert rejected_again.current_status == ProposalStatus.REJECTED

    def test_persistence_roundtrip(self, tmp_path):
        storage = tmp_path / "queue.json"
        queue = ProposalQueue(storage_path=str(storage))
        proposal = ImprovementProposal(id="ADL-003", title="T", problem="P", recommendation="R")
        queue.submit(proposal, priority=3, tags=["architect", "urgent"])
        queue.approve("ADL-003")

        # Load into fresh queue
        queue2 = ProposalQueue(storage_path=str(storage))
        queue2.load_from_memory()
        loaded = queue2.get("ADL-003")
        assert loaded is not None
        assert loaded.current_status == ProposalStatus.APPROVED
        assert loaded.priority == 3
        assert "architect" in loaded.tags

    def test_stats(self, tmp_path):
        queue = ProposalQueue(storage_path=str(tmp_path / "queue.json"))
        p1 = ImprovementProposal(id="p1", title="T1", problem="P1")
        p2 = ImprovementProposal(id="p2", title="T2", problem="P2")
        p3 = ImprovementProposal(id="p3", title="T3", problem="P3")

        queue.submit(p1)
        queue.submit(p2)
        queue.approve("p2")
        queue.submit(p3)
        queue.complete("p3")

        stats = queue.stats()
        assert stats["total"] == 3
        assert stats["pending"] == 1
        assert stats["approved"] == 1
        assert stats["complete"] == 1
        assert stats["rejected"] == 0


# ---------------------------------------------------------------------------
# CitizenCouncil tests
# ---------------------------------------------------------------------------


class TestCitizenCouncil:
    def test_collect_from_memory(self, tmp_path):
        mock_memory = MagicMock()
        proposal_dict = ImprovementProposal(
            id="ADL-001",
            title="T1",
            problem="P1",
            recommendation="R1",
            affected_components=["Factory"],
        ).to_dict()
        mock_memory.search.return_value = [
            {
                "content": "proposal 1",
                "metadata": proposal_dict,
            }
        ]

        council = CitizenCouncil(memory_layer=mock_memory)
        count = council.collect_from_memory(citizen_names=["architect"])
        assert count == 1
        assert "ADL-001" in council._proposals

    def test_collect_from_memory_includes_intelligence(self, tmp_path):
        """Verify that intelligence proposals are collected by default."""
        mock_memory = MagicMock()
        intel_proposal = ImprovementProposal(
            id="INTEL-20260712-123456",
            title="Secret Detected",
            problem="AWS key exposed",
            recommendation="Rotate credentials",
            affected_components=["Security"],
        ).to_dict()

        def _search(query, **kwargs):
            if "intelligence" in query:
                return [{"content": "intelligence proposal", "metadata": intel_proposal}]
            return []

        mock_memory.search.side_effect = _search

        council = CitizenCouncil(memory_layer=mock_memory)
        # Default citizen_names should include "intelligence"
        count = council.collect_from_memory()
        assert count == 1
        assert "INTEL-20260712-123456" in council._proposals
        rp = council._proposals["INTEL-20260712-123456"]
        assert "intelligence" in rp.source_citizens

    def test_rank_backlog_scoring(self, tmp_path):
        council = CitizenCouncil()
        p1 = ImprovementProposal(
            id="p1",
            title="High severity",
            problem="P1",
            confidence_score=0.9,
            estimated_effort_hours=2.0,
            affected_components=["Factory"],
            evidence=[EvidenceItem(source="test", description="Critical issue")],
        )
        p2 = ImprovementProposal(
            id="p2",
            title="Low severity",
            problem="P2",
            confidence_score=0.3,
            estimated_effort_hours=8.0,
            affected_components=["Kernel"],
        )
        council._add_proposal(p1, source="architect")
        council._add_proposal(p2, source="test_oracle")

        ranked = council.rank_backlog(deduplicate=False)
        assert len(ranked) == 2
        assert ranked[0].proposal.id == "p1"
        assert ranked[0].rank == 1
        assert ranked[0].priority_score > ranked[1].priority_score

    def test_deduplication_by_component_overlap(self, tmp_path):
        council = CitizenCouncil()
        p1 = ImprovementProposal(
            id="p1",
            title="First",
            problem="P1",
            confidence_score=0.9,
            estimated_effort_hours=1.0,
            affected_components=["Factory", "Kernel"],
        )
        p2 = ImprovementProposal(
            id="p2",
            title="Second",
            problem="P2",
            confidence_score=0.8,
            estimated_effort_hours=1.0,
            affected_components=["Factory", "Mind"],
        )
        council._add_proposal(p1, source="architect")
        council._add_proposal(p2, source="conversation_designer")

        ranked = council.rank_backlog(deduplicate=True)
        assert len(ranked) == 1
        assert ranked[0].duplicates == ["p2"]


# ---------------------------------------------------------------------------
# IntelligenceCitizen tests
# ---------------------------------------------------------------------------


class TestIntelligenceCitizen:
    def test_initialization(self):
        intel = IntelligenceCitizen()
        assert intel.memory is None
        assert intel.evidence_dir is None

    def test_extract_entities(self):
        intel = IntelligenceCitizen()
        text = (
            "Contact alice@example.com or visit https://github.com/test "
            "Server at 192.168.1.1 MD5: aabbccdd11223344556677889900aabb "
            "Reach us at +1-555-123-4567"
        )
        entities = intel.extract_entities(text)
        assert "alice@example.com" in entities.emails
        assert any("github.com/test" in u for u in entities.urls)
        assert "192.168.1.1" in entities.ipv4_addresses
        assert "aabbccdd11223344556677889900aabb" in entities.md5_hashes
        assert entities.total_count() > 0

    def test_extract_entities_empty_text(self):
        intel = IntelligenceCitizen()
        entities = intel.extract_entities("")
        assert entities.is_empty()

    def test_scan_secrets(self):
        intel = IntelligenceCitizen()
        text = "API key: AKIAIOSFODNN7EXAMPLE and github token: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        findings = intel.scan_secrets(text)
        assert len(findings) >= 2
        patterns = {f.pattern_name for f in findings}
        assert "aws_access_key" in patterns
        assert "github_token" in patterns

    def test_scan_secrets_empty_text(self):
        intel = IntelligenceCitizen()
        findings = intel.scan_secrets("")
        assert findings == []

    def test_scan_file_secrets(self, tmp_path):
        intel = IntelligenceCitizen()
        test_file = tmp_path / "config.py"
        test_file.write_text("API_KEY = 'AKIAIOSFODNN7EXAMPLE'\n")

        findings = intel.scan_file_secrets(test_file)
        assert len(findings) == 1
        assert findings[0].pattern_name == "aws_access_key"
        assert findings[0].line_number == 1

    def test_generate_profile_urls(self):
        intel = IntelligenceCitizen()
        profiles = intel.generate_profile_urls("octocat")
        assert len(profiles) > 0

        github = next((p for p in profiles if p.platform == "GitHub"), None)
        assert github is not None
        assert github.url == "https://github.com/octocat"
        assert github.category == "code"

    def test_generate_profile_urls_invalid_username(self):
        intel = IntelligenceCitizen()
        # Twitter max_length = 15, so 20-char username should be skipped
        profiles = intel.generate_profile_urls("a" * 20)
        twitter = next((p for p in profiles if p.platform == "Twitter/X"), None)
        assert twitter is None

    def test_extract_usernames(self):
        intel = IntelligenceCitizen()
        text = "Follow @octocat and check github.com/testuser for more."
        usernames = intel.extract_usernames(text)
        assert "octocat" in usernames
        assert "testuser" in usernames

    def test_generate_osint_report(self):
        intel = IntelligenceCitizen()
        text = (
            "Developer @johndoe uses AWS key AKIAIOSFODNN7EXAMPLE. "
            "Visit https://github.com/johndoe for code."
        )
        report = intel.generate_osint_report(text)
        assert report.extracted.total_count() > 0
        assert len(report.secrets) > 0
        assert len(report.profiles) > 0
        assert "secret(s) detected" in report.summary or "entities" in report.summary

    def test_analyze_text(self):
        intel = IntelligenceCitizen()
        text = "Email: admin@example.com"
        report = intel.analyze(text=text)
        assert "admin@example.com" in report.extracted.emails

    def test_analyze_no_input(self):
        intel = IntelligenceCitizen()
        report = intel.analyze()
        assert report.summary == "No input provided"

    def test_generate_proposal_from_critical_secrets(self):
        intel = IntelligenceCitizen()
        report = intel.generate_osint_report("AWS key: AKIAIOSFODNN7EXAMPLE")
        proposal = intel.generate_proposal(report)
        assert proposal is not None
        assert "INTEL-" in proposal.id
        assert "critical" in proposal.problem.lower()
        assert proposal.confidence_score == 0.85

    def test_generate_proposal_no_actionable_findings(self):
        intel = IntelligenceCitizen()
        report = intel.generate_osint_report("Just some harmless text here.")
        proposal = intel.generate_proposal(report)
        assert proposal is None

    def test_proposal_from_high_secrets(self):
        intel = IntelligenceCitizen()
        report = intel.generate_osint_report("Generic API key: api_key=xxxxxxxxxxxxxxxxxxxx")
        proposal = intel.generate_proposal(report)
        assert proposal is not None
        assert "high" in proposal.problem.lower()

    def test_store_report_without_memory(self):
        intel = IntelligenceCitizen()
        report = intel.generate_osint_report("test")
        result = intel.store_report(report)
        assert result is False

    def test_store_proposal_without_memory(self):
        intel = IntelligenceCitizen()
        report = intel.generate_osint_report("AWS key: AKIAIOSFODNN7EXAMPLE")
        proposal = intel.generate_proposal(report)
        assert proposal is not None
        result = intel.store_proposal(proposal)
        assert result is False


# ---------------------------------------------------------------------------
# Intelligence CLI tests
# ---------------------------------------------------------------------------


class TestIntelligenceCli:
    """Test animus intelligence CLI subcommands via _cmd_intelligence."""

    def test_cli_extract(self, capsys):
        from argparse import Namespace

        from animus.cli import _cmd_intelligence

        args = Namespace(intel_command="extract", text="Email: alice@example.com", file="")
        ret = _cmd_intelligence(args)
        assert ret == 0
        captured = capsys.readouterr()
        assert "alice@example.com" in captured.out
        assert "Emails" in captured.out

    def test_cli_extract_no_input(self, capsys):
        from argparse import Namespace

        from animus.cli import _cmd_intelligence

        args = Namespace(intel_command="extract", text="", file="")
        ret = _cmd_intelligence(args)
        assert ret == 1
        captured = capsys.readouterr()
        assert "Provide --text or --file" in captured.err

    def test_cli_secrets(self, capsys):
        from argparse import Namespace

        from animus.cli import _cmd_intelligence

        args = Namespace(intel_command="secrets", text="AWS_KEY=AKIAIOSFODNN7EXAMPLE", file="")
        ret = _cmd_intelligence(args)
        assert ret == 0
        captured = capsys.readouterr()
        assert "AWS Access Key ID" in captured.out
        assert "CRITICAL" in captured.out

    def test_cli_secrets_empty(self, capsys):
        from argparse import Namespace

        from animus.cli import _cmd_intelligence

        args = Namespace(intel_command="secrets", text="safe text", file="")
        ret = _cmd_intelligence(args)
        assert ret == 0
        captured = capsys.readouterr()
        assert "No secrets detected" in captured.out

    def test_cli_osint(self, capsys):
        from argparse import Namespace

        from animus.cli import _cmd_intelligence

        args = Namespace(intel_command="osint", username="octocat")
        ret = _cmd_intelligence(args)
        assert ret == 0
        captured = capsys.readouterr()
        assert "GitHub" in captured.out
        assert "octocat" in captured.out

    def test_cli_analyze(self, capsys):
        from argparse import Namespace

        from animus.cli import _cmd_intelligence

        args = Namespace(
            intel_command="analyze",
            text="Email: admin@example.com",
            file="",
            store=False,
        )
        ret = _cmd_intelligence(args)
        assert ret == 0
        captured = capsys.readouterr()
        assert "Intelligence Report" in captured.out
        assert "Entities" in captured.out
        assert "emails: 1" in captured.out

    def test_cli_analyze_no_input(self, capsys):
        from argparse import Namespace

        from animus.cli import _cmd_intelligence

        args = Namespace(intel_command="analyze", text="", file="", store=False)
        ret = _cmd_intelligence(args)
        assert ret == 1
        captured = capsys.readouterr()
        assert "Provide --text or --file" in captured.err


# ---------------------------------------------------------------------------
# HarvesterCitizen tests
# ---------------------------------------------------------------------------


class TestHarvesterCitizen:
    def test_initialization(self):
        harvester = HarvesterCitizen(codebase_path="/tmp/test")
        assert harvester.codebase_path == Path("/tmp/test")
        assert harvester._harvested == []

    def test_harvest_text(self):
        harvester = HarvesterCitizen()
        source = harvester.harvest_text("Hello world", source_type="document", identifier="doc1")
        assert source.source_type == "document"
        assert source.identifier == "doc1"
        assert source.title == "Hello world"
        assert source.content_snippet == "Hello world"
        assert source.confidence == 0.5

    def test_harvest_file(self, tmp_path):
        harvester = HarvesterCitizen()
        doc = tmp_path / "test.md"
        doc.write_text("# Test Document\nThis is a test.")
        source = harvester.harvest_file(doc)
        assert source is not None
        assert source.source_type == "document"
        assert source.title == "test.md"
        assert "# Test Document" in source.content_snippet

    def test_harvest_file_not_found(self, tmp_path):
        harvester = HarvesterCitizen()
        source = harvester.harvest_file(tmp_path / "nonexistent.txt")
        assert source is None

    def test_deduplicate(self):
        harvester = HarvesterCitizen()
        s1 = harvester.harvest_text("Alpha", identifier="doc1")
        s2 = harvester.harvest_text(
            "Alpha", identifier="doc1"
        )  # Same type + identifier + title → duplicate
        s3 = harvester.harvest_text("Gamma", identifier="doc2")
        result = harvester.deduplicate([s1, s2, s3])
        assert len(result) == 2
        identifiers = {s.identifier for s in result}
        assert identifiers == {"doc1", "doc2"}

    def test_observe_codebase(self, tmp_path):
        harvester = HarvesterCitizen(codebase_path=tmp_path)
        py_file = tmp_path / "main.py"
        py_file.write_text("# TODO: refactor this\n# FIXME: bug here\nprint('hello')\n")
        findings = harvester.observe_codebase()
        assert len(findings) >= 1
        assert any("TODO" in f["description"] for f in findings)

    def test_observe_codebase_with_document(self, tmp_path):
        harvester = HarvesterCitizen(codebase_path=tmp_path)
        md_file = tmp_path / "readme.md"
        md_file.write_text("# README\n" + "word " * 100)
        findings = harvester.observe_codebase()
        doc_findings = [
            f for f in findings if f["context"].get("pattern_type") == "document_source"
        ]
        assert len(doc_findings) >= 1
        assert "readme.md" in doc_findings[0]["description"]

    def test_observe_memory_no_memory(self):
        harvester = HarvesterCitizen()
        sources = harvester.observe_memory()
        assert sources == []

    def test_observe_memory_with_mock(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            {
                "content": "Architecture note: use separation of concerns",
                "id": "mem1",
                "metadata": {"topic": "architecture"},
            },
        ]
        harvester = HarvesterCitizen(memory_layer=mock_memory)
        sources = harvester.observe_memory()
        assert len(sources) >= 1
        assert sources[0].source_type == "memory"

    def test_generate_proposal_no_sources(self):
        harvester = HarvesterCitizen()
        proposal = harvester.generate_proposal([])
        assert proposal is None

    def test_generate_proposal_from_sources(self):
        harvester = HarvesterCitizen()
        sources = [
            harvester.harvest_text(
                "Repo analysis of fastapi", source_type="repo", identifier="fastapi/fastapi"
            ),
        ]
        proposal = harvester.generate_proposal(sources)
        assert proposal is not None
        assert "HARV-" in proposal.id
        assert "ResearchGuild" in proposal.affected_components
        assert len(proposal.evidence) >= 1

    def test_store_source_without_memory(self):
        harvester = HarvesterCitizen()
        source = harvester.harvest_text("test")
        assert harvester.store_source(source) is False

    def test_store_source_with_memory(self):
        mock_memory = MagicMock()
        harvester = HarvesterCitizen(memory_layer=mock_memory)
        source = harvester.harvest_text("test")
        assert harvester.store_source(source) is True
        mock_memory.remember.assert_called_once()

    def test_store_proposal_with_memory(self):
        mock_memory = MagicMock()
        harvester = HarvesterCitizen(memory_layer=mock_memory)
        proposal = ImprovementProposal(id="1", title="Test", problem="P", recommendation="R")
        assert harvester.store_proposal(proposal) is True
        mock_memory.remember.assert_called_once()

    def test_list_stored_sources(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            {
                "content": "harvested text",
                "id": "mem1",
                "metadata": {"title": "Test Source", "source_type": "text"},
            },
        ]
        harvester = HarvesterCitizen(memory_layer=mock_memory)
        sources = harvester.list_stored_sources(limit=10)
        assert len(sources) == 1
        assert sources[0]["metadata"]["title"] == "Test Source"


# ---------------------------------------------------------------------------
# Harvester CLI tests
# ---------------------------------------------------------------------------


class TestHarvesterCli:
    def test_cli_harvest_no_target(self, capsys):
        from argparse import Namespace

        from animus.cli import _cmd_harvester

        args = Namespace(
            harvester_command="harvest",
            target="",
            depth="quick",
            store=False,
        )
        ret = _cmd_harvester(args)
        assert ret == 1
        captured = capsys.readouterr()
        assert "Provide --target" in captured.err

    def test_cli_sources(self, capsys):
        from argparse import Namespace

        from animus.cli import _cmd_harvester

        args = Namespace(
            harvester_command="sources",
            limit=10,
        )
        ret = _cmd_harvester(args)
        assert ret == 0
        captured = capsys.readouterr()
        assert "Stored Harvested Sources" in captured.out

    def test_cli_analyze(self, capsys, tmp_path):
        from argparse import Namespace

        from animus.cli import _cmd_harvester

        # Create a file with TODO for observe_codebase to find
        py_file = tmp_path / "test_module.py"
        py_file.write_text("# TODO: refactor\nprint('hello')\n")

        args = Namespace(
            harvester_command="analyze",
            codebase_path=str(tmp_path),
            store=False,
        )
        ret = _cmd_harvester(args)
        assert ret == 0
        captured = capsys.readouterr()
        assert "Harvester Observation Sweep" in captured.out


# ---------------------------------------------------------------------------
# MCP tool tests
# ---------------------------------------------------------------------------


class TestHarvesterMcpTools:
    @pytest.fixture
    def mcp_server(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANIMUS_DATA_DIR", str(tmp_path / "mcp-data"))
        monkeypatch.setenv("ANIMUS_MEMORY_BACKEND", "json")
        pytest.importorskip("mcp")
        from animus.mcp_server import create_mcp_server

        return create_mcp_server()

    def test_harvester_tools_exist(self, mcp_server):
        tools = list(mcp_server._tools.keys())
        assert "animus_harvester_scan" in tools
        assert "animus_harvester_watchlist_scan" in tools
        assert "animus_harvester_list_sources" in tools

    def test_harvester_scan_mocked(self, mcp_server, tmp_path, monkeypatch):

        def _mock_harvest_repo(*, target, compare, depth):
            from animus.lugh.repos import HarvestResult

            return HarvestResult(
                repo=target,
                score=75,
                architecture="Clean architecture with separation of concerns",
                notable_patterns=["dependency injection"],
                tools_worth_adopting=["pytest"],
            )

        monkeypatch.setattr(
            "animus.lugh.repos.harvest_repo",
            _mock_harvest_repo,
        )

        result = mcp_server._tools["animus_harvester_scan"].fn(
            target="fastapi/fastapi",
            depth="quick",
            store_source=False,
        )
        assert "Harvester Scan Result" in result
        assert "fastapi/fastapi" in result

    def test_harvester_list_sources_empty(self, mcp_server):
        result = mcp_server._tools["animus_harvester_list_sources"].fn(
            limit=10,
        )
        assert isinstance(result, str) and len(result) > 0

    def test_harvester_watchlist_scan_empty(self, mcp_server):
        result = mcp_server._tools["animus_harvester_watchlist_scan"].fn(
            interval_hours=0,
            store_report=False,
        )
        assert "Watchlist Scan Report" in result


# ---------------------------------------------------------------------------
# AbstractionCitizen tests (Research Guild — Citizen 008)
# ---------------------------------------------------------------------------


class TestAbstractionCitizen:
    def test_initialization(self):
        citizen = AbstractionCitizen()
        assert citizen.codebase_path == Path(".").expanduser()
        assert citizen.memory is None

    def test_strip_implementation_basic(self):
        citizen = AbstractionCitizen()
        text = "Use Redis for caching"
        result = citizen.strip_implementation(text)
        assert "[TECH]" in result
        assert "Redis" not in result

    def test_strip_implementation_multiple_techs(self):
        citizen = AbstractionCitizen()
        text = "Deploy with Kubernetes and monitor via Prometheus"
        result = citizen.strip_implementation(text)
        assert result.count("[TECH]") == 2

    def test_extract_mechanisms_cache(self):
        citizen = AbstractionCitizen()
        source = "Use Redis cache with TTL and LRU eviction"
        mechanisms = citizen.extract_mechanisms(source, "src1")
        names = [m.name for m in mechanisms]
        assert "caching layer" in names

    def test_extract_mechanisms_async_comm(self):
        citizen = AbstractionCitizen()
        source = "Use message queues for async communication with retry"
        mechanisms = citizen.extract_mechanisms(source, "src2")
        names = [m.name for m in mechanisms]
        assert "asynchronous communication" in names
        assert "fault tolerance" in names

    def test_extract_mechanisms_fault_tolerance(self):
        citizen = AbstractionCitizen()
        source = "Circuit breaker pattern for fault tolerance with exponential backoff"
        mechanisms = citizen.extract_mechanisms(source, "src3")
        names = [m.name for m in mechanisms]
        assert "fault tolerance" in names

    def test_extract_mechanisms_observability(self):
        citizen = AbstractionCitizen()
        source = "Enable telemetry and span collection for monitoring"
        mechanisms = citizen.extract_mechanisms(source, "src4")
        names = [m.name for m in mechanisms]
        assert "observability" in names

    def test_extract_mechanisms_no_match(self):
        citizen = AbstractionCitizen()
        source = "The quick brown fox jumps over the lazy dog"
        mechanisms = citizen.extract_mechanisms(source, "src5")
        assert mechanisms == []

    def test_mechanism_card_fields(self):
        citizen = AbstractionCitizen()
        source = "Use Redis for caching with TTL"
        mechanisms = citizen.extract_mechanisms(source, "src6")
        assert mechanisms
        m = mechanisms[0]
        assert m.name
        assert m.description
        assert m.category
        assert m.confidence > 0
        assert "src6" in m.source_provenance

    def test_generate_proposal_with_mechanisms(self):
        citizen = AbstractionCitizen()
        mechanisms = citizen.extract_mechanisms("Circuit breaker for fault tolerance", "src")
        proposal = citizen.generate_proposal(mechanisms)
        assert proposal is not None
        assert "mechanism" in proposal.title.lower()
        assert proposal.confidence_score > 0

    def test_generate_proposal_empty_mechanisms(self):
        citizen = AbstractionCitizen()
        proposal = citizen.generate_proposal([])
        assert proposal is None

    def test_observe_codebase_returns_list(self):
        citizen = AbstractionCitizen(codebase_path=".")
        obs = citizen.observe_codebase()
        assert isinstance(obs, list)

    def test_store_and_list_mechanisms(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            {
                "id": "m1",
                "content": "caching layer: Separate read-heavy data",
                "metadata": {"name": "caching layer", "category": "performance"},
            }
        ]
        citizen = AbstractionCitizen(memory_layer=mock_memory)
        mechanisms = citizen.extract_mechanisms("Use Redis for caching with TTL", "src7")
        assert mechanisms
        stored = citizen.store_mechanism(mechanisms[0])
        assert stored is True
        mock_memory.remember.assert_called_once()

        listed = citizen.list_stored_mechanisms(limit=10)
        assert len(listed) == 1
        assert listed[0]["metadata"]["name"] == "caching layer"

    def test_store_proposal(self):
        mock_memory = MagicMock()
        citizen = AbstractionCitizen(memory_layer=mock_memory)
        mechanisms = citizen.extract_mechanisms("Circuit breaker with exponential backoff", "src8")
        proposal = citizen.generate_proposal(mechanisms)
        assert proposal is not None
        stored = citizen.store_proposal(proposal)
        assert stored is True
        mock_memory.remember.assert_called_once()

    def test_store_mechanism_without_memory(self):
        citizen = AbstractionCitizen()
        mechanisms = citizen.extract_mechanisms("Use Redis for caching", "src")
        stored = citizen.store_mechanism(mechanisms[0])
        assert stored is False

    def test_store_report_with_memory(self):
        mock_memory = MagicMock()
        citizen = AbstractionCitizen(memory_layer=mock_memory)
        from animus.citizens.abstraction import AbstractionReport

        report = AbstractionReport(mechanisms=[], sources_processed=5)
        stored = citizen.store_report(report)
        assert stored is True
        mock_memory.remember.assert_called_once()

    def test_list_mechanisms_without_memory(self):
        citizen = AbstractionCitizen()
        listed = citizen.list_stored_mechanisms(limit=10)
        assert listed == []


class TestAbstractionCli:
    def test_cli_import(self):
        from animus.cli import _cmd_abstraction

        assert callable(_cmd_abstraction)

    def test_cmd_abstraction_scan(self, capsys, tmp_path, monkeypatch):
        from argparse import Namespace

        from animus.cli import _cmd_abstraction

        args = Namespace(
            abstraction_command="scan",
            codebase_path=str(tmp_path),
            store=False,
        )
        result = _cmd_abstraction(args)
        captured = capsys.readouterr()
        assert "Abstraction" in captured.out or result == 0

    def test_cmd_abstraction_mechanisms(self, capsys, monkeypatch):
        from argparse import Namespace

        from animus.cli import _cmd_abstraction

        args = Namespace(
            abstraction_command="mechanisms",
            codebase_path="",
            limit=10,
        )
        result = _cmd_abstraction(args)
        captured = capsys.readouterr()
        assert "Abstraction" in captured.out or result == 0


class TestAbstractionMcpTools:
    @pytest.fixture
    def mcp_server(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANIMUS_DATA_DIR", str(tmp_path / "mcp-data"))
        monkeypatch.setenv("ANIMUS_MEMORY_BACKEND", "json")
        pytest.importorskip("mcp")
        from animus.mcp_server import create_mcp_server

        return create_mcp_server()

    def test_abstraction_tools_exist(self, mcp_server):
        tools = list(mcp_server._tools.keys())
        assert "animus_abstraction_scan" in tools
        assert "animus_abstraction_list_mechanisms" in tools

    def test_abstraction_scan_mocked(self, mcp_server, monkeypatch):
        def _mock_observe_codebase(*args, **kwargs):
            return [
                {
                    "id": "abs1",
                    "description": "Mock mechanism",
                    "severity": "info",
                    "context": {},
                }
            ]

        def _mock_observe_harvested(*args, **kwargs):
            return [
                {
                    "id": "src1",
                    "description": "Mock source",
                    "severity": "info",
                    "context": {"content": "Use Redis for caching", "identifier": "src1"},
                }
            ]

        monkeypatch.setattr(
            "animus.citizens.abstraction.AbstractionCitizen.observe_codebase",
            _mock_observe_codebase,
        )
        monkeypatch.setattr(
            "animus.citizens.abstraction.AbstractionCitizen.observe_harvested_sources",
            _mock_observe_harvested,
        )

        result = mcp_server._tools["animus_abstraction_scan"].fn(
            codebase_path=".",
            store_mechanisms=False,
        )
        assert "Abstraction Citizen Scan Report" in result
        assert "Mock mechanism" in result

    def test_abstraction_list_mechanisms_empty(self, mcp_server):
        result = mcp_server._tools["animus_abstraction_list_mechanisms"].fn(
            limit=10,
        )
        assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# PatternCitizen tests (Research Guild — Citizen 009)
# ---------------------------------------------------------------------------


class TestPatternCitizen:
    def test_initialization(self):
        citizen = PatternCitizen()
        assert citizen.codebase_path == Path(".").expanduser()
        assert citizen.memory is None

    def test_discover_patterns_category_cluster(self):
        citizen = PatternCitizen()
        mechanisms = [
            {
                "name": "caching layer",
                "category": "performance",
                "description": "Cache data",
                "tags": ["performance"],
                "source_provenance": ["src1"],
            },
            {
                "name": "bounded retrieval",
                "category": "performance",
                "description": "Paginate results",
                "tags": ["performance"],
                "source_provenance": ["src2"],
            },
            {
                "name": "flow control",
                "category": "reliability",
                "description": "Rate limit",
                "tags": ["reliability"],
                "source_provenance": ["src3"],
            },
            {
                "name": "progressive rollout",
                "category": "performance",
                "description": "Feature flags",
                "tags": ["performance", "deployment"],
                "source_provenance": ["src4"],
            },
        ]
        patterns = citizen.discover_patterns(mechanisms)
        assert len(patterns) >= 1
        perf_patterns = [p for p in patterns if p.category == "performance"]
        assert len(perf_patterns) >= 1
        assert len(perf_patterns[0].constituent_mechanisms) >= 3

    def test_discover_patterns_cross_cutting_tags(self):
        citizen = PatternCitizen()
        mechanisms = [
            {
                "name": "caching layer",
                "category": "performance",
                "description": "Cache data",
                "tags": ["performance", "scalability"],
                "source_provenance": ["src1"],
            },
            {
                "name": "bounded retrieval",
                "category": "performance",
                "description": "Paginate results",
                "tags": ["performance", "scalability"],
                "source_provenance": ["src2"],
            },
            {
                "name": "fault tolerance",
                "category": "reliability",
                "description": "Circuit breaker",
                "tags": ["reliability"],
                "source_provenance": ["src3"],
            },
        ]
        patterns = citizen.discover_patterns(mechanisms)
        # Cross-cutting tag "scalability" should create a pattern
        cross = [p for p in patterns if p.category == "cross-cutting"]
        assert len(cross) >= 1
        assert "scalability" in cross[0].tags

    def test_discover_patterns_no_match(self):
        citizen = PatternCitizen()
        mechanisms = [
            {
                "name": "caching layer",
                "category": "performance",
                "description": "Cache data",
                "tags": ["performance"],
                "source_provenance": ["src1"],
            },
        ]
        patterns = citizen.discover_patterns(mechanisms)
        assert patterns == []

    def test_discover_patterns_empty(self):
        citizen = PatternCitizen()
        assert citizen.discover_patterns([]) == []
        assert citizen.discover_patterns(None) == []

    def test_pattern_card_fields(self):
        citizen = PatternCitizen()
        mechanisms = [
            {
                "name": "caching layer",
                "category": "performance",
                "description": "Cache data",
                "tags": ["performance"],
                "source_provenance": ["src1"],
            },
            {
                "name": "bounded retrieval",
                "category": "performance",
                "description": "Paginate",
                "tags": ["performance"],
                "source_provenance": ["src2"],
            },
            {
                "name": "progressive rollout",
                "category": "performance",
                "description": "Flags",
                "tags": ["performance"],
                "source_provenance": ["src3"],
            },
        ]
        patterns = citizen.discover_patterns(mechanisms)
        assert patterns
        p = patterns[0]
        assert p.name
        assert p.description
        assert p.category
        assert p.confidence > 0
        assert len(p.constituent_mechanisms) >= 3

    def test_generate_proposal_with_patterns(self):
        citizen = PatternCitizen()
        mechanisms = [
            {
                "name": "caching layer",
                "category": "performance",
                "description": "Cache data",
                "tags": ["performance"],
                "source_provenance": ["src1"],
            },
            {
                "name": "bounded retrieval",
                "category": "performance",
                "description": "Paginate",
                "tags": ["performance"],
                "source_provenance": ["src2"],
            },
            {
                "name": "progressive rollout",
                "category": "performance",
                "description": "Flags",
                "tags": ["performance"],
                "source_provenance": ["src3"],
            },
        ]
        patterns = citizen.discover_patterns(mechanisms)
        proposal = citizen.generate_proposal(patterns)
        assert proposal is not None
        assert "pattern" in proposal.title.lower()
        assert proposal.confidence_score > 0

    def test_generate_proposal_empty_patterns(self):
        citizen = PatternCitizen()
        proposal = citizen.generate_proposal([])
        assert proposal is None

    def test_generate_proposal_auto_discover(self):
        citizen = PatternCitizen()
        proposal = citizen.generate_proposal()
        assert proposal is None

    def test_observe_mechanisms_without_memory(self):
        citizen = PatternCitizen()
        obs = citizen.observe_mechanisms()
        assert obs == []

    def test_observe_mechanisms_with_memory(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            {
                "content": "caching layer: Separate read-heavy data",
                "metadata": {
                    "name": "caching layer",
                    "category": "performance",
                    "description": "Separate read-heavy data",
                    "source_provenance": ["src1"],
                    "tags": ["performance"],
                },
            }
        ]
        citizen = PatternCitizen(memory_layer=mock_memory)
        obs = citizen.observe_mechanisms()
        assert len(obs) == 1
        assert obs[0]["context"]["name"] == "caching layer"

    def test_store_and_list_patterns(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            {
                "id": "p1",
                "content": "Performance pattern",
                "metadata": {
                    "name": "Performance pattern",
                    "category": "performance",
                    "constituent_mechanisms": ["a", "b"],
                },
            }
        ]
        citizen = PatternCitizen(memory_layer=mock_memory)
        patterns = citizen.discover_patterns(
            [
                {
                    "name": "a",
                    "category": "performance",
                    "description": "x",
                    "tags": ["performance"],
                    "source_provenance": ["s1"],
                },
                {
                    "name": "b",
                    "category": "performance",
                    "description": "y",
                    "tags": ["performance"],
                    "source_provenance": ["s2"],
                },
                {
                    "name": "c",
                    "category": "performance",
                    "description": "z",
                    "tags": ["performance"],
                    "source_provenance": ["s3"],
                },
            ]
        )
        stored = citizen.store_pattern(patterns[0])
        assert stored is True
        mock_memory.remember.assert_called_once()

        listed = citizen.list_stored_patterns(limit=10)
        assert len(listed) == 1
        assert listed[0]["metadata"]["name"] == "Performance pattern"

    def test_store_proposal(self):
        mock_memory = MagicMock()
        citizen = PatternCitizen(memory_layer=mock_memory)
        patterns = citizen.discover_patterns(
            [
                {
                    "name": "a",
                    "category": "performance",
                    "description": "x",
                    "tags": ["performance"],
                    "source_provenance": ["s1"],
                },
                {
                    "name": "b",
                    "category": "performance",
                    "description": "y",
                    "tags": ["performance"],
                    "source_provenance": ["s2"],
                },
                {
                    "name": "c",
                    "category": "performance",
                    "description": "z",
                    "tags": ["performance"],
                    "source_provenance": ["s3"],
                },
            ]
        )
        proposal = citizen.generate_proposal(patterns)
        assert proposal is not None
        stored = citizen.store_proposal(proposal)
        assert stored is True
        mock_memory.remember.assert_called_once()

    def test_store_pattern_without_memory(self):
        citizen = PatternCitizen()
        patterns = citizen.discover_patterns(
            [
                {
                    "name": "a",
                    "category": "performance",
                    "description": "x",
                    "tags": ["performance"],
                    "source_provenance": ["s1"],
                },
                {
                    "name": "b",
                    "category": "performance",
                    "description": "y",
                    "tags": ["performance"],
                    "source_provenance": ["s2"],
                },
                {
                    "name": "c",
                    "category": "performance",
                    "description": "z",
                    "tags": ["performance"],
                    "source_provenance": ["s3"],
                },
            ]
        )
        stored = citizen.store_pattern(patterns[0])
        assert stored is False

    def test_store_report_with_memory(self):
        mock_memory = MagicMock()
        citizen = PatternCitizen(memory_layer=mock_memory)
        from animus.citizens.pattern import PatternReport

        report = PatternReport(patterns=[], mechanisms_processed=5)
        stored = citizen.store_report(report)
        assert stored is True
        mock_memory.remember.assert_called_once()

    def test_list_patterns_without_memory(self):
        citizen = PatternCitizen()
        listed = citizen.list_stored_patterns(limit=10)
        assert listed == []

    def test_pattern_report_summary(self):
        from animus.citizens.pattern import PatternCard, PatternReport

        report = PatternReport(
            patterns=[PatternCard(name="p1", description="d1")],
            mechanisms_processed=5,
            mechanisms_with_no_pattern=2,
        )
        assert "1 pattern(s) discovered from 5 mechanism(s)" in report.summary()
        assert "2 mechanism(s) with no recognizable pattern" in report.summary()


class TestPatternCli:
    def test_cli_import(self):
        from animus.cli import _cmd_pattern

        assert callable(_cmd_pattern)

    def test_cmd_pattern_scan(self, capsys, tmp_path):
        from argparse import Namespace

        from animus.cli import _cmd_pattern

        args = Namespace(
            pattern_command="scan",
            codebase_path=str(tmp_path),
            store=False,
        )
        result = _cmd_pattern(args)
        captured = capsys.readouterr()
        assert "Pattern" in captured.out or result == 0

    def test_cmd_pattern_patterns(self, capsys):
        from argparse import Namespace

        from animus.cli import _cmd_pattern

        args = Namespace(
            pattern_command="patterns",
            codebase_path="",
            limit=10,
        )
        result = _cmd_pattern(args)
        captured = capsys.readouterr()
        assert "Pattern" in captured.out or result == 0


class TestPatternMcpTools:
    @pytest.fixture
    def mcp_server(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANIMUS_DATA_DIR", str(tmp_path / "mcp-data"))
        monkeypatch.setenv("ANIMUS_MEMORY_BACKEND", "json")
        pytest.importorskip("mcp")
        from animus.mcp_server import create_mcp_server

        return create_mcp_server()

    def test_pattern_tools_exist(self, mcp_server):
        tools = list(mcp_server._tools.keys())
        assert "animus_pattern_scan" in tools
        assert "animus_pattern_list_patterns" in tools

    def test_pattern_scan_mocked(self, mcp_server, monkeypatch):
        def _mock_observe_mechanisms(*args, **kwargs):
            return [
                {
                    "id": "m1",
                    "description": "Mock mechanism",
                    "severity": "info",
                    "context": {
                        "name": "caching layer",
                        "category": "performance",
                        "description": "Cache data",
                        "tags": ["performance"],
                        "source_provenance": ["src1"],
                    },
                },
                {
                    "id": "m2",
                    "description": "Mock mechanism 2",
                    "severity": "info",
                    "context": {
                        "name": "bounded retrieval",
                        "category": "performance",
                        "description": "Paginate",
                        "tags": ["performance"],
                        "source_provenance": ["src2"],
                    },
                },
                {
                    "id": "m3",
                    "description": "Mock mechanism 3",
                    "severity": "info",
                    "context": {
                        "name": "progressive rollout",
                        "category": "performance",
                        "description": "Flags",
                        "tags": ["performance"],
                        "source_provenance": ["src3"],
                    },
                },
            ]

        monkeypatch.setattr(
            "animus.citizens.pattern.PatternCitizen.observe_mechanisms",
            _mock_observe_mechanisms,
        )

        result = mcp_server._tools["animus_pattern_scan"].fn(
            codebase_path=".",
            store_patterns=False,
        )
        assert "Pattern Citizen Scan Report" in result
        assert "Mock mechanism" in result

    def test_pattern_list_patterns_empty(self, mcp_server):
        result = mcp_server._tools["animus_pattern_list_patterns"].fn(
            limit=10,
        )
        assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# FirstPrinciplesCitizen tests (Research Guild — Citizen 010)
# ---------------------------------------------------------------------------


class TestFirstPrinciplesCitizen:
    def test_initialization(self):
        citizen = FirstPrinciplesCitizen()
        assert citizen.codebase_path == Path(".").expanduser()
        assert citizen.memory is None

    def test_reduce_to_principles_single_pattern(self):
        citizen = FirstPrinciplesCitizen()
        patterns = [
            {
                "name": "State externalization pattern",
                "category": "architecture",
                "description": "Separate state from computation",
                "tags": ["state"],
                "source_provenance": ["src1"],
            },
        ]
        principles = citizen.reduce_to_principles(patterns)
        assert len(principles) >= 1
        statements = [p.principle_statement for p in principles]
        assert any("separate state" in s.lower() for s in statements)

    def test_reduce_to_principles_multiple_patterns_same_principle(self):
        citizen = FirstPrinciplesCitizen()
        patterns = [
            {
                "name": "State externalization",
                "category": "architecture",
                "description": "Separate state",
                "tags": ["state"],
                "source_provenance": ["src1"],
            },
            {
                "name": "Immutable log pattern",
                "category": "architecture",
                "description": "Use immutable logs",
                "tags": ["state"],
                "source_provenance": ["src2"],
            },
        ]
        principles = citizen.reduce_to_principles(patterns)
        # Should merge into a single principle with combined supporting patterns
        assert len(principles) >= 1
        # At least one principle should have 2 supporting patterns
        assert any(len(p.supporting_patterns) >= 2 for p in principles)

    def test_reduce_to_principles_no_match(self):
        citizen = FirstPrinciplesCitizen()
        patterns = [
            {
                "name": "Unknown pattern",
                "category": "unknown",
                "description": "Something random",
                "tags": ["unknown"],
                "source_provenance": ["src1"],
            },
        ]
        principles = citizen.reduce_to_principles(patterns)
        assert principles == []

    def test_reduce_to_principles_empty(self):
        citizen = FirstPrinciplesCitizen()
        assert citizen.reduce_to_principles([]) == []
        assert citizen.reduce_to_principles(None) == []

    def test_reduce_to_principles_contradictions(self):
        citizen = FirstPrinciplesCitizen()
        # Create a pattern that would trigger a contradiction keyword pair
        patterns = [
            {
                "name": "Stateless services",
                "category": "architecture",
                "description": "stateless and state externalization",
                "tags": ["state"],
                "source_provenance": ["src1"],
            },
        ]
        principles = citizen.reduce_to_principles(patterns)
        for p in principles:
            if (
                "stateless" in p.principle_statement.lower()
                and "state externalization" in p.principle_statement.lower()
            ):
                assert len(p.contradictions) > 0

    def test_principle_card_fields(self):
        citizen = FirstPrinciplesCitizen()
        patterns = [
            {
                "name": "Async communication pattern",
                "category": "architecture",
                "description": "Use async message queues",
                "tags": ["async"],
                "source_provenance": ["src1"],
            },
        ]
        principles = citizen.reduce_to_principles(patterns)
        assert principles
        p = principles[0]
        assert p.principle_statement
        assert p.category
        assert p.confidence > 0
        assert p.supporting_patterns

    def test_generate_proposal_with_principles(self):
        citizen = FirstPrinciplesCitizen()
        patterns = [
            {
                "name": "Async communication",
                "category": "architecture",
                "description": "Use async message queues",
                "tags": ["async"],
                "source_provenance": ["src1"],
            },
            {
                "name": "Decoupling pattern",
                "category": "architecture",
                "description": "Decouple producers from consumers",
                "tags": ["async"],
                "source_provenance": ["src2"],
            },
        ]
        principles = citizen.reduce_to_principles(patterns)
        proposal = citizen.generate_proposal(principles)
        assert proposal is not None
        assert "principle" in proposal.title.lower()
        assert proposal.confidence_score > 0

    def test_generate_proposal_empty_principles(self):
        citizen = FirstPrinciplesCitizen()
        proposal = citizen.generate_proposal([])
        assert proposal is None

    def test_generate_proposal_auto_discover(self):
        citizen = FirstPrinciplesCitizen()
        proposal = citizen.generate_proposal()
        assert proposal is None

    def test_observe_patterns_without_memory(self):
        citizen = FirstPrinciplesCitizen()
        obs = citizen.observe_patterns()
        assert obs == []

    def test_observe_patterns_with_memory(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            {
                "content": "Performance pattern",
                "metadata": {
                    "name": "Performance pattern",
                    "category": "performance",
                    "description": "Cache and paginate",
                    "constituent_mechanisms": ["caching", "pagination"],
                    "tags": ["performance"],
                    "source_provenance": ["src1"],
                },
            }
        ]
        citizen = FirstPrinciplesCitizen(memory_layer=mock_memory)
        obs = citizen.observe_patterns()
        assert len(obs) == 1
        assert obs[0]["context"]["name"] == "Performance pattern"

    def test_store_and_list_principles(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            {
                "id": "pr1",
                "content": "Systems that separate concerns survive longer",
                "metadata": {
                    "principle_statement": "Systems that separate concerns survive longer",
                    "category": "architecture",
                },
            }
        ]
        citizen = FirstPrinciplesCitizen(memory_layer=mock_memory)
        principles = citizen.reduce_to_principles(
            [
                {
                    "name": "Separation of concerns",
                    "category": "architecture",
                    "description": "Separate concerns",
                    "tags": ["architecture"],
                    "source_provenance": ["s1"],
                },
            ]
        )
        assert principles
        stored = citizen.store_principle(principles[0])
        assert stored is True
        mock_memory.remember.assert_called_once()

        listed = citizen.list_stored_principles(limit=10)
        assert len(listed) == 1
        assert (
            listed[0]["metadata"]["principle_statement"]
            == "Systems that separate concerns survive longer"
        )

    def test_store_proposal(self):
        mock_memory = MagicMock()
        citizen = FirstPrinciplesCitizen(memory_layer=mock_memory)
        principles = citizen.reduce_to_principles(
            [
                {
                    "name": "Async communication",
                    "category": "architecture",
                    "description": "Use async message queues",
                    "tags": ["async"],
                    "source_provenance": ["s1"],
                },
            ]
        )
        proposal = citizen.generate_proposal(principles)
        assert proposal is not None
        stored = citizen.store_proposal(proposal)
        assert stored is True
        mock_memory.remember.assert_called_once()

    def test_store_principle_without_memory(self):
        citizen = FirstPrinciplesCitizen()
        principles = citizen.reduce_to_principles(
            [
                {
                    "name": "Async communication",
                    "category": "architecture",
                    "description": "Use async message queues",
                    "tags": ["async"],
                    "source_provenance": ["s1"],
                },
            ]
        )
        stored = citizen.store_principle(principles[0])
        assert stored is False

    def test_store_report_with_memory(self):
        mock_memory = MagicMock()
        citizen = FirstPrinciplesCitizen(memory_layer=mock_memory)
        from animus.citizens.first_principles import FirstPrinciplesReport

        report = FirstPrinciplesReport(principles=[], patterns_processed=5)
        stored = citizen.store_report(report)
        assert stored is True
        mock_memory.remember.assert_called_once()

    def test_list_principles_without_memory(self):
        citizen = FirstPrinciplesCitizen()
        listed = citizen.list_stored_principles(limit=10)
        assert listed == []

    def test_first_principles_report_summary(self):
        from animus.citizens.first_principles import FirstPrinciplesReport, PrincipleCard

        report = FirstPrinciplesReport(
            principles=[PrincipleCard(principle_statement="P1")],
            patterns_processed=5,
            contradictions_found=2,
        )
        assert "1 principle(s) reduced from 5 pattern(s)" in report.summary()
        assert "2 contradiction(s) flagged" in report.summary()


class TestFirstPrinciplesCli:
    def test_cli_import(self):
        from animus.cli import _cmd_first_principles

        assert callable(_cmd_first_principles)

    def test_cmd_first_principles_scan(self, capsys, tmp_path):
        from argparse import Namespace

        from animus.cli import _cmd_first_principles

        args = Namespace(
            first_principles_command="scan",
            codebase_path=str(tmp_path),
            store=False,
        )
        result = _cmd_first_principles(args)
        captured = capsys.readouterr()
        assert "First-Principles" in captured.out or result == 0

    def test_cmd_first_principles_principles(self, capsys):
        from argparse import Namespace

        from animus.cli import _cmd_first_principles

        args = Namespace(
            first_principles_command="principles",
            codebase_path="",
            limit=10,
        )
        result = _cmd_first_principles(args)
        captured = capsys.readouterr()
        assert "Principle" in captured.out or result == 0


class TestFirstPrinciplesMcpTools:
    @pytest.fixture
    def mcp_server(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANIMUS_DATA_DIR", str(tmp_path / "mcp-data"))
        monkeypatch.setenv("ANIMUS_MEMORY_BACKEND", "json")
        pytest.importorskip("mcp")
        from animus.mcp_server import create_mcp_server

        return create_mcp_server()

    def test_first_principles_tools_exist(self, mcp_server):
        tools = list(mcp_server._tools.keys())
        assert "animus_first_principles_scan" in tools
        assert "animus_first_principles_list_principles" in tools

    def test_first_principles_scan_mocked(self, mcp_server, monkeypatch):
        def _mock_observe_patterns(*args, **kwargs):
            return [
                {
                    "id": "p1",
                    "description": "Mock pattern",
                    "severity": "info",
                    "context": {
                        "name": "Async communication",
                        "category": "architecture",
                        "description": "Use async message queues",
                        "tags": ["async"],
                        "source_provenance": ["src1"],
                    },
                },
            ]

        monkeypatch.setattr(
            "animus.citizens.first_principles.FirstPrinciplesCitizen.observe_patterns",
            _mock_observe_patterns,
        )

        result = mcp_server._tools["animus_first_principles_scan"].fn(
            codebase_path=".",
            store_principles=False,
        )
        assert "First-Principles Citizen Scan Report" in result
        assert "Mock pattern" in result

    def test_first_principles_list_principles_empty(self, mcp_server):
        result = mcp_server._tools["animus_first_principles_list_principles"].fn(
            limit=10,
        )
        assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# ArchitectureCitizen tests (Research Guild — Citizen 011)
# ---------------------------------------------------------------------------


class TestArchitectureCitizen:
    def test_initialization(self):
        citizen = ArchitectureCitizen()
        assert citizen.codebase_path == Path(".").expanduser()
        assert citizen.memory is None

    def test_analyze_gaps_with_principles(self, tmp_path):
        # Create a minimal codebase file to search
        (tmp_path / "test_module.py").write_text("class TestClass: pass\\n")
        citizen = ArchitectureCitizen(codebase_path=tmp_path)
        principles = [
            {
                "principle_statement": "Systems that separate state from computation survive longer.",
                "category": "architecture",
                "tags": ["architecture"],
                "source_provenance": ["src1"],
            },
        ]
        gaps = citizen.analyze_gaps(principles)
        assert len(gaps) >= 1
        assert gaps[0].principle_statement
        assert gaps[0].severity in ["low", "medium", "high", "critical"]
        assert 0 <= gaps[0].coverage_ratio <= 1.0

    def test_analyze_gaps_no_principles(self):
        citizen = ArchitectureCitizen()
        assert citizen.analyze_gaps([]) == []
        assert citizen.analyze_gaps(None) == []

    def test_gap_analysis_fields(self, tmp_path):
        (tmp_path / "test_module.py").write_text("def test(): pass\\n")
        citizen = ArchitectureCitizen(codebase_path=tmp_path)
        principles = [
            {
                "principle_statement": "Decoupling producers from consumers is the single most effective way to scale systems under uncertainty.",
                "category": "architecture",
                "tags": ["async"],
                "source_provenance": ["src1"],
            },
        ]
        gaps = citizen.analyze_gaps(principles)
        assert gaps
        g = gaps[0]
        assert g.principle_statement
        assert g.gap_description
        assert g.recommendation
        assert g.estimated_effort_hours >= 0

    def test_generate_proposal_with_gaps(self):
        citizen = ArchitectureCitizen()
        from animus.citizens.architecture_citizen import GapAnalysis

        gaps = [
            GapAnalysis(
                principle_statement="Test principle",
                principle_category="architecture",
                gap_description="Test gap",
                severity="high",
                coverage_ratio=0.2,
                estimated_effort_hours=8.0,
            ),
        ]
        proposal = citizen.generate_proposal(gaps)
        assert proposal is not None
        assert "gap" in proposal.title.lower() or "architecture" in proposal.title.lower()
        assert proposal.confidence_score > 0
        assert proposal.estimated_effort_hours > 0

    def test_generate_proposal_empty_gaps(self):
        citizen = ArchitectureCitizen()
        proposal = citizen.generate_proposal([])
        assert proposal is None

    def test_generate_proposal_auto_discover(self):
        citizen = ArchitectureCitizen()
        proposal = citizen.generate_proposal()
        assert proposal is None

    def test_observe_principles_without_memory(self):
        citizen = ArchitectureCitizen()
        obs = citizen.observe_principles()
        assert obs == []

    def test_observe_principles_with_memory(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            {
                "content": "Systems that separate concerns survive longer",
                "metadata": {
                    "principle_statement": "Systems that separate concerns survive longer",
                    "category": "architecture",
                    "supporting_patterns": ["Separation of concerns"],
                    "tags": ["architecture"],
                    "source_provenance": ["src1"],
                },
            }
        ]
        citizen = ArchitectureCitizen(memory_layer=mock_memory)
        obs = citizen.observe_principles()
        assert len(obs) == 1
        assert (
            obs[0]["context"]["principle_statement"]
            == "Systems that separate concerns survive longer"
        )

    def test_store_and_list_gaps(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = [
            {
                "id": "g1",
                "content": "[HIGH] architecture gap",
                "metadata": {
                    "principle_statement": "Test principle",
                    "severity": "high",
                    "principle_category": "architecture",
                },
            }
        ]
        citizen = ArchitectureCitizen(memory_layer=mock_memory)
        from animus.citizens.architecture_citizen import GapAnalysis

        gap = GapAnalysis(
            principle_statement="Test principle",
            principle_category="architecture",
            gap_description="Test gap",
            severity="high",
            coverage_ratio=0.1,
        )
        stored = citizen.store_gap(gap)
        assert stored is True
        mock_memory.remember.assert_called_once()

        listed = citizen.list_stored_gaps(limit=10)
        assert len(listed) == 1
        assert listed[0]["metadata"]["principle_statement"] == "Test principle"

    def test_store_proposal(self):
        mock_memory = MagicMock()
        citizen = ArchitectureCitizen(memory_layer=mock_memory)
        from animus.citizens.architecture_citizen import GapAnalysis

        gaps = [
            GapAnalysis(
                principle_statement="Test principle",
                principle_category="architecture",
                gap_description="Test gap",
                severity="high",
                coverage_ratio=0.2,
                estimated_effort_hours=8.0,
            ),
        ]
        proposal = citizen.generate_proposal(gaps)
        assert proposal is not None
        stored = citizen.store_proposal(proposal)
        assert stored is True
        mock_memory.remember.assert_called_once()

    def test_store_gap_without_memory(self):
        citizen = ArchitectureCitizen()
        from animus.citizens.architecture_citizen import GapAnalysis

        gap = GapAnalysis(principle_statement="Test", gap_description="Gap")
        stored = citizen.store_gap(gap)
        assert stored is False

    def test_store_report_with_memory(self):
        mock_memory = MagicMock()
        citizen = ArchitectureCitizen(memory_layer=mock_memory)
        from animus.citizens.architecture_citizen import ArchitectureReport

        report = ArchitectureReport(gaps=[], principles_processed=5)
        stored = citizen.store_report(report)
        assert stored is True
        mock_memory.remember.assert_called_once()

    def test_list_gaps_without_memory(self):
        citizen = ArchitectureCitizen()
        listed = citizen.list_stored_gaps(limit=10)
        assert listed == []

    def test_architecture_report_summary(self):
        from animus.citizens.architecture_citizen import ArchitectureReport, GapAnalysis

        report = ArchitectureReport(
            gaps=[
                GapAnalysis(principle_statement="P1", severity="critical"),
                GapAnalysis(principle_statement="P2", severity="high"),
            ],
            principles_processed=3,
        )
        assert "2 gap(s) identified from 3 principle(s)" in report.summary()
        assert "1 critical" in report.summary()
        assert "1 high" in report.summary()

    def test_estimate_effort(self):
        citizen = ArchitectureCitizen()
        assert citizen._estimate_effort("critical", 10) > citizen._estimate_effort("low", 0)
        assert citizen._estimate_effort("critical", 0) >= 16.0
        assert citizen._estimate_effort("low", 0) >= 2.0

    def test_draft_recommendation(self):
        citizen = ArchitectureCitizen()
        rec = citizen._draft_recommendation(
            "Test principle", "architecture", "high", ["file1.py", "file2.py"]
        )
        assert "Test principle" in rec
        assert "file1.py" in rec
        assert "high" in rec.lower() or "moderate" in rec.lower()


class TestArchitectureCitizenCli:
    def test_cli_import(self):
        from animus.cli import _cmd_architecture_citizen

        assert callable(_cmd_architecture_citizen)

    def test_cmd_architecture_citizen_scan(self, capsys, tmp_path):
        from argparse import Namespace

        from animus.cli import _cmd_architecture_citizen

        args = Namespace(
            architecture_citizen_command="scan",
            codebase_path=str(tmp_path),
            store=False,
        )
        result = _cmd_architecture_citizen(args)
        captured = capsys.readouterr()
        assert "Architecture" in captured.out or result == 0

    def test_cmd_architecture_citizen_gaps(self, capsys):
        from argparse import Namespace

        from animus.cli import _cmd_architecture_citizen

        args = Namespace(
            architecture_citizen_command="gaps",
            codebase_path="",
            limit=10,
        )
        result = _cmd_architecture_citizen(args)
        captured = capsys.readouterr()
        assert "Gap" in captured.out or result == 0


class TestArchitectureCitizenMcpTools:
    @pytest.fixture
    def mcp_server(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANIMUS_DATA_DIR", str(tmp_path / "mcp-data"))
        monkeypatch.setenv("ANIMUS_MEMORY_BACKEND", "json")
        pytest.importorskip("mcp")
        from animus.mcp_server import create_mcp_server

        return create_mcp_server()

    def test_architecture_citizen_tools_exist(self, mcp_server):
        tools = list(mcp_server._tools.keys())
        assert "animus_architecture_citizen_scan" in tools
        assert "animus_architecture_citizen_list_gaps" in tools

    def test_architecture_citizen_scan_mocked(self, mcp_server, monkeypatch):
        def _mock_observe_principles(*args, **kwargs):
            return [
                {
                    "id": "pr1",
                    "description": "Mock principle",
                    "severity": "info",
                    "context": {
                        "principle_statement": "Systems that separate concerns survive longer.",
                        "category": "architecture",
                        "tags": ["architecture"],
                        "source_provenance": ["src1"],
                    },
                },
            ]

        monkeypatch.setattr(
            "animus.citizens.architecture_citizen.ArchitectureCitizen.observe_principles",
            _mock_observe_principles,
        )

        result = mcp_server._tools["animus_architecture_citizen_scan"].fn(
            codebase_path=".",
            store_gaps=False,
        )
        assert "Architecture Citizen Scan Report" in result
        assert "Mock principle" in result

    def test_architecture_citizen_list_gaps_empty(self, mcp_server):
        result = mcp_server._tools["animus_architecture_citizen_list_gaps"].fn(
            limit=10,
        )
        assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# Research Guild Orchestrator tests
# ---------------------------------------------------------------------------


class TestStageResult:
    def test_basic_creation(self):
        r = StageResult(citizen_name="harvester", outputs_count=3)
        assert r.citizen_name == "harvester"
        assert r.outputs_count == 3
        assert r.stored_count == 0
        assert r.errors == []
        assert r.duration_seconds == 0.0


class TestGuildPipelineReport:
    def test_basic_creation(self):
        report = GuildPipelineReport()
        assert report.total_stages == 0
        assert report.total_outputs == 0
        assert report.total_errors == 0
        assert report.final_proposal is None

    def test_with_stages(self):
        report = GuildPipelineReport(
            stages=[
                StageResult(citizen_name="harvester", outputs_count=2),
                StageResult(citizen_name="abstraction", outputs_count=1, stored_count=1),
            ]
        )
        assert report.total_stages == 2
        assert report.total_outputs == 3
        assert report.total_errors == 0

    def test_summary(self):
        report = GuildPipelineReport(
            stages=[
                StageResult(citizen_name="harvester", outputs_count=2, duration_seconds=1.0),
            ],
            duration_seconds=5.0,
        )
        summary = report.summary()
        assert "Research Guild Pipeline" in summary
        assert "harvester" in summary
        assert "2 output(s)" in summary
        assert "5.0s" in summary

    def test_to_dict(self):
        report = GuildPipelineReport(
            stages=[
                StageResult(citizen_name="harvester", outputs_count=2, duration_seconds=1.0),
            ],
            duration_seconds=5.0,
        )
        d = report.to_dict()
        assert d["duration_seconds"] == 5.0
        assert d["final_proposal_id"] is None
        assert isinstance(d["stages"], list)
        assert len(d["stages"]) == 1
        assert d["stages"][0]["citizen_name"] == "harvester"
        assert d["stages"][0]["outputs_count"] == 2


class TestResearchGuildOrchestrator:
    def test_instantiation(self):
        o = ResearchGuildOrchestrator(codebase_path=".")
        assert o is not None
        assert str(o.codebase_path) == "."

    def test_run_pipeline_skip_harvester(self, tmp_path, monkeypatch):
        """Pipeline with skip_harvester=True should still run remaining stages."""
        memory = MagicMock()
        orchestrator = ResearchGuildOrchestrator(
            memory_layer=memory,
            codebase_path=tmp_path,
        )

        # Mock all citizen methods to avoid real file scanning
        monkeypatch.setattr(
            "animus.citizens.HarvesterCitizen",
            MagicMock,
        )
        monkeypatch.setattr(
            "animus.citizens.AbstractionCitizen",
            MagicMock,
        )
        monkeypatch.setattr(
            "animus.citizens.PatternCitizen",
            MagicMock,
        )
        monkeypatch.setattr(
            "animus.citizens.FirstPrinciplesCitizen",
            MagicMock,
        )
        monkeypatch.setattr(
            "animus.citizens.ArchitectureCitizen",
            MagicMock,
        )

        report = orchestrator.run_pipeline(skip_harvester=True)
        # All mocked, so stages complete but produce 0 outputs
        assert report.total_stages == 5
        assert report.duration_seconds >= 0

    def test_run_pipeline_without_memory(self, tmp_path, monkeypatch):
        """Pipeline should run without memory layer (no storage)."""
        orchestrator = ResearchGuildOrchestrator(codebase_path=tmp_path)

        monkeypatch.setattr(
            "animus.citizens.HarvesterCitizen",
            MagicMock,
        )
        monkeypatch.setattr(
            "animus.citizens.AbstractionCitizen",
            MagicMock,
        )
        monkeypatch.setattr(
            "animus.citizens.PatternCitizen",
            MagicMock,
        )
        monkeypatch.setattr(
            "animus.citizens.FirstPrinciplesCitizen",
            MagicMock,
        )
        monkeypatch.setattr(
            "animus.citizens.ArchitectureCitizen",
            MagicMock,
        )

        report = orchestrator.run_pipeline()
        assert report.total_stages == 5
        # No memory means no storage
        for s in report.stages:
            assert s.stored_count == 0

    def test_run_pipeline_error_handling(self, tmp_path, monkeypatch):
        """Pipeline should capture stage errors and continue."""
        memory = MagicMock()
        orchestrator = ResearchGuildOrchestrator(
            memory_layer=memory,
            codebase_path=tmp_path,
        )

        class BrokenHarvester:
            def __init__(self, **kwargs):
                pass

            def observe_codebase(self):
                raise RuntimeError("harvester broke")

        monkeypatch.setattr(
            "animus.citizens.HarvesterCitizen",
            BrokenHarvester,
        )
        monkeypatch.setattr(
            "animus.citizens.AbstractionCitizen",
            MagicMock,
        )
        monkeypatch.setattr(
            "animus.citizens.PatternCitizen",
            MagicMock,
        )
        monkeypatch.setattr(
            "animus.citizens.FirstPrinciplesCitizen",
            MagicMock,
        )
        monkeypatch.setattr(
            "animus.citizens.ArchitectureCitizen",
            MagicMock,
        )

        report = orchestrator.run_pipeline()
        # Should still complete all 5 stages
        assert report.total_stages == 5
        # Harvester stage should have an error
        harvester_stage = report.stages[0]
        assert harvester_stage.citizen_name == "harvester"
        assert len(harvester_stage.errors) == 1
        assert "harvester broke" in harvester_stage.errors[0]

    def test_stage_result_error_aggregation(self):
        report = GuildPipelineReport(
            stages=[
                StageResult(citizen_name="harvester", errors=["e1", "e2"]),
                StageResult(citizen_name="abstraction", errors=["e3"]),
            ],
            errors=["pipeline error"],
        )
        assert report.total_errors == 4  # 2 + 1 + 1

    def test_repr(self):
        o = ResearchGuildOrchestrator(codebase_path="/tmp/test")
        assert "ResearchGuildOrchestrator" in repr(o)
        assert "/tmp/test" in repr(o)


class TestResearchGuildCli:
    def test_cli_import(self):
        from animus.cli import _cmd_research_guild

        assert callable(_cmd_research_guild)

    def test_cmd_research_guild_run(self, capsys, tmp_path):
        from argparse import Namespace

        from animus.cli import _cmd_research_guild

        args = Namespace(
            research_guild_command="run",
            target="",
            skip_harvester=False,
            codebase_path=str(tmp_path),
            store=False,
        )
        result = _cmd_research_guild(args)
        captured = capsys.readouterr()
        assert result == 0
        assert "Research Guild" in captured.out or "Research Guild" in captured.err


class TestResearchGuildMcpTools:
    @pytest.fixture
    def mcp_server(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANIMUS_DATA_DIR", str(tmp_path / "mcp-data"))
        monkeypatch.setenv("ANIMUS_MEMORY_BACKEND", "json")
        pytest.importorskip("mcp")
        from animus.mcp_server import create_mcp_server

        return create_mcp_server()

    def test_research_guild_tools_exist(self, mcp_server):
        tools = list(mcp_server._tools.keys())
        assert "animus_research_guild_pipeline" in tools
        assert "animus_research_guild_report" in tools

    def test_research_guild_pipeline_mocked(self, mcp_server, monkeypatch):
        from animus.citizens.research_guild import GuildPipelineReport, StageResult

        def _mock_run_pipeline(*args, **kwargs):
            return GuildPipelineReport(
                stages=[
                    StageResult(citizen_name="harvester", outputs_count=2, duration_seconds=1.0),
                    StageResult(citizen_name="abstraction", outputs_count=3, duration_seconds=1.5),
                    StageResult(citizen_name="pattern", outputs_count=1, duration_seconds=0.5),
                    StageResult(
                        citizen_name="first_principles", outputs_count=2, duration_seconds=1.0
                    ),
                    StageResult(citizen_name="architecture", outputs_count=1, duration_seconds=2.0),
                ],
                duration_seconds=6.0,
            )

        monkeypatch.setattr(
            "animus.citizens.research_guild.ResearchGuildOrchestrator.run_pipeline",
            _mock_run_pipeline,
        )

        result = mcp_server._tools["animus_research_guild_pipeline"].fn(
            target="",
            skip_harvester=False,
            store_outputs=False,
        )
        assert "Research Guild Pipeline Report" in result
        assert "harvester" in result
        assert "6.0s" in result

    def test_research_guild_report_empty(self, mcp_server):
        result = mcp_server._tools["animus_research_guild_report"].fn(
            limit=5,
        )
        assert isinstance(result, str) and len(result) > 0

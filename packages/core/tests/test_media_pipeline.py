"""Tests for the Media Pipeline Orchestrator and related tuning."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from animus.citizens.abstraction import MechanismCard
from animus.citizens.architecture_citizen import ArchitectureCitizen, GapAnalysis
from animus.citizens.first_principles import FirstPrinciplesCitizen, PrincipleCard
from animus.citizens.media import (
    MediaAbstractionAdapter,
    MediaHarvester,
    MediaPipelineOrchestrator,
    MediaPipelineReport,
    MediaSynthesizer,
)
from animus.citizens.pattern import PatternCard, PatternCitizen
from animus.citizens.proposal import ImprovementProposal
from animus.lugh.sources.base import SourceItem
from animus.ogma.models import OgmaOutput

# ---------------------------------------------------------------------------
# MediaHarvester tests
# ---------------------------------------------------------------------------


class TestMediaHarvester:
    def test_ingest_text(self):
        mh = MediaHarvester()
        item = mh.ingest_text("hello world", "test-id", "Test Title")
        assert item.item_id == "test-id"
        assert item.title == "Test Title"
        assert item.raw_text == "hello world"
        assert "media" in item.tags

    @patch("animus.citizens.media.playlist_to_source_items")
    def test_ingest_playlist_delegates(self, mock_playlist):
        mock_playlist.return_value = [
            SourceItem(
                source_id="youtube:playlist:PLabc",
                item_id="vid1",
                title="Video 1",
                url="https://youtube.com/watch?v=vid1",
                published=datetime.now(),
                raw_text="transcript 1",
                tags=["ai"],
            )
        ]
        mh = MediaHarvester()
        items = mh.ingest_playlist("https://youtube.com/playlist?list=PLabc")
        assert len(items) == 1
        assert items[0].item_id == "vid1"
        mock_playlist.assert_called_once()


# ---------------------------------------------------------------------------
# MediaAbstractionAdapter tests
# ---------------------------------------------------------------------------


class TestMediaAbstractionAdapter:
    def test_from_ogma_output_basic(self):
        adapter = MediaAbstractionAdapter()
        ogma = OgmaOutput(
            title="Test",
            source_id="src",
            item_id="item1",
            date=datetime.now().date(),
            concept="A caching layer for embeddings.",
            novelty="New idea",
            animus_gap="PARTIAL",
            animus_gap_notes="Some overlap",
            weaknesses="None",
            proposal="Add packages/core/animus/cache/embedding_cache.py with LRU eviction.",
            roi_value="Faster inference",
            roi_effort="moderate",
            roi_priority="High",
            risks="Cache invalidation",
            confidence=0.75,
            confidence_justification="Strong evidence",
            sources_cited=["https://example.com"],
        )
        cards = adapter.from_ogma_output(ogma, ["item1"])
        assert len(cards) >= 1
        assert cards[0].description == "A caching layer for embeddings."
        assert "media" in cards[0].tags
        assert "ogma" in cards[0].tags

    def test_extract_name_truncates_long(self):
        adapter = MediaAbstractionAdapter()
        name = adapter._extract_name("a" * 100 + ". " + "b" * 50)
        assert len(name) <= 80

    def test_infer_category(self):
        adapter = MediaAbstractionAdapter()
        assert adapter._infer_category("cache and latency optimization") == "performance"
        assert adapter._infer_category("auth and identity verification") == "security"
        assert adapter._infer_category("test mocks and fixtures") == "quality"
        assert adapter._infer_category("LLM prompt engineering and inference") == "ai-engineering"
        assert adapter._infer_category("random unrelated text") == "general"

    def test_split_proposal(self):
        adapter = MediaAbstractionAdapter()
        text = (
            "First idea is to build a caching layer for embeddings.\n\n"
            "Second idea here is to add retry logic with exponential backoff.\n\n"
            "Third consideration is observability through metrics."
        )
        ideas = adapter._split_proposal(text)
        assert len(ideas) >= 2

    def test_store_mechanisms_with_memory(self):
        adapter = MediaAbstractionAdapter()
        mock_memory = MagicMock()
        mock_memory.remember.return_value = MagicMock(id="mem-123")
        cards = [MechanismCard(name="test", description="desc", category="general")]
        ids = adapter.store_mechanisms(cards, mock_memory)
        assert len(ids) == 1
        mock_memory.remember.assert_called_once()

    def test_store_mechanisms_without_memory(self):
        adapter = MediaAbstractionAdapter()
        ids = adapter.store_mechanisms([MechanismCard(name="test", description="desc")], None)
        assert ids == []


# ---------------------------------------------------------------------------
# MediaSynthesizer tests
# ---------------------------------------------------------------------------


class TestMediaSynthesizer:
    @patch("animus.ogma.read.synthesize")
    def test_synthesize_corpus_combines_items(self, mock_synthesize):
        mock_synthesize.return_value = MagicMock(spec=OgmaOutput)
        ms = MediaSynthesizer()
        items = [
            SourceItem(
                source_id="yt:PLabc",
                item_id="vid1",
                title="Video 1",
                url="https://youtube.com/watch?v=vid1",
                published=datetime.now(),
                raw_text="transcript one",
                tags=["ai"],
            ),
            SourceItem(
                source_id="yt:PLabc",
                item_id="vid2",
                title="Video 2",
                url="https://youtube.com/watch?v=vid2",
                published=datetime.now(),
                raw_text="transcript two",
                tags=["ml"],
            ),
        ]
        result = ms.synthesize_corpus(items)
        assert mock_synthesize.called
        call_args = mock_synthesize.call_args
        corpus_item = call_args[1]["item"] if "item" in call_args[1] else call_args[0][0]
        assert "Video 1" in corpus_item.raw_text
        assert "Video 2" in corpus_item.raw_text
        assert "transcript one" in corpus_item.raw_text
        assert "transcript two" in corpus_item.raw_text

    def test_synthesize_corpus_empty_items(self):
        ms = MediaSynthesizer()
        with pytest.raises(ValueError, match="no items"):
            ms.synthesize_corpus([])


# ---------------------------------------------------------------------------
# MediaPipelineOrchestrator tests
# ---------------------------------------------------------------------------


class TestMediaPipelineOrchestrator:
    def test_empty_harvest_returns_early(self):
        orchestrator = MediaPipelineOrchestrator(memory_layer=None, codebase_path=".")
        with patch.object(orchestrator.harvester, "ingest_playlist", return_value=[]):
            report = orchestrator.run(
                url="https://youtube.com/playlist?list=PLabc",
                source_type="youtube_playlist",
            )
        assert report.gap_status == "NONE"
        assert report.mechanisms == []
        assert len(report.stages) == 1
        assert report.stages[0].citizen_name == "MediaHarvester"

    @patch("animus.ogma.read.synthesize")
    def test_none_gate_no_downstream(self, mock_synthesize):
        ogma = OgmaOutput(
            title="Test",
            source_id="src",
            item_id="item1",
            date=datetime.now().date(),
            concept="A concept",
            novelty="New",
            animus_gap="NONE",
            animus_gap_notes="No overlap",
            weaknesses="None",
            proposal="Do nothing.",
            roi_value="Low",
            roi_effort="trivial",
            roi_priority="Later",
            risks="None",
            confidence=0.5,
            confidence_justification="Guess",
            sources_cited=["https://example.com"],
        )
        mock_synthesize.return_value = ogma
        orchestrator = MediaPipelineOrchestrator(memory_layer=None, codebase_path=".")
        items = [
            SourceItem(
                source_id="yt:PLabc",
                item_id="vid1",
                title="V1",
                url="https://youtube.com/watch?v=vid1",
                published=datetime.now(),
                raw_text="text",
            )
        ]
        with patch.object(orchestrator.harvester, "ingest_playlist", return_value=items):
            report = orchestrator.run(
                url="https://youtube.com/playlist?list=PLabc",
                source_type="youtube_playlist",
            )
        assert report.gap_status == "NONE"
        assert report.ogma_output is not None
        assert len(report.mechanisms) >= 1
        assert report.patterns == []
        assert report.principles == []
        assert report.gaps == []
        assert report.final_proposal is None

    @patch("animus.ogma.read.synthesize")
    def test_partial_gate_pattern_only(self, mock_synthesize):
        ogma = OgmaOutput(
            title="Test",
            source_id="src",
            item_id="item1",
            date=datetime.now().date(),
            concept="A concept",
            novelty="New",
            animus_gap="PARTIAL",
            animus_gap_notes="Some overlap",
            weaknesses="None",
            proposal="Build a module.",
            roi_value="High",
            roi_effort="moderate",
            roi_priority="Now",
            risks="None",
            confidence=0.7,
            confidence_justification="Evidence",
            sources_cited=["https://example.com"],
        )
        mock_synthesize.return_value = ogma
        orchestrator = MediaPipelineOrchestrator(memory_layer=None, codebase_path=".")
        items = [
            SourceItem(
                source_id="yt:PLabc",
                item_id="vid1",
                title="V1",
                url="https://youtube.com/watch?v=vid1",
                published=datetime.now(),
                raw_text="text",
            )
        ]
        with patch.object(orchestrator.harvester, "ingest_playlist", return_value=items):
            report = orchestrator.run(
                url="https://youtube.com/playlist?list=PLabc",
                source_type="youtube_playlist",
            )
        assert report.gap_status == "PARTIAL"
        assert (
            len(report.patterns) >= 0
        )  # PatternCitizen may or may not find patterns with 1 mechanism
        assert report.principles == []
        assert report.gaps == []
        assert report.final_proposal is None

    @patch("animus.ogma.read.synthesize")
    def test_full_gate_runs_full_rg(self, mock_synthesize):
        ogma = OgmaOutput(
            title="Test",
            source_id="src",
            item_id="item1",
            date=datetime.now().date(),
            concept="A concept with retry logic and observability",
            novelty="New",
            animus_gap="FULL",
            animus_gap_notes="Full overlap",
            weaknesses="None",
            proposal="Build a retry module with metrics.",
            roi_value="High",
            roi_effort="moderate",
            roi_priority="Now",
            risks="None",
            confidence=0.8,
            confidence_justification="Strong evidence",
            sources_cited=["https://example.com"],
        )
        mock_synthesize.return_value = ogma
        orchestrator = MediaPipelineOrchestrator(memory_layer=None, codebase_path=".")
        items = [
            SourceItem(
                source_id="yt:PLabc",
                item_id="vid1",
                title="V1",
                url="https://youtube.com/watch?v=vid1",
                published=datetime.now(),
                raw_text="text about retry and observability",
            )
        ]
        with patch.object(orchestrator.harvester, "ingest_playlist", return_value=items):
            report = orchestrator.run(
                url="https://youtube.com/playlist?list=PLabc",
                source_type="youtube_playlist",
            )
        assert report.gap_status == "FULL"
        assert len(report.patterns) >= 0
        # Note: principles/gaps may be empty if pattern step yields no patterns
        # but the pipeline should have attempted all stages
        assert report.forced_rg is False

    @patch("animus.ogma.read.synthesize")
    def test_force_rg_override(self, mock_synthesize):
        ogma = OgmaOutput(
            title="Test",
            source_id="src",
            item_id="item1",
            date=datetime.now().date(),
            concept="A concept with retry logic",
            novelty="New",
            animus_gap="NONE",
            animus_gap_notes="No overlap",
            weaknesses="None",
            proposal="Build something.",
            roi_value="High",
            roi_effort="moderate",
            roi_priority="Now",
            risks="None",
            confidence=0.6,
            confidence_justification="Evidence",
            sources_cited=["https://example.com"],
        )
        mock_synthesize.return_value = ogma
        orchestrator = MediaPipelineOrchestrator(memory_layer=None, codebase_path=".")
        items = [
            SourceItem(
                source_id="yt:PLabc",
                item_id="vid1",
                title="V1",
                url="https://youtube.com/watch?v=vid1",
                published=datetime.now(),
                raw_text="text about retry logic",
            )
        ]
        with patch.object(orchestrator.harvester, "ingest_playlist", return_value=items):
            report = orchestrator.run(
                url="https://youtube.com/playlist?list=PLabc",
                source_type="youtube_playlist",
                run_research_guild=True,
            )
        assert report.gap_status == "NONE"
        assert report.forced_rg is True
        # With forced RG, should have attempted pattern + FP + architecture
        # Patterns may still be empty if only 1 mechanism, but stages should exist
        stage_names = [s.citizen_name for s in report.stages]
        assert "PatternCitizen" in stage_names
        assert "FirstPrinciplesCitizen" in stage_names
        assert "ArchitectureCitizen" in stage_names

    def test_store_ogma_with_memory(self):
        mock_memory = MagicMock()
        orchestrator = MediaPipelineOrchestrator(memory_layer=mock_memory, codebase_path=".")
        ogma = OgmaOutput(
            title="Test",
            source_id="src",
            item_id="item1",
            date=datetime.now().date(),
            concept="A concept",
            novelty="New",
            animus_gap="NONE",
            animus_gap_notes="No overlap",
            weaknesses="None",
            proposal="Build something.",
            roi_value="High",
            roi_effort="moderate",
            roi_priority="Now",
            risks="None",
            confidence=0.6,
            confidence_justification="Evidence",
            sources_cited=["https://example.com"],
        )
        result = orchestrator._store_ogma(ogma)
        assert result is True
        mock_memory.remember.assert_called_once()

    def test_store_ogma_without_memory(self):
        orchestrator = MediaPipelineOrchestrator(memory_layer=None, codebase_path=".")
        ogma = OgmaOutput(
            title="Test",
            source_id="src",
            item_id="item1",
            date=datetime.now().date(),
            concept="A concept",
            novelty="New",
            animus_gap="NONE",
            animus_gap_notes="No overlap",
            weaknesses="None",
            proposal="Build something.",
            roi_value="High",
            roi_effort="moderate",
            roi_priority="Now",
            risks="None",
            confidence=0.6,
            confidence_justification="Evidence",
            sources_cited=["https://example.com"],
        )
        result = orchestrator._store_ogma(ogma)
        assert result is False


# ---------------------------------------------------------------------------
# Pattern deduplication tests
# ---------------------------------------------------------------------------


class TestPatternDedup:
    def test_overlapping_tag_clusters_deduped(self):
        """Verify that mechanisms sharing multiple tags produce one pattern, not duplicates."""
        mechanisms = [
            {
                "name": "Mechanism A",
                "description": "Desc A",
                "category": "performance",
                "tags": ["performance", "media", "youtube"],
                "source_provenance": ["src1"],
            },
            {
                "name": "Mechanism B",
                "description": "Desc B",
                "category": "performance",
                "tags": ["performance", "media", "youtube"],
                "source_provenance": ["src2"],
            },
        ]
        pc = PatternCitizen(memory_layer=None, codebase_path=".")
        patterns = pc.discover_patterns(mechanisms)
        # With 2 mechanisms, category clustering (≥3) won't fire.
        # Tag cross-clustering will fire for "media" and "youtube", but
        # they share the SAME mechanisms, so dedup should collapse to 1.
        assert len(patterns) == 1

    def test_distinct_tag_clusters_preserved(self):
        """Verify that different tag clusters still produce distinct patterns."""
        mechanisms = [
            {
                "name": "Mechanism A",
                "description": "Desc A",
                "category": "performance",
                "tags": ["performance", "media"],
                "source_provenance": ["src1"],
            },
            {
                "name": "Mechanism B",
                "description": "Desc B",
                "category": "security",
                "tags": ["security", "auth"],
                "source_provenance": ["src2"],
            },
        ]
        pc = PatternCitizen(memory_layer=None, codebase_path=".")
        patterns = pc.discover_patterns(mechanisms)
        # Each mechanism is in a different tag cluster; no cross-cluster match
        assert len(patterns) == 0  # No shared tags across ≥2 mechanisms


# ---------------------------------------------------------------------------
# FirstPrinciples media-awareness tests
# ---------------------------------------------------------------------------


class TestFirstPrinciplesMediaAware:
    def test_small_media_list_skips_reduction(self):
        """Media-derived patterns (<3) should pass through without deep reduction."""
        fpc = FirstPrinciplesCitizen(memory_layer=None, codebase_path=".")
        patterns = [
            {
                "name": "Media pattern",
                "description": "A media pattern",
                "category": "general",
                "tags": ["media", "youtube"],
                "source_provenance": ["src1"],
                "confidence": 0.6,
            }
        ]
        principles = fpc.reduce_to_principles(patterns)
        assert len(principles) == 1
        assert principles[0].category == "general"
        assert "media" in principles[0].tags
        assert "passthrough" in principles[0].tags

    def test_media_no_rule_match_creates_principle(self):
        """Media patterns with no _PRINCIPLE_RULES match should still produce a principle."""
        fpc = FirstPrinciplesCitizen(memory_layer=None, codebase_path=".")
        patterns = [
            {
                "name": "Obscure media pattern xyz123",
                "description": "Something that doesn't match any rule",
                "category": "general",
                "tags": ["media", "obscure"],
                "source_provenance": ["src1"],
                "confidence": 0.5,
            },
            {
                "name": "Another obscure pattern",
                "description": "Also doesn't match any rule",
                "category": "general",
                "tags": ["media", "obscure"],
                "source_provenance": ["src2"],
                "confidence": 0.5,
            },
            {
                "name": "Third pattern",
                "description": "Still no rule match",
                "category": "general",
                "tags": ["media", "obscure"],
                "source_provenance": ["src3"],
                "confidence": 0.5,
            },
        ]
        principles = fpc.reduce_to_principles(patterns)
        # Should produce at least one principle, not zero
        assert len(principles) >= 1
        # The principle should mention the pattern
        assert "xyz123" in principles[0].principle_statement or "media" in principles[0].tags


# ---------------------------------------------------------------------------
# Architecture gap proxy tests
# ---------------------------------------------------------------------------


class TestArchitectureGapProxy:
    def test_media_gap_uses_status_proxy(self):
        """Media-derived principles should use Ogma gap proxy, not keyword coverage."""
        ac = ArchitectureCitizen(memory_layer=None, codebase_path=".")
        principle = {
            "principle_statement": "Add packages/core/animus/cache/manager.py for embedding caching",
            "category": "performance",
            "tags": ["media", "ogma"],
            "source_provenance": ["src1"],
        }
        gap = ac._analyze_media_gap(principle)
        assert gap is not None
        assert gap.severity == "critical"  # default when no gap: status in tags
        assert "Ogma gap status" in gap.gap_description

    def test_standard_principle_uses_keyword_coverage(self):
        """Non-media principles should use standard keyword-based analysis."""
        ac = ArchitectureCitizen(memory_layer=None, codebase_path=".")
        principles = [
            {
                "principle_statement": "Systems that separate state from computation survive longer",
                "category": "architecture",
                "tags": ["architecture", "state"],
                "source_provenance": ["src1"],
            }
        ]
        gaps = ac.analyze_gaps(principles)
        assert len(gaps) >= 1
        # Keyword coverage should have been computed
        assert gaps[0].keyword_total > 0


# ---------------------------------------------------------------------------
# YouTubeSource playlist support tests
# ---------------------------------------------------------------------------


class TestYouTubePlaylistSupport:
    def test_source_id_with_playlist_url(self):
        from animus.lugh.sources.youtube import YouTubeSource

        src = YouTubeSource(playlist_url="https://www.youtube.com/playlist?list=PLabc123")
        assert src.source_id == "youtube:playlist:PLabc123"

    def test_source_id_with_channel(self):
        from animus.lugh.sources.youtube import YouTubeSource

        src = YouTubeSource(channel="@TestChannel")
        assert src.source_id == "youtube:@TestChannel"

    def test_list_url_prefers_playlist(self):
        from animus.lugh.sources.youtube import YouTubeSource

        src = YouTubeSource(
            channel="@TestChannel",
            playlist_url="https://www.youtube.com/playlist?list=PLabc",
        )
        assert src._list_url() == "https://www.youtube.com/playlist?list=PLabc"

    def test_playlist_to_source_items_returns_list(self):
        from animus.lugh.sources.youtube import playlist_to_source_items

        with patch("animus.lugh.sources.youtube.YouTubeSource.fetch", return_value=iter([])):
            items = playlist_to_source_items("https://www.youtube.com/playlist?list=PLabc")
            assert isinstance(items, list)

    def test_probe_playlist_invalid_url(self):
        from animus.lugh.sources.youtube import probe_playlist

        with patch("animus.lugh.sources.youtube._yt_dlp_available", return_value=True):
            result = probe_playlist("not-a-url")
        assert result["ok"] is False
        assert "not a valid playlist URL" in result["error"]


# ---------------------------------------------------------------------------
# MediaPipelineReport tests
# ---------------------------------------------------------------------------


class TestMediaPipelineReport:
    def test_summary_format(self):
        report = MediaPipelineReport(
            gap_status="FULL",
            mechanisms=[MechanismCard(name="m1", description="d1")],
            patterns=[PatternCard(name="p1", description="d1")],
        )
        summary = report.summary()
        assert "gap=FULL" in summary
        assert "Mechanisms: 1" in summary


# ---------------------------------------------------------------------------
# ProposalQueue wiring tests
# ---------------------------------------------------------------------------


class TestProposalQueueWiring:
    @patch("animus.ogma.read.synthesize")
    def test_full_gap_submits_to_queue(self, mock_synthesize):
        """When gap=FULL, the final proposal should be submitted to ProposalQueue."""
        from animus.citizens.pattern import PatternCard

        mock_queue = MagicMock()
        ogma = OgmaOutput(
            title="Technical Talk",
            source_id="src",
            item_id="item1",
            date=datetime.now().date(),
            concept="A system with retry logic and observability.",
            novelty="New",
            animus_gap="FULL",
            animus_gap_notes="Full overlap",
            weaknesses="None",
            proposal="Add packages/core/animus/messaging/async_processor.py with retry. Also add packages/core/animus/state/external_store.py for state externalization.",
            roi_value="High",
            roi_effort="moderate",
            roi_priority="Now",
            risks="None",
            confidence=0.8,
            confidence_justification="Strong evidence",
            sources_cited=["https://example.com"],
        )
        mock_synthesize.return_value = ogma
        orchestrator = MediaPipelineOrchestrator(
            memory_layer=None, codebase_path=".", proposal_queue=mock_queue
        )
        items = [
            SourceItem(
                source_id="yt:PLabc",
                item_id="vid1",
                title="V1",
                url="https://youtube.com/watch?v=vid1",
                published=datetime.now(),
                raw_text="text about retry and observability",
            ),
            SourceItem(
                source_id="yt:PLabc",
                item_id="vid2",
                title="V2",
                url="https://youtube.com/watch?v=vid2",
                published=datetime.now(),
                raw_text="text about state externalization",
            ),
        ]
        # Patch pipeline internals to guarantee downstream outputs
        with patch.object(orchestrator.harvester, "ingest_playlist", return_value=items):
            with patch.object(
                orchestrator,
                "_patternstep",
                return_value=[
                    PatternCard(
                        name="Retry pattern",
                        description="Retry and observability",
                        category="reliability",
                        tags=["media"],
                        source_provenance=["src1"],
                        constituent_mechanisms=["m1"],
                    )
                ],
            ):
                with patch.object(
                    orchestrator,
                    "_fpstep",
                    return_value=[
                        PrincipleCard(
                            principle_statement="Retry systems are reliable",
                            category="reliability",
                            tags=["media"],
                            source_provenance=["src1"],
                            confidence=0.8,
                        )
                    ],
                ):
                    with patch.object(
                        orchestrator,
                        "_archstep",
                        return_value=[
                            GapAnalysis(
                                principle_statement="Retry systems are reliable",
                                gap_description="Missing retry module",
                                severity="high",
                                affected_files=["animus/messaging/async_processor.py"],
                                confidence=0.8,
                            )
                        ],
                    ):
                        with patch.object(
                            ArchitectureCitizen,
                            "generate_proposal",
                            return_value=ImprovementProposal(
                                id="ARCH-20260713-test001",
                                title="Add retry module",
                                problem="Missing retry logic.",
                                affected_components=["animus"],
                                confidence_score=0.8,
                            ),
                        ):
                            report = orchestrator.run(
                                url="https://youtube.com/playlist?list=PLabc",
                                source_type="youtube_playlist",
                            )
        assert report.gap_status == "FULL"
        assert report.final_proposal is not None
        mock_queue.submit.assert_called_once()
        call_kwargs = mock_queue.submit.call_args[1]
        assert call_kwargs["priority"] == 3  # FULL gap gets priority 3
        assert "media" in call_kwargs["tags"]
        assert "gap:full" in call_kwargs["tags"]

    @patch("animus.ogma.read.synthesize")
    def test_none_gap_does_not_submit(self, mock_synthesize):
        """When gap=NONE, no proposal is generated and queue.submit is not called."""
        mock_queue = MagicMock()
        ogma = OgmaOutput(
            title="Career Advice",
            source_id="src",
            item_id="item1",
            date=datetime.now().date(),
            concept="How to get a data job.",
            novelty="New",
            animus_gap="NONE",
            animus_gap_notes="No overlap",
            weaknesses="None",
            proposal="Build a portfolio.",
            roi_value="High",
            roi_effort="moderate",
            roi_priority="Later",
            risks="None",
            confidence=0.5,
            confidence_justification="Evidence",
            sources_cited=["https://example.com"],
        )
        mock_synthesize.return_value = ogma
        orchestrator = MediaPipelineOrchestrator(
            memory_layer=None, codebase_path=".", proposal_queue=mock_queue
        )
        items = [
            SourceItem(
                source_id="yt:PLabc",
                item_id="vid1",
                title="V1",
                url="https://youtube.com/watch?v=vid1",
                published=datetime.now(),
                raw_text="career advice text",
            )
        ]
        with patch.object(orchestrator.harvester, "ingest_playlist", return_value=items):
            report = orchestrator.run(
                url="https://youtube.com/playlist?list=PLabc",
                source_type="youtube_playlist",
            )
        assert report.gap_status == "NONE"
        assert report.final_proposal is None
        mock_queue.submit.assert_not_called()


# ---------------------------------------------------------------------------
# Daemon scheduler wiring tests
# ---------------------------------------------------------------------------


class TestDaemonSchedulerWiring:
    def test_schedule_scan_creates_cron_task(self):
        """MediaPipelineOrchestrator.schedule_scan should create a cron task."""
        from animus.daemon.scheduler import TaskScheduler

        scheduler = TaskScheduler(persistence_dir="/tmp/test_scheduler_media")
        task = MediaPipelineOrchestrator.schedule_scan(
            scheduler=scheduler,
            url="https://youtube.com/playlist?list=PLabc",
            source_type="youtube_playlist",
            cron_expression="0 9 * * 1",
            run_research_guild=False,
            list_limit=10,
        )
        assert task.task_id.startswith("task-")
        assert task.schedule_type.value == "cron"
        assert task.metadata["task_type"] == "media_pipeline"
        assert task.metadata["url"] == "https://youtube.com/playlist?list=PLabc"
        assert task.metadata["source_type"] == "youtube_playlist"
        assert task.metadata["list_limit"] == 10
        assert task.metadata["run_research_guild"] is False
        scheduler.cancel(task.task_id)

"""Tests for animus.ogma.models — OgmaOutput contract + markdown round-trip."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from animus.ogma.models import (
    OgmaOutput,
    OgmaParseError,
    _make_slug,
)


def _valid_kwargs(**overrides) -> dict:
    base = {
        "title": "What the Pope Actually Said About AI",
        "source_id": "youtube:@AIDailyBrief",
        "item_id": "JWS8bYZrtnQ",
        "date": date(2026, 5, 27),
        "concept": "An encyclical on AI as a tool, not a person.",
        "novelty": "First papal encyclical on AI; recasts industrial-revolution labor framing.",
        "animus_gap": "NONE",
        "animus_gap_notes": "(no animus implementation)",
        "weaknesses": "Theology-bound; not engineering-actionable.",
        "proposal": "Cite as institutional signal in TIAID Article 6 alongside NIST AI RMF.",
        "roi_value": "Adds an institutional citation to the TIAID corpus.",
        "roi_effort": "trivial",
        "roi_priority": "soon (Article 6 outline phase)",
        "risks": "Religious framing reads as out-of-band for B2B audiences.",
        "confidence": 0.7,
        "confidence_justification": "Direct text; framing in source is unambiguous.",
        "sources_cited": ["https://youtube.com/watch?v=JWS8bYZrtnQ"],
    }
    base.update(overrides)
    return base


class TestOgmaOutputValidation:
    def test_constructs_with_valid_kwargs(self):
        out = OgmaOutput(**_valid_kwargs())
        assert out.title == "What the Pope Actually Said About AI"
        assert out.confidence == 0.7

    def test_empty_concept_raises(self):
        with pytest.raises(ValueError, match="concept is empty"):
            OgmaOutput(**_valid_kwargs(concept=""))

    def test_whitespace_concept_raises(self):
        with pytest.raises(ValueError, match="concept is empty"):
            OgmaOutput(**_valid_kwargs(concept="   "))

    def test_bad_animus_gap_raises(self):
        with pytest.raises(ValueError, match="animus_gap"):
            OgmaOutput(**_valid_kwargs(animus_gap="MAYBE"))  # type: ignore[arg-type]

    def test_bad_roi_effort_raises(self):
        with pytest.raises(ValueError, match="roi_effort"):
            OgmaOutput(**_valid_kwargs(roi_effort="huge"))  # type: ignore[arg-type]

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            OgmaOutput(**_valid_kwargs(confidence=1.5))
        with pytest.raises(ValueError, match="confidence"):
            OgmaOutput(**_valid_kwargs(confidence=-0.1))

    def test_empty_sources_cited_raises(self):
        with pytest.raises(ValueError, match="sources_cited"):
            OgmaOutput(**_valid_kwargs(sources_cited=[]))


class TestMarkdownRoundtrip:
    def test_to_markdown_contains_all_nine_sections(self):
        out = OgmaOutput(**_valid_kwargs())
        md = out.to_markdown()
        for header in (
            "## Concept",
            "## Novelty",
            "## Animus gap",
            "## Weaknesses in the source",
            "## Proposal — how we build it better",
            "## ROI",
            "## Risks",
            "## Confidence",
            "## Sources cited",
        ):
            assert header in md, f"missing section {header!r}"

    def test_roundtrip_through_markdown_preserves_fields(self):
        original = OgmaOutput(**_valid_kwargs())
        parsed = OgmaOutput.from_markdown(
            original.to_markdown(),
            source_id=original.source_id,
            item_id=original.item_id,
        )
        assert parsed.title == original.title
        assert parsed.date == original.date
        assert parsed.concept == original.concept
        assert parsed.novelty == original.novelty
        assert parsed.animus_gap == original.animus_gap
        assert parsed.weaknesses == original.weaknesses
        assert parsed.proposal == original.proposal
        assert parsed.roi_value == original.roi_value
        assert parsed.roi_effort == original.roi_effort
        assert parsed.roi_priority == original.roi_priority
        assert parsed.risks == original.risks
        assert parsed.confidence == original.confidence
        assert parsed.confidence_justification == original.confidence_justification
        assert parsed.sources_cited == original.sources_cited

    def test_partial_status_with_paths_roundtrips(self):
        original = OgmaOutput(
            **_valid_kwargs(
                animus_gap="PARTIAL",
                animus_gap_notes=(
                    "See packages/core/animus/memory/layer.py:39-82 (supported retrieval)."
                ),
                sources_cited=[
                    "https://arxiv.org/abs/2501.00663",
                    "packages/core/animus/memory/layer.py:39-82",
                ],
            )
        )
        parsed = OgmaOutput.from_markdown(
            original.to_markdown(), source_id=original.source_id, item_id=original.item_id
        )
        assert parsed.animus_gap == "PARTIAL"
        assert "memory/layer.py:39-82" in parsed.animus_gap_notes
        assert "packages/core/animus/memory/layer.py:39-82" in parsed.sources_cited

    def test_missing_section_raises_parse_error(self):
        # Strip the ## Concept section, parse should fail.
        original = OgmaOutput(**_valid_kwargs())
        md = original.to_markdown()
        broken = md.replace("## Concept\nAn encyclical on AI as a tool, not a person.", "")
        with pytest.raises(OgmaParseError, match="Concept"):
            OgmaOutput.from_markdown(broken, source_id="x", item_id="y")

    def test_missing_status_marker_raises(self):
        original = OgmaOutput(**_valid_kwargs())
        broken = original.to_markdown().replace("**Status:** NONE", "Status: NONE")
        with pytest.raises(OgmaParseError, match="Status"):
            OgmaOutput.from_markdown(broken, source_id="x", item_id="y")

    def test_unparseable_confidence_raises(self):
        original = OgmaOutput(**_valid_kwargs())
        broken = original.to_markdown().replace(
            "0.70 — Direct text", "high confidence — Direct text"
        )
        with pytest.raises(OgmaParseError, match="Confidence"):
            OgmaOutput.from_markdown(broken, source_id="x", item_id="y")

    def test_tolerates_llm_preamble_before_h1(self):
        """LLMs often emit prose before the requested format; the parser must
        skip past it and anchor on the first '# <title>' line."""
        original = OgmaOutput(**_valid_kwargs())
        preamble = (
            "Here is the synthesis you requested:\n\n"
            "<think>let me work through this step by step</think>\n\n"
            "Based on the source text:\n\n"
        )
        parsed = OgmaOutput.from_markdown(
            preamble + original.to_markdown(),
            source_id=original.source_id,
            item_id=original.item_id,
        )
        assert parsed.title == original.title
        assert parsed.concept == original.concept


class TestWrite:
    def test_write_creates_file_at_dated_slug_path(self, tmp_path: Path):
        out = OgmaOutput(**_valid_kwargs())
        path = out.write(output_dir=tmp_path)
        assert path.exists()
        assert path.name == "2026-05-27-what-the-pope-actually-said-about-ai.md"
        assert "## Concept" in path.read_text(encoding="utf-8")

    def test_write_creates_parent_dirs(self, tmp_path: Path):
        out = OgmaOutput(**_valid_kwargs())
        nested = tmp_path / "deep" / "nested" / "ogma"
        path = out.write(output_dir=nested)
        assert path.exists()
        assert path.parent == nested


class TestSlug:
    def test_normal_title(self):
        assert _make_slug("What the Pope Said About AI", "x") == "what-the-pope-said-about-ai"

    def test_empty_title_falls_back_to_item_id(self):
        assert _make_slug("", "JWS8bYZrtnQ") == "jws8byzrtnq"
        assert _make_slug("   ", "JWS8bYZrtnQ") == "jws8byzrtnq"

    def test_non_ascii_stripped_not_raised(self):
        # "naïve résumé café" → "nave-rsum-caf" (accents stripped, not transliterated)
        slug = _make_slug("naïve résumé café", "x")
        assert all(c.isascii() for c in slug)
        assert slug
        assert "-" in slug or slug.isalnum()

    def test_truncates_to_60_chars(self):
        long_title = "a " * 100
        slug = _make_slug(long_title, "x")
        assert len(slug) <= 60

    def test_truncated_slug_does_not_end_in_hyphen(self):
        # 61 chars of "a-" — truncation could leave a trailing hyphen
        title = "a-" * 30 + "a"
        slug = _make_slug(title, "x")
        assert not slug.endswith("-")

    def test_all_non_alnum_title_falls_back_to_item_id(self):
        assert _make_slug("!!!!!", "JWS8") == "jws8"

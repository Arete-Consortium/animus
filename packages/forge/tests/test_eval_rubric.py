"""Tests for evaluation/rubric.py — Rubric artifact + YAML + library."""

from __future__ import annotations

from pathlib import Path

import pytest

from animus_forge.evaluation.base import EvalCase
from animus_forge.evaluation.rubric import (
    DEFAULT_BANDS,
    GradeBand,
    Rubric,
    RubricDim,
    RubricLibrary,
)


def test_composite_score_weighted_average():
    rubric = Rubric(
        name="r",
        dims=[
            RubricDim(name="a", metric="ContainsMetric", weight=3.0),
            RubricDim(name="b", metric="LengthMetric", weight=1.0),
        ],
    )
    score = rubric.composite_score({"a": 1.0, "b": 0.0})
    # 3*1 + 1*0 = 3; /4 = 0.75
    assert score == pytest.approx(0.75)


def test_composite_score_missing_dim_skipped():
    rubric = Rubric(
        name="r",
        dims=[
            RubricDim(name="a", metric="ContainsMetric", weight=1.0),
            RubricDim(name="b", metric="LengthMetric", weight=1.0),
        ],
    )
    score = rubric.composite_score({"a": 0.8})
    assert score == pytest.approx(0.8)


def test_composite_score_no_dims_returns_zero():
    rubric = Rubric(name="r", dims=[])
    assert rubric.composite_score({}) == 0.0


def test_band_for_returns_letter():
    rubric = Rubric(name="r")
    assert rubric.band_for(0.95) == "A"
    assert rubric.band_for(0.85) == "B"
    assert rubric.band_for(0.75) == "C"
    assert rubric.band_for(0.65) == "D"
    assert rubric.band_for(0.10) == "F"


def test_band_for_custom_bands():
    rubric = Rubric(
        name="r",
        bands=[GradeBand("PASS", 0.5), GradeBand("FAIL", 0.0)],
    )
    assert rubric.band_for(0.7) == "PASS"
    assert rubric.band_for(0.3) == "FAIL"


def test_content_hash_stable_across_instances():
    r1 = Rubric(
        name="r",
        version="1.0.0",
        dims=[RubricDim(name="a", metric="ContainsMetric", weight=1.0)],
    )
    r2 = Rubric(
        name="r",
        version="1.0.0",
        dims=[RubricDim(name="a", metric="ContainsMetric", weight=1.0)],
    )
    assert r1.content_hash() == r2.content_hash()


def test_content_hash_changes_with_weight():
    r1 = Rubric(
        name="r",
        dims=[RubricDim(name="a", metric="ContainsMetric", weight=1.0)],
    )
    r2 = Rubric(
        name="r",
        dims=[RubricDim(name="a", metric="ContainsMetric", weight=2.0)],
    )
    assert r1.content_hash() != r2.content_hash()


def test_build_metrics_resolves_classes():
    rubric = Rubric(
        name="r",
        dims=[
            RubricDim(name="correctness", metric="ContainsMetric", weight=1.0),
            RubricDim(name="length", metric="LengthMetric", weight=1.0),
        ],
    )
    metrics = rubric.build_metrics()
    assert len(metrics) == 2
    names = [m.name for m in metrics]
    assert names == ["correctness", "length"]


def test_build_metrics_unknown_class_raises():
    rubric = Rubric(
        name="r",
        dims=[RubricDim(name="x", metric="DoesNotExist")],
    )
    with pytest.raises(ValueError, match="Unknown metric"):
        rubric.build_metrics()


def test_repeated_metric_class_preserves_dimension_names_and_configuration():
    rubric = Rubric(
        name="case-rules",
        dims=[
            RubricDim(name="meaning", metric="ExactMatchMetric", weight=3.0),
            RubricDim(
                name="casing",
                metric="ExactMatchMetric",
                kwargs={"case_sensitive": True},
            ),
        ],
    )
    case = EvalCase(input="Greeting", expected="Hello")
    scores = {
        metric.name: metric.score("hello", case.expected, case) for metric in rubric.build_metrics()
    }
    assert scores == {"meaning": 1.0, "casing": 0.0}
    assert rubric.composite_score(scores) == pytest.approx(0.75)
    assert rubric.band_for(rubric.composite_score(scores)) == "C"


def test_yaml_roundtrip(tmp_path: Path):
    original = Rubric(
        name="r",
        version="2.0.0",
        description="test",
        tags=["role:test"],
        dims=[RubricDim(name="a", metric="ContainsMetric", weight=2.5)],
    )
    path = tmp_path / "r.yaml"
    original.to_yaml(path)
    loaded = Rubric.from_yaml(path)
    assert loaded.name == original.name
    assert loaded.version == original.version
    assert len(loaded.dims) == 1
    assert loaded.dims[0].weight == 2.5
    assert loaded.content_hash() == original.content_hash()


def test_yaml_default_bands_when_missing(tmp_path: Path):
    path = tmp_path / "minimal.yaml"
    path.write_text(
        "name: minimal\ndims:\n  - name: a\n    metric: ContainsMetric\n    weight: 1.0\n"
    )
    rubric = Rubric.from_yaml(path)
    assert len(rubric.bands) == len(DEFAULT_BANDS)


def test_rubric_library_lists_rubrics(tmp_path: Path):
    (tmp_path / "one.yaml").write_text(
        "name: one\nversion: 1.0\ndims:\n  - {name: a, metric: ContainsMetric, weight: 1}\n"
    )
    (tmp_path / "two.yaml").write_text(
        "name: two\nversion: 1.0\ndims:\n  - {name: b, metric: LengthMetric, weight: 1}\n"
    )
    library = RubricLibrary(rubrics_dir=tmp_path)
    rubrics = library.list_rubrics()
    assert len(rubrics) == 2
    names = {r["name"] for r in rubrics}
    assert names == {"one", "two"}


def test_rubric_library_load_missing_raises(tmp_path: Path):
    library = RubricLibrary(rubrics_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        library.load("nope")


def test_rubric_library_missing_dir_returns_empty(tmp_path: Path):
    library = RubricLibrary(rubrics_dir=tmp_path / "nonexistent")
    assert library.list_rubrics() == []


def test_default_rubrics_load():
    """The rubrics shipped in packages/forge/rubrics/ should all parse."""
    library = RubricLibrary()
    rubrics = library.list_rubrics()
    assert len(rubrics) >= 1, "Expected at least one shipped rubric"
    for summary in rubrics:
        loaded = library.load(summary["name"])
        assert loaded.dims, f"Rubric {summary['name']} has no dims"

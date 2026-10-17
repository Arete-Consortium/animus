"""Rubrics: versioned, reusable scoring artifacts.

A Rubric is a named, versioned collection of weighted scoring dimensions
that can be applied to any EvalSuite. Unlike inline CompositeMetric, a
Rubric is authored once as YAML and reused across suites/runs.

Typical structure:
    name: code-edit-rubric
    version: 1.0.0
    dims:
      - name: correctness
        metric: ExactMatchMetric
        weight: 3.0
      - name: schema_valid
        metric: RegexMatchMetric
        weight: 1.0
        kwargs: {pattern: "^\\{"}
    bands:
      - {letter: A, floor: 0.90}
      - {letter: B, floor: 0.80}
      - {letter: F, floor: 0.0}
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .base import EvalCase, EvalMetric

JUDGE_METRIC_PROVIDER_KWARG = {
    "LLMJudgeMetric": "judge_provider",
    "FactualityMetric": "verifier_provider",
    "SafetyMetric": "safety_provider",
}


class _RubricMetric(EvalMetric):
    """Expose the rubric dimension name without changing a metric implementation."""

    def __init__(self, name: str, metric: EvalMetric) -> None:
        self._name = name
        self._metric = metric
        self.fail_fast = metric.fail_fast

    @property
    def name(self) -> str:
        return self._name

    def score(self, output: Any, expected: Any, case: EvalCase) -> float:
        return self._metric.score(output, expected, case)


@dataclass
class GradeBand:
    """A letter grade with a minimum composite score floor."""

    letter: str
    floor: float


DEFAULT_BANDS: list[GradeBand] = [
    GradeBand("A", 0.90),
    GradeBand("B", 0.80),
    GradeBand("C", 0.70),
    GradeBand("D", 0.60),
    GradeBand("F", 0.0),
]


@dataclass
class RubricDim:
    """One weighted scoring dimension in a rubric.

    Attributes:
        name: Dimension name (e.g. "correctness", "schema_valid"). This is
            also the key used in per-case metric score dicts.
        metric: Class name from ``animus_forge.evaluation.metrics``. Looked
            up reflectively at build time so the YAML stays declarative.
        weight: Relative contribution to the composite score.
        kwargs: Constructor kwargs passed when instantiating the metric.
        description: Optional human-readable hint for authors.
    """

    name: str
    metric: str
    weight: float = 1.0
    kwargs: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class Rubric:
    """Versioned, reusable scoring rubric.

    A rubric defines *what* to score (dims) and *how to grade* (bands),
    independent of *which* cases to run (suites).
    """

    name: str
    version: str = "1.0.0"
    dims: list[RubricDim] = field(default_factory=list)
    bands: list[GradeBand] = field(default_factory=lambda: list(DEFAULT_BANDS))
    description: str = ""
    tags: list[str] = field(default_factory=list)

    # -----------------------------------------------------------------
    # Scoring
    # -----------------------------------------------------------------

    def composite_score(self, dim_scores: dict[str, float]) -> float:
        """Compute weighted composite from per-dim scores.

        Missing dims are skipped rather than treated as zero — this lets
        partial runs (e.g. metric errored) still produce a defensible
        score. Callers that want strict all-dims-required behavior should
        check ``set(dim_scores) >= {d.name for d in self.dims}`` first.
        """
        total_weight = 0.0
        total_score = 0.0
        for dim in self.dims:
            if dim.name in dim_scores:
                total_weight += dim.weight
                total_score += dim_scores[dim.name] * dim.weight
        if total_weight == 0:
            return 0.0
        return total_score / total_weight

    def band_for(self, score: float) -> str:
        """Return letter grade for a composite score."""
        for band in sorted(self.bands, key=lambda b: b.floor, reverse=True):
            if score >= band.floor:
                return band.letter
        return self.bands[-1].letter if self.bands else "F"

    def content_hash(self) -> str:
        """Stable hash of rubric content — used to detect drift between runs."""
        payload = json.dumps(
            {
                "name": self.name,
                "version": self.version,
                "dims": [asdict(d) for d in self.dims],
                "bands": [asdict(b) for b in self.bands],
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # -----------------------------------------------------------------
    # Metric resolution
    # -----------------------------------------------------------------

    def build_metrics(self, provider: Any = None) -> list[EvalMetric]:
        """Resolve ``dim.metric`` strings into concrete EvalMetric instances.

        ``provider`` is injected into judge-style metrics (LLMJudgeMetric,
        FactualityMetric, SafetyMetric) so YAML authors don't have to
        wire it manually. Other metrics ignore it.
        """
        from . import metrics as metrics_module

        resolved: list[EvalMetric] = []
        for dim in self.dims:
            cls = getattr(metrics_module, dim.metric, None)
            if cls is None:
                raise ValueError(
                    f"Unknown metric '{dim.metric}' in rubric '{self.name}' dim '{dim.name}'"
                )
            kwargs = dict(dim.kwargs)
            provider_kwarg = JUDGE_METRIC_PROVIDER_KWARG.get(dim.metric)
            if provider_kwarg and provider is not None:
                kwargs.setdefault(provider_kwarg, provider)
            instance = cls(**kwargs)
            # Metrics with a fixed name property cannot be renamed by assigning
            # _name. Preserve dimension identity through the EvalMetric interface.
            resolved.append(_RubricMetric(dim.name, instance))
        return resolved

    # -----------------------------------------------------------------
    # YAML I/O
    # -----------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str | Path) -> Rubric:
        """Load rubric from YAML."""
        import yaml

        path = Path(path)
        with path.open() as f:
            data = yaml.safe_load(f) or {}

        dims = [RubricDim(**d) for d in data.get("dims", [])]
        bands_data = data.get("bands") or [asdict(b) for b in DEFAULT_BANDS]
        bands = [GradeBand(**b) for b in bands_data]

        return cls(
            name=data.get("name", path.stem),
            version=data.get("version", "1.0.0"),
            dims=dims,
            bands=bands,
            description=data.get("description", ""),
            tags=data.get("tags", []),
        )

    def to_yaml(self, path: str | Path) -> None:
        """Save rubric to YAML."""
        import yaml

        payload = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tags": self.tags,
            "bands": [asdict(b) for b in self.bands],
            "dims": [asdict(d) for d in self.dims],
        }
        Path(path).write_text(yaml.dump(payload, default_flow_style=False, sort_keys=False))


# =========================================================================
# Library
# =========================================================================


DEFAULT_RUBRICS_DIR = Path(__file__).resolve().parents[3] / "rubrics"


class RubricLibrary:
    """Discovers and loads rubrics from a directory of YAML files.

    Defaults to ``packages/forge/rubrics/`` relative to this module.
    """

    def __init__(self, rubrics_dir: Path | None = None):
        self.rubrics_dir = rubrics_dir or DEFAULT_RUBRICS_DIR

    def list_rubrics(self) -> list[dict[str, Any]]:
        """Return summary metadata for each rubric in the directory."""
        if not self.rubrics_dir.exists():
            return []
        summaries = []
        for path in sorted(self.rubrics_dir.glob("*.yaml")):
            try:
                rubric = Rubric.from_yaml(path)
            except (OSError, ValueError, TypeError):
                continue
            summaries.append(
                {
                    "name": rubric.name,
                    "version": rubric.version,
                    "dims": len(rubric.dims),
                    "description": rubric.description,
                    "path": str(path),
                }
            )
        return summaries

    def load(self, name: str) -> Rubric:
        """Load rubric by name (filename stem)."""
        path = self.rubrics_dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(
                f"Rubric '{name}' not found in {self.rubrics_dir}. "
                f"Available: {[s['name'] for s in self.list_rubrics()]}"
            )
        return Rubric.from_yaml(path)

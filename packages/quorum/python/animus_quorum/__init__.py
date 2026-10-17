"""Convergent — Multi-agent coherence and coordination for AI systems."""

try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _version

    __version__ = _version("animus-quorum")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0+dev"

from animus_quorum.async_backend import AsyncBackendWrapper, AsyncGraphBackend
from animus_quorum.benchmark import (
    BenchmarkMetrics,
    BenchmarkSuite,
    ScenarioType,
    run_benchmark,
    run_scaling_suite,
)
from animus_quorum.constraints import (
    ConstraintCheckResult,
    ConstraintEngine,
    ConstraintKind,
    GateResult,
    TypedConstraint,
)
from animus_quorum.contract import (
    DEFAULT_CONTRACT,
    DEFAULT_RESOLUTION_POLICY,
    DEFAULT_STABILITY_WEIGHTS,
    ConflictClass,
    ContractViolation,
    EdgeType,
    GraphInvariant,
    IntentGraphContract,
    MutationType,
    ResolutionPolicy,
    StabilityWeights,
    content_hash_intent,
    content_hash_intents,
    validate_publish,
)
from animus_quorum.coordination_bridge import GorgonBridge

# Phase 3: Coordination Protocol
from animus_quorum.coordination_config import CoordinationConfig

# Phase 4: Observability & Analysis
from animus_quorum.cycles import DependencyCycle, DependencyGraph, find_cycles, topological_order
from animus_quorum.economics import (
    Budget,
    CoordinationCostReport,
    CostModel,
    EscalationAction,
    EscalationDecision,
    EscalationPolicy,
)
from animus_quorum.event_log import CoordinationEvent, EventLog, EventType, event_timeline
from animus_quorum.flocking import FlockingCoordinator
from animus_quorum.gates import (
    CommandGate,
    CompileGate,
    ConstraintGate,
    GateReport,
    GateRunner,
    GateRunResult,
    MypyGate,
    PytestGate,
)
from animus_quorum.governor import (
    AgentBranch,
    GovernorVerdict,
    MergeGovernor,
    ProposalResult,
    VerdictKind,
)
from animus_quorum.health import (
    CoordinationHealth,
    HealthChecker,
    IntentGraphHealth,
    ScoringHealth,
    StigmergyHealth,
    VotingHealth,
    health_report,
)
from animus_quorum.intent import (
    DEFAULT_STABILITY_SCORER,
    Adjustment,
    ConflictReport,
    Constraint,
    ConstraintSeverity,
    DefaultStabilityScorer,
    Evidence,
    EvidenceKind,
    Intent,
    InterfaceKind,
    InterfaceSpec,
    ResolutionResult,
    StabilityScorer,
)
from animus_quorum.matching import (
    names_overlap,
    normalize_constraint_target,
    normalize_name,
    normalize_type,
    parse_signature,
    signatures_compatible,
)
from animus_quorum.protocol import (
    AgentIdentity,
    ConsensusRequest,
    Decision,
    DecisionOutcome,
    QuorumLevel,
    Signal,
    StigmergyMarker,
    Vote,
    VoteChoice,
)
from animus_quorum.replay import ReplayLog, ReplayResult
from animus_quorum.resolver import GraphBackend, IntentResolver, PythonGraphBackend
from animus_quorum.rust_backend import HAS_RUST, RustGraphBackend
from animus_quorum.score_store import ScoreStore
from animus_quorum.scoring import PhiScorer
from animus_quorum.semantic import (
    ConstraintApplicability,
    SemanticMatch,
    SemanticMatcher,
    TrajectoryPrediction,
)
from animus_quorum.signal_backend import FilesystemSignalBackend, SignalBackend
from animus_quorum.signal_bus import SignalBus
from animus_quorum.sqlite_backend import SQLiteBackend
from animus_quorum.sqlite_signal_backend import SQLiteSignalBackend
from animus_quorum.stigmergy import StigmergyField
from animus_quorum.triumvirate import Triumvirate
from animus_quorum.versioning import GraphSnapshot, MergeResult, VersionedGraph
from animus_quorum.visualization import dot_graph, html_report, overlap_matrix, text_table

__all__ = [
    # Layer 1: Constraint Engine
    "ConstraintCheckResult",
    "ConstraintEngine",
    "ConstraintKind",
    "GateResult",
    "TypedConstraint",
    # Layer 3: Economics
    "Budget",
    "CoordinationCostReport",
    "CostModel",
    "EscalationAction",
    "EscalationDecision",
    "EscalationPolicy",
    # Governor (integrates all 3 layers)
    "AgentBranch",
    "GovernorVerdict",
    "MergeGovernor",
    "ProposalResult",
    "VerdictKind",
    # Contract
    "ConflictClass",
    "ContractViolation",
    "DEFAULT_CONTRACT",
    "DEFAULT_RESOLUTION_POLICY",
    "DEFAULT_STABILITY_WEIGHTS",
    "EdgeType",
    "GraphInvariant",
    "IntentGraphContract",
    "MutationType",
    "ResolutionPolicy",
    "StabilityWeights",
    "content_hash_intent",
    "content_hash_intents",
    "validate_publish",
    # Core types
    "Adjustment",
    "ConflictReport",
    "Constraint",
    "ConstraintApplicability",
    "ConstraintSeverity",
    "DEFAULT_STABILITY_SCORER",
    "DefaultStabilityScorer",
    "StabilityScorer",
    "Evidence",
    "EvidenceKind",
    "Intent",
    "IntentResolver",
    "InterfaceKind",
    "InterfaceSpec",
    "ResolutionResult",
    # Backends
    "AsyncBackendWrapper",
    "AsyncGraphBackend",
    "GraphBackend",
    "HAS_RUST",
    "PythonGraphBackend",
    "RustGraphBackend",
    "SQLiteBackend",
    # Replay
    "ReplayLog",
    "ReplayResult",
    # Semantic
    "SemanticMatch",
    "SemanticMatcher",
    "TrajectoryPrediction",
    # Versioning
    "GraphSnapshot",
    "MergeResult",
    "VersionedGraph",
    # Matching utilities
    "names_overlap",
    "normalize_constraint_target",
    "normalize_name",
    "normalize_type",
    "parse_signature",
    "signatures_compatible",
    # Benchmark
    "BenchmarkMetrics",
    "BenchmarkSuite",
    "ScenarioType",
    "run_benchmark",
    "run_scaling_suite",
    # Gates (subprocess-backed evidence)
    "CommandGate",
    "CompileGate",
    "ConstraintGate",
    "GateReport",
    "GateRunResult",
    "GateRunner",
    "MypyGate",
    "PytestGate",
    # Visualization
    "dot_graph",
    "html_report",
    "overlap_matrix",
    "text_table",
    # Factories
    "create_delegation_checker",
    # Phase 3: Coordination Protocol
    "AgentIdentity",
    "ConsensusRequest",
    "CoordinationConfig",
    "Decision",
    "DecisionOutcome",
    "QuorumLevel",
    "Signal",
    "StigmergyMarker",
    "Vote",
    "VoteChoice",
    # Phase 3: Phi-Weighted Scoring
    "PhiScorer",
    "ScoreStore",
    # Phase 3: Triumvirate Voting
    "Triumvirate",
    # Phase 3: Signal Bus
    "FilesystemSignalBackend",
    "SignalBackend",
    "SignalBus",
    "SQLiteSignalBackend",
    # Phase 3: Stigmergy
    "StigmergyField",
    # Phase 3: Flocking
    "FlockingCoordinator",
    # Phase 3: Gorgon Integration
    "GorgonBridge",
    # Phase 4: Health Dashboard
    "CoordinationHealth",
    "HealthChecker",
    "IntentGraphHealth",
    "ScoringHealth",
    "StigmergyHealth",
    "VotingHealth",
    "health_report",
    # Phase 4: Cycle Detection
    "DependencyCycle",
    "DependencyGraph",
    "find_cycles",
    "topological_order",
    # Phase 4: Event Log
    "CoordinationEvent",
    "EventLog",
    "EventType",
    "event_timeline",
]

# Conditional export: AnthropicSemanticMatcher (only when anthropic installed)
try:
    from animus_quorum.semantic import AnthropicSemanticMatcher  # noqa: F401

    __all__.append("AnthropicSemanticMatcher")
except ImportError:
    pass  # anthropic not installed; AnthropicSemanticMatcher unavailable


def create_delegation_checker(
    min_stability: float = 0.0,
    backend: GraphBackend | None = None,
) -> IntentResolver:
    """Create an IntentResolver configured for delegation coherence checking.

    Convenience factory for Gorgon integration. Uses a PythonGraphBackend
    by default (in-memory, no persistence needed for delegation checks).

    Args:
        min_stability: Minimum stability threshold for overlap detection.
        backend: Optional custom backend (e.g., SQLiteBackend for persistence).

    Returns:
        Configured IntentResolver ready for delegation checking.
    """
    return IntentResolver(
        backend=backend or PythonGraphBackend(),
        min_stability=min_stability,
    )

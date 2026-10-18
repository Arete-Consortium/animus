"""``/ogma read`` — synthesize one cached lugh item into an ``OgmaOutput``.

Pipeline: ``SourceItem`` → ``verify_animus_gap`` against the animus repo →
assemble system + user prompts → ``ModelInterface.generate(prompt, system)``
→ ``OgmaOutput.from_markdown`` → ``.write()``.

Default provider is Ollama (``ModelConfig.ollama()``). Per
``[[ADL-20260511-001]] #2``, a 401/403 on a configured provider MUST NOT
silently fall back to Ollama — exceptions propagate as
``OgmaSynthesisError``. Pass an explicit ``model=CognitiveLayer(...)`` to
opt into a different provider.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from animus.cognitive import CognitiveLayer, ModelConfig, ModelInterface, create_model
from animus.lugh.sources.base import SourceItem
from animus.ogma.grounding import GapResult, verify_animus_gap
from animus.ogma.models import OgmaOutput, OgmaParseError

logger = logging.getLogger(__name__)

DEFAULT_MIN_RELEVANCE = 0.5
DEFAULT_FAILURE_DIR = Path("~/projects/notes/ogma/.failures").expanduser()


PERSONA_SYSTEM_PROMPT = """You are Ogma — the reverse-engineering synthesis persona for the Animus exocortex project. Companion to Lugh. Ethos: figure out how it works, then build it better.

DOMAIN CONTEXT (read carefully — these terms are project-specific, not their dictionary meanings):

- "Animus" = the name of an open-source Python project (a personal AI exocortex system at https://github.com/your-org/animus). NOT the Latin word for "spirit" or "intention." When you see "Animus" in this contract, it always means the codebase.
- "Animus gap" = a technical question: "does the Animus codebase already implement this concept, and if so where (file:line)?" It is NOT a philosophical critique of the source's argument.
- "Lugh" = Animus's harvest subsystem. "Ogma" = the synthesis persona you are inhabiting right now.

Your output MUST follow this exact markdown contract, with every section non-empty and in this order. Treat each section header and each bold-marker field as a LITERAL string. Do NOT rephrase or collapse them into prose.

# <Title of the source work>

**Source:** <item_id>  •  **Date:** <YYYY-MM-DD>
**Cited from:** <source_id>

## Concept
<One paragraph. What is this, really. No hedging. No "this paper proposes to possibly explore.">

## Novelty
<What's actually new here vs prior art. Cite predecessors where known. If reheated, say so.>

## Animus gap
**Status:** <NONE | PARTIAL | FULL>
<If PARTIAL/FULL: the exact file(s) + function(s) in the Animus codebase that implement the overlapping concept. Use ONLY the file paths listed in the grounding context below — never invent paths. If NONE: write one sentence explaining that the Animus codebase does not currently implement this concept, then move on. Do NOT philosophize about the source's argument — this section is about the Animus repo at ~/projects/animus, not about the source's internal logic.>

## Weaknesses in the source
<What's hand-wavy, unreproducible, missing ablations, or load-bearing on bad assumptions.>

## Proposal — how we build it better
<Concrete. Name the module (existing or new) in the Animus codebase namespace (e.g. packages/core/animus/<new_module>/). Sketch the change. Explicitly call out how this version improves on the source (sharper contract, better Forge/Quorum composition, smaller deps, reproducibility test, etc.). If Animus gap is NONE, greenfield-propose — never refuse.>

## ROI
**Value:** <one line — what this unlocks>
**Effort:** <trivial | moderate | substantial>
**Priority:** <why now / why later>

## Risks
<Reproducibility, maturity, licensing, perf, scope creep, coupling.>

## Confidence
<0.00–1.00> — <one-line justification>

## Sources cited
- <source URL or id>
- <every animus file:line ref you cited in Animus gap or Proposal — must come from the grounding context>

NON-NEGOTIABLES (each is a contract violation if missed):

1. EVERY required section above MUST be present and non-empty.
2. The "## ROI" section MUST contain exactly three lines starting with "**Value:**", "**Effort:**", "**Priority:**" in that order. Do NOT replace them with prose paragraphs.
3. "**Effort:**" MUST be exactly one of: trivial, moderate, substantial.
4. The "## Confidence" section MUST contain a number in [0.00, 1.00] formatted to 2 decimals, followed by " — ", followed by a one-line justification. Example: "0.75 — strong source but small sample size."
5. The "## Sources cited" section MUST be a bullet list using "- " prefix, one item per line. Do NOT write prose.
6. "## Animus gap" MUST begin with the literal "**Status:** NONE", "**Status:** PARTIAL", or "**Status:** FULL" marker, then a body paragraph. Do NOT omit the Status marker.
7. Animus file paths in your output MUST come from the grounding context — never invent.
8. No preamble, no closing remarks, no markdown other than the contract above.

EXAMPLE OF CORRECT OUTPUT (for a hypothetical paper on test-time learned memory):

# Titans: Learning to Memorize at Test Time

**Source:** arxiv:2501.00663  •  **Date:** 2026-04-22
**Cited from:** arxiv:cs.LG

## Concept
A new memory module that learns to memorize raw context at test time via gradient updates on a small per-instance MLP, attached to a frozen retrieval transformer.

## Novelty
First test-time-learned memory layer that updates parameters per query without retraining the base model. Prior work (Memorizing Transformers, Hopfield Layers) used fixed retrieval; Titans makes the memory itself a per-query learnable function.

## Animus gap
**Status:** NONE
The Animus codebase implements supported local/durable retrieval through packages/core/animus/memory/layer.py, but has no learned per-query memory layer.

## Weaknesses in the source
Reproducibility unclear (no released code at time of writing). Performance at scale (>100K context tokens) not validated. Interaction with existing retrieval not specified.

## Proposal — how we build it better
Add packages/core/animus/learning/test_time_memory.py with a TestTimeMemory class that wraps the supported retrieval interface as the base, with an optional learned overlay invoked per query under a feature flag. Reproducibility test baked in (deterministic seed + fixed eval set).

## ROI
**Value:** Differentiates Animus's memory tier from vanilla vector-retrieval systems
**Effort:** moderate
**Priority:** later — wait for source code release first

## Risks
Reproducibility (paper has no released implementation). Perf at production query rates unvalidated. Coupling with the supported retrieval interface may introduce silent contract drift.

## Confidence
0.60 — promising direction but reproducibility unclear without released code

## Sources cited
- https://arxiv.org/abs/2501.00663
- packages/core/animus/memory/layer.py:42-58

END OF EXAMPLE. Now produce the synthesis for the source provided in the user message, following the contract EXACTLY.
"""


class OgmaSynthesisError(RuntimeError):
    """Raised when the LLM call or response parse fails."""


def synthesize(
    item: SourceItem,
    *,
    model: ModelInterface | CognitiveLayer | None = None,
    repo_root: Path | None = None,
    min_relevance: float = DEFAULT_MIN_RELEVANCE,
    relevance_score: float | None = None,
    concept_hint: str | None = None,
    output_dir: Path | None = None,
) -> OgmaOutput | None:
    """Synthesize one ``SourceItem`` → ``OgmaOutput`` (written to disk).

    Args:
        item: the cached lugh item to read.
        model: a ``ModelInterface`` (provider) or ``CognitiveLayer``. When
            None, defaults to ``create_model(ModelConfig.ollama())`` — Ollama
            with no Anthropic key required.
        repo_root: animus repo path passed to ``verify_animus_gap``; defaults
            to ``~/projects/animus``.
        min_relevance: items scoring below this are skipped (returns None).
        relevance_score: caller-supplied score; if None, the gate passes.
        concept_hint: pin the gap-check concept; if None, derive from title.
        output_dir: override the default ``~/projects/notes/ogma/``.

    Returns:
        The written ``OgmaOutput``, or ``None`` if the item was gated out.

    Raises:
        ValueError: item has no usable text (raw_text/summary/title all empty).
        OgmaSynthesisError: the provider call raised, or the response could
            not be parsed into the contract. The raw response is dumped to
            ``~/projects/notes/ogma/.failures/`` for diagnosis.
    """
    if relevance_score is not None and relevance_score < min_relevance:
        logger.info(
            "ogma.read: skipping %s (score %.3f < %.3f)",
            item.fingerprint[:12],
            relevance_score,
            min_relevance,
        )
        return None

    source_text = item.raw_text or item.summary or item.title
    if not source_text or not source_text.strip():
        raise ValueError("read: source has no text to synthesize")

    provider = _resolve_provider(model)
    concept = concept_hint or item.title or item.summary[:120] or item.item_id
    gap = verify_animus_gap(concept, repo_root=repo_root)
    prompt = _assemble_prompt(item, source_text, gap)

    try:
        response = provider.generate(prompt, system=PERSONA_SYSTEM_PROMPT)
    except Exception as e:
        raise OgmaSynthesisError(f"provider.generate raised: {e}") from e

    try:
        output = OgmaOutput.from_markdown(response, source_id=item.source_id, item_id=item.item_id)
    except OgmaParseError as e:
        dump = _dump_failure(item, response)
        raise OgmaSynthesisError(
            f"could not parse synthesis response: {e}; raw response at {dump}"
        ) from e

    output.write(output_dir=output_dir)
    return output


def _resolve_provider(
    model: ModelInterface | CognitiveLayer | None,
) -> ModelInterface:
    """Resolve the provider for synthesis.

    1. **Explicit model arg** — if the caller passes a ``ModelInterface`` or a
       ``CognitiveLayer``, honour it exactly (unwrapping the layer's primary).
       An explicit choice always wins.
    2. **Local default** — else the existing local Ollama default.

    Returns a provider exposing ``.generate(prompt, system=None) -> str``.
    """
    if model is not None:
        if isinstance(model, CognitiveLayer):
            return model.primary
        return model
    return create_model(ModelConfig.ollama())


def _assemble_prompt(item: SourceItem, source_text: str, gap: GapResult) -> str:
    """Build the user-message text that pairs with the persona system prompt.

    Local instruction-following models (llama3, qwen2.5) lose track of long
    system prompts when the user message is large. We repeat the format
    contract at the *tail* of the user prompt — where the model's attention
    is freshest before generation — so the first response token is more
    likely to be the required ``# <Title>`` heading.
    """
    grounding_block = _format_grounding(gap)
    return (
        f"# Source\n"
        f"- title: {item.title}\n"
        f"- source_id: {item.source_id}\n"
        f"- item_id: {item.item_id}\n"
        f"- url: {item.url}\n"
        f"\n"
        f"# Grounding (the ONLY animus paths you may cite)\n"
        f"{grounding_block}\n"
        f"\n"
        f"# Source text\n"
        f"{source_text}\n"
        f"\n"
        f"---\n"
        f"\n"
        f"Now produce the Ogma synthesis for this source. Reminders:\n"
        f"\n"
        f"1. Your response MUST begin with the literal line `# {item.title}` (the\n"
        f"   source's title as a level-1 markdown heading). No preamble, no\n"
        f"   acknowledgement, no '<think>' block.\n"
        f"2. After that line, emit each of the nine `## ` sections in the order\n"
        f"   specified by the system prompt: Concept, Novelty, Animus gap,\n"
        f"   Weaknesses in the source, Proposal — how we build it better, ROI,\n"
        f"   Risks, Confidence, Sources cited.\n"
        f"3. The ## Animus gap section is about the Animus codebase at\n"
        f"   ~/projects/animus. It is NOT a philosophical critique of the source's\n"
        f"   argument. Begin the section with `**Status:** NONE`, `**Status:**\n"
        f"   PARTIAL`, or `**Status:** FULL` on its own line, then a body sentence.\n"
        f"4. The ## ROI section MUST contain exactly three bold-marker lines in\n"
        f"   this order: `**Value:**`, `**Effort:**`, `**Priority:**`. Do NOT\n"
        f"   collapse these into prose. `**Effort:**` MUST be exactly one of:\n"
        f"   trivial, moderate, substantial.\n"
        f"5. The ## Confidence section MUST be a single line: `0.NN — <one-line\n"
        f"   justification>` where NN is in [0.00, 1.00].\n"
        f"6. The ## Sources cited section MUST be a bullet list using `- ` prefix,\n"
        f"   one citation per line. Do NOT write prose.\n"
        f"7. Animus file paths cited anywhere in your output MUST come from the\n"
        f"   grounding block above. Never invent paths.\n"
        f"8. Every section MUST be non-empty.\n"
        f"\n"
        f"Match the example output from the system prompt exactly in structure.\n"
    )


def _format_grounding(gap: GapResult) -> str:
    if gap.status == "NONE":
        return (
            "Status: NONE — animus does not currently implement this concept. "
            "Greenfield-propose: name the new module path you would add, the "
            "abstractions it composes with, and the public API shape. Do NOT "
            "refuse to propose."
        )
    paths = "\n".join(f"- {p}" for p in gap.paths_read) or "(none)"
    return f"Status: {gap.status}\nNotes: {gap.notes}\nPaths read:\n{paths}"


def _dump_failure(item: SourceItem, response: str) -> Path:
    DEFAULT_FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    safe_id = item.item_id.replace("/", "_").replace(":", "_")[:60]
    path = DEFAULT_FAILURE_DIR / f"{ts}-{safe_id}.txt"
    path.write_text(response, encoding="utf-8")
    return path

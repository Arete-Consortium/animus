"""Phase C1 — close the enforcement loop END-TO-END.

The post-C0 review found C0 made the enforcement PRIMITIVES correct but the live
request path dropped the data they need, so ET enforcement and the egress tier
gate were inert in production. These tests pin the wiring:

  C1-1  executor surfaces model + input/output split so record_usage cost-weights
  C1-2  executor tags requests with the step's sensitivity (not silent PUBLIC)
  C1-3  TierRouter rebuild preserves sensitivity / tools / tool_choice
  C1-4  LlamaCppProvider gates egress (it can reach an arbitrary remote host)
  C1-14 the loop: a CONFIDENTIAL executor request is blocked by a cloud gate
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from animus_types import Sensitivity

from animus_forge.budget import BudgetConfig, BudgetManager
from animus_forge.network import EgressDeniedError
from animus_forge.providers.base import (
    CompletionRequest,
    CompletionResponse,
    ModelTier,
    ProviderConfig,
    ProviderType,
    assert_egress_allowed,
)
from animus_forge.workflow.executor_ai import AIHandlersMixin, _resolve_sensitivity
from animus_forge.workflow.loader import StepConfig

_KEY = "sk-ant-abc1234567890ABCDEFGHIJ"


# ---------------------------------------------------------------------------
# C1-2 — sensitivity resolution (fails CLOSED on a typo)
# ---------------------------------------------------------------------------


class TestResolveSensitivity:
    def test_none_defaults_public(self):
        assert _resolve_sensitivity(None) is Sensitivity.PUBLIC

    def test_string_tier_names(self):
        assert _resolve_sensitivity("confidential") is Sensitivity.CONFIDENTIAL
        assert _resolve_sensitivity("SECRET") is Sensitivity.SECRET

    def test_enum_passthrough(self):
        assert _resolve_sensitivity(Sensitivity.PERSONAL) is Sensitivity.PERSONAL

    def test_unknown_fails_closed_to_secret(self):
        # A typo must never silently WIDEN egress — fail to the strictest tier.
        assert _resolve_sensitivity("publik") is Sensitivity.SECRET


# ---------------------------------------------------------------------------
# C1-1 + C1-2 — the executor tags sensitivity and surfaces the token breakdown
# ---------------------------------------------------------------------------


class _CaptureProvider:
    """Stands in for the Ollama provider; records the request it receives."""

    def __init__(self):
        self.captured: CompletionRequest | None = None

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.captured = request
        return CompletionResponse(
            content="ok",
            model="claude-opus-4-8",
            provider="ollama",
            tokens_used=1000,
            input_tokens=200,
            output_tokens=800,
        )


def _ai_host():
    class _Host(AIHandlersMixin):
        def __init__(self):
            self.dry_run = False
            self.memory_manager = None
            self.budget_manager = None

    return _Host()


def test_executor_tags_sensitivity_and_surfaces_breakdown(monkeypatch):
    import animus_kernel.executor.executor_ai as ai

    cap = _CaptureProvider()
    monkeypatch.setattr(ai, "_get_ollama_provider", lambda: cap)

    step = StepConfig(
        id="s1",
        type="ollama",
        params={"prompt": "do the thing", "sensitivity": "confidential"},
    )
    out = _ai_host()._execute_ollama(step, {})

    # C1-2: the request carried the declared sensitivity (was silently PUBLIC).
    assert cap.captured.sensitivity is Sensitivity.CONFIDENTIAL
    # C1-1: the output surfaces model + input/output split for cost-weighting.
    assert out["model"] == "claude-opus-4-8"
    assert out["input_tokens"] == 200
    assert out["output_tokens"] == 800


def test_executor_defaults_public_when_unspecified(monkeypatch):
    import animus_kernel.executor.executor_ai as ai

    cap = _CaptureProvider()
    monkeypatch.setattr(ai, "_get_ollama_provider", lambda: cap)
    step = StepConfig(id="s1", type="ollama", params={"prompt": "hi"})
    _ai_host()._execute_ollama(step, {})
    assert cap.captured.sensitivity is Sensitivity.PUBLIC


def test_breakdown_feeds_cost_weighted_effective_tokens():
    """C1-1 payoff: with the model + I/O split now threaded to record_usage, an
    opus output-heavy step costs far more Effective-Tokens than raw — so the ET
    ceiling trips even though raw usage is tiny. Before C1-1 this collapsed to
    raw (m=1.0) and never tripped."""
    bm = BudgetManager(BudgetConfig(total_budget=1_000_000, effective_token_budget=10_000))
    # exactly what executor_core now passes from StepResult
    bm.record_usage("s1", 1000, model="claude-opus-4-8", input_tokens=200, output_tokens=800)
    # ET = 5 * (1*200 + 4*800) = 5 * 3400 = 17000 >> raw 1000
    assert bm.effective_used == pytest.approx(17000.0)
    assert bm.status.value == "exceeded"  # ET ceiling tripped; raw alone would read OK


# ---------------------------------------------------------------------------
# C1-3 — TierRouter rebuild preserves sensitivity / tools / tool_choice
# ---------------------------------------------------------------------------


def test_router_rebuild_preserves_sensitivity_and_tools(monkeypatch):
    from animus_forge.providers.manager import ProviderManager
    from animus_forge.providers.router import RoutingConfig, TierRouter

    pm = MagicMock(spec=ProviderManager)
    pm.list_providers.return_value = ["ollama"]
    prov = MagicMock()
    prov.provider_type = ProviderType.OLLAMA
    pm.get.return_value = prov

    captured = {}

    def _complete(req, provider_name=None, use_fallback=False):
        captured["req"] = req
        return CompletionResponse(content="ok", model="qwen2.5:14b", provider="ollama")

    pm.complete.side_effect = _complete

    router = TierRouter(pm, RoutingConfig())
    # Force the tier→model resolution so the rebuild branch (router.py:130) runs.
    monkeypatch.setattr(router, "_resolve_tier_to_model", lambda req, name: "qwen2.5:14b")

    req = CompletionRequest(
        prompt="x",
        sensitivity=Sensitivity.CONFIDENTIAL,
        tools=[{"name": "deploy"}],
        tool_choice="auto",
        model_tier=ModelTier.STANDARD,
    )
    router.complete(req)

    got = captured["req"]
    assert got.model == "qwen2.5:14b"  # rebuild happened
    assert got.sensitivity is Sensitivity.CONFIDENTIAL  # C1-3: not downgraded to PUBLIC
    assert got.tools == [{"name": "deploy"}]  # C1-3: tools preserved
    assert got.tool_choice == "auto"


# ---------------------------------------------------------------------------
# C1-4 — LlamaCppProvider egress gate
# ---------------------------------------------------------------------------


class TestLlamaCppEgressGate:
    def _provider(self, base_url: str):
        from animus_forge.providers.llamacpp_provider import LlamaCppProvider

        p = LlamaCppProvider(ProviderConfig(provider_type=ProviderType.LLAMACPP, base_url=base_url))
        p._egress_endpoint = base_url
        return p

    def test_local_endpoint_passes(self):
        # Loopback is exempt — a local llama.cpp server works unconditionally.
        p = self._provider("http://127.0.0.1:11435/v1")
        p._check_request_egress(CompletionRequest(prompt="hi", sensitivity=Sensitivity.SECRET))

    def test_remote_endpoint_blocks_confidential(self):
        p = self._provider("https://llm.example.com/v1")
        with pytest.raises(EgressDeniedError):
            p._check_request_egress(
                CompletionRequest(prompt="hi", sensitivity=Sensitivity.CONFIDENTIAL)
            )

    def test_remote_endpoint_blocks_secret_payload(self):
        p = self._provider("https://llm.example.com/v1")
        with pytest.raises(EgressDeniedError, match="credential"):
            p._check_request_egress(
                CompletionRequest(prompt=f"deploy with {_KEY}", sensitivity=Sensitivity.PUBLIC)
            )

    def test_offline_init_blocks_remote(self, monkeypatch):
        monkeypatch.setenv("ANIMUS_OFFLINE", "1")
        from animus_forge.providers.llamacpp_provider import LlamaCppProvider

        p = LlamaCppProvider(
            ProviderConfig(
                provider_type=ProviderType.LLAMACPP, base_url="https://llm.example.com/v1"
            )
        )
        with pytest.raises(EgressDeniedError, match="ANIMUS_OFFLINE"):
            p.initialize()


# ---------------------------------------------------------------------------
# C1-14 — the loop: a CONFIDENTIAL executor-tagged request is blocked at a cloud
# gate; a PUBLIC one passes. This is the end-to-end seal the cluster lacked.
# ---------------------------------------------------------------------------


class TestEnforcementLoopClosed:
    CLOUD = "https://api.anthropic.com"

    def test_confidential_executor_request_blocked_at_cloud(self):
        # executor_ai now tags the request (C1-2); the cloud gate blocks it.
        req = CompletionRequest(
            prompt="the secret plan", sensitivity=_resolve_sensitivity("confidential")
        )
        with pytest.raises(EgressDeniedError):
            assert_egress_allowed(self.CLOUD, req)

    def test_public_executor_request_passes(self):
        req = CompletionRequest(prompt="hello", sensitivity=_resolve_sensitivity("public"))
        assert_egress_allowed(self.CLOUD, req)  # no raise

    def test_secret_bearing_public_request_still_blocked(self):
        # Content-aware DLP: even tagged PUBLIC, a credential in the body is denied.
        req = CompletionRequest(prompt=f"ship {_KEY}", sensitivity=Sensitivity.PUBLIC)
        with pytest.raises(EgressDeniedError, match="credential"):
            assert_egress_allowed(self.CLOUD, req)

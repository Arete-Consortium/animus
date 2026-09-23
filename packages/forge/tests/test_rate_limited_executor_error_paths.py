"""Coverage for rate_limited_executor.py error/edge branches on 2c8cde2.

Targets:
- 225-228: distributed limiter lazy init path
- 243: _check_distributed_limit early return when no limiter
- 313: _adjust_rate_limit early return when provider has no state
- 380: break-on-allowed inside distributed-limit retry loop
- 469-471: deadlock raise when pending tasks have no ready set
- 479-491: task exception handling inside as_completed loop
- 494: item is None fallthrough
- 499: task not in pending fallthrough
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "src")

from animus_forge.workflow.parallel import ParallelTask
from animus_forge.workflow.rate_limited_executor import (
    RateLimitedParallelExecutor,
)

# ---------------------------------------------------------------------------
# _get_distributed_limiter / _check_distributed_limit
# ---------------------------------------------------------------------------


class TestDistributedLimiter:
    def test_get_distributed_limiter_returns_none_when_disabled(self):
        ex = RateLimitedParallelExecutor(distributed=False)
        assert ex._get_distributed_limiter() is None

    def test_get_distributed_limiter_lazy_init(self):
        """Lines 224-228: first call builds + caches the limiter."""
        ex = RateLimitedParallelExecutor(distributed=True)
        with patch("animus_kernel.executor.distributed_rate_limiter.get_rate_limiter") as mock_get:
            fake_limiter = MagicMock()
            mock_get.return_value = fake_limiter

            out = ex._get_distributed_limiter()
            assert out is fake_limiter
            # Second call returns cached, no re-init.
            out2 = ex._get_distributed_limiter()
            assert out2 is fake_limiter
            assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_check_distributed_limit_returns_true_without_limiter(self):
        """Line 243: no limiter → allowed by default."""
        ex = RateLimitedParallelExecutor(distributed=False)
        assert await ex._check_distributed_limit("anthropic") is True

    @pytest.mark.asyncio
    async def test_check_distributed_limit_delegates_to_limiter(self):
        ex = RateLimitedParallelExecutor(distributed=True)
        fake_result = MagicMock()
        fake_result.allowed = False
        fake_result.current_count = 10
        fake_result.retry_after = 1.5
        fake_limiter = MagicMock()
        fake_limiter.acquire = AsyncMock(return_value=fake_result)
        ex._distributed_limiter = fake_limiter

        result = await ex._check_distributed_limit("anthropic")
        assert result is False
        fake_limiter.acquire.assert_awaited_once()


# ---------------------------------------------------------------------------
# _adjust_rate_limit
# ---------------------------------------------------------------------------


class TestAdjustRateLimitNoState:
    @pytest.mark.asyncio
    async def test_returns_early_when_provider_not_in_state(self):
        """Line 313: _adaptive_state lacks the provider → early return."""
        ex = RateLimitedParallelExecutor(adaptive=True)
        # Make sure the unknown provider isn't seeded.
        ex._adaptive_state.pop("mystery_provider", None)

        # Must not raise — just return without touching state.
        await ex._adjust_rate_limit("mystery_provider", is_success=True)


# ---------------------------------------------------------------------------
# _run_task_with_rate_limit — break-on-allowed (line 380)
# ---------------------------------------------------------------------------


class TestRunTaskDistributedBreakOnAllowed:
    @pytest.mark.asyncio
    async def test_first_allowed_check_breaks_retry_loop(self):
        """Line 380: `if allowed: break` exits the retry loop cleanly on the
        first successful check."""
        ex = RateLimitedParallelExecutor(distributed=True)
        ex._check_distributed_limit = AsyncMock(return_value=True)

        async def handler(**kwargs):
            return {"ok": True}

        task = ParallelTask(
            id="t1", step_id="s1", handler=handler, kwargs={"provider": "anthropic"}
        )
        semaphores = ex._get_semaphores()

        task_id, res, err = await ex._run_task_with_rate_limit(task, semaphores)
        assert task_id == "t1"
        assert err is None
        assert res == {"ok": True}
        # Distributed check was called exactly once (broke on first allowed).
        ex._check_distributed_limit.assert_awaited_once()


# ---------------------------------------------------------------------------
# execute_parallel_rate_limited — deadlock + as_completed error paths
# ---------------------------------------------------------------------------


class TestExecuteParallelDeadlockAndErrorPaths:
    @pytest.mark.asyncio
    async def test_deadlock_raises_value_error(self):
        """Lines 469-470: pending tasks with an unsatisfied dependency → deadlock."""
        ex = RateLimitedParallelExecutor(max_workers=2)

        async def handler(**kwargs):
            return {}

        # t2 depends on t1, but t1 isn't in the list — dependency never satisfies.
        t2 = ParallelTask(
            id="t2", step_id="s2", handler=handler, kwargs={}, dependencies=["t1-missing"]
        )

        with pytest.raises(ValueError, match="Deadlock"):
            await ex.execute_parallel_rate_limited(tasks=[t2])

    @pytest.mark.asyncio
    async def test_task_exception_records_failure(self):
        """Lines 479-491: a task exception in `await coro` populates
        result.failed and invokes on_error."""
        ex = RateLimitedParallelExecutor(max_workers=2, timeout=5.0)

        async def bad_handler(**kwargs):
            raise RuntimeError("handler boom")

        # Patch _run_task_with_rate_limit to raise directly, so the coro
        # in as_completed raises. This is the uncovered except path.
        async def raising_run(task, semaphores):
            raise RuntimeError(f"{task.id} exploded")

        ex._run_task_with_rate_limit = raising_run

        errors = []

        def on_error(task_id, exc):
            errors.append((task_id, str(exc)))

        t1 = ParallelTask(id="t1", step_id="s1", handler=bad_handler, kwargs={})
        t2 = ParallelTask(id="t2", step_id="s2", handler=bad_handler, kwargs={})

        result = await ex.execute_parallel_rate_limited(tasks=[t1, t2], on_error=on_error)

        assert set(result.failed) == {"t1", "t2"}
        assert len(errors) == 2
        # ptask.error is the caught Exception.
        for tid in ("t1", "t2"):
            assert isinstance(result.tasks[tid].error, Exception)

    # Note: the None-result and mismatched-task-id defensive branches
    # are exercised in test_rate_limited_executor_livelock_fix.py — they
    # were previously untestable because the branches themselves
    # livelocked the outer loop. The fix in this PR makes them safe.

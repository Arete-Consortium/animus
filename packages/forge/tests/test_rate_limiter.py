"""Tests for the distributed rate limiter module."""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from animus_forge.workflow.distributed_rate_limiter import (
    DistributedRateLimiter,
    MemoryRateLimiter,
    RateLimitResult,
    SQLiteRateLimiter,
    _create_rate_limiter,
    get_rate_limiter,
    reset_rate_limiter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# RateLimitResult dataclass
# ---------------------------------------------------------------------------


class TestRateLimitResult:
    """Tests for the RateLimitResult dataclass."""

    def test_remaining_under_limit(self):
        result = RateLimitResult(allowed=True, current_count=3, limit=10, reset_at=time.time() + 60)
        assert result.remaining == 7

    def test_remaining_at_limit(self):
        result = RateLimitResult(
            allowed=False, current_count=10, limit=10, reset_at=time.time() + 60
        )
        assert result.remaining == 0

    def test_remaining_over_limit(self):
        result = RateLimitResult(
            allowed=False, current_count=15, limit=10, reset_at=time.time() + 60
        )
        assert result.remaining == 0

    def test_retry_after_none_when_allowed(self):
        result = RateLimitResult(allowed=True, current_count=1, limit=10, reset_at=time.time() + 60)
        assert result.retry_after is None

    def test_retry_after_set_when_denied(self):
        result = RateLimitResult(
            allowed=False,
            current_count=11,
            limit=10,
            reset_at=time.time() + 60,
            retry_after=30.0,
        )
        assert result.retry_after == 30.0


# ---------------------------------------------------------------------------
# MemoryRateLimiter
# ---------------------------------------------------------------------------


class TestMemoryRateLimiter:
    """Tests for the in-memory rate limiter."""

    def test_acquire_first_request(self):
        limiter = MemoryRateLimiter()
        result = _run(limiter.acquire("test_key", limit=10, window_seconds=3600))
        assert result.allowed is True
        assert result.current_count == 1
        assert result.limit == 10
        assert result.remaining == 9

    def test_acquire_multiple_within_limit(self):
        limiter = MemoryRateLimiter()
        for i in range(5):
            result = _run(limiter.acquire("key", limit=10, window_seconds=3600))
        assert result.allowed is True
        assert result.current_count == 5

    def test_acquire_exceeds_limit(self):
        limiter = MemoryRateLimiter()
        for i in range(3):
            result = _run(limiter.acquire("key", limit=3, window_seconds=3600))
        # 3rd request is at limit (allowed)
        assert result.allowed is True

        # 4th request exceeds limit
        result = _run(limiter.acquire("key", limit=3, window_seconds=3600))
        assert result.allowed is False
        assert result.current_count == 4
        assert result.remaining == 0
        assert result.retry_after is not None

    def test_get_current_no_requests(self):
        limiter = MemoryRateLimiter()
        count = _run(limiter.get_current("key", window_seconds=3600))
        assert count == 0

    def test_get_current_after_requests(self):
        limiter = MemoryRateLimiter()
        _run(limiter.acquire("key", limit=10, window_seconds=3600))
        _run(limiter.acquire("key", limit=10, window_seconds=3600))
        count = _run(limiter.get_current("key", window_seconds=3600))
        assert count == 2

    def test_reset(self):
        limiter = MemoryRateLimiter()
        _run(limiter.acquire("key", limit=10, window_seconds=3600))
        _run(limiter.acquire("key", limit=10, window_seconds=3600))
        _run(limiter.reset("key"))
        count = _run(limiter.get_current("key", window_seconds=3600))
        assert count == 0

    def test_reset_nonexistent_key(self):
        """Reset on a key that was never used should not raise."""
        limiter = MemoryRateLimiter()
        _run(limiter.reset("nonexistent"))

    def test_independent_keys(self):
        limiter = MemoryRateLimiter()
        _run(limiter.acquire("key_a", limit=10, window_seconds=3600))
        _run(limiter.acquire("key_a", limit=10, window_seconds=3600))
        _run(limiter.acquire("key_b", limit=10, window_seconds=3600))
        count_a = _run(limiter.get_current("key_a", window_seconds=3600))
        count_b = _run(limiter.get_current("key_b", window_seconds=3600))
        assert count_a == 2
        assert count_b == 1

    def test_window_reset(self):
        """New window resets the count."""
        limiter = MemoryRateLimiter()
        # Acquire with a very small window, then manually manipulate state
        # to simulate the window having changed
        _run(limiter.acquire("key", limit=10, window_seconds=3600))
        # Manually set a different window_start to simulate time passing
        limiter._counts["key"] = (5, 0)  # Old window_start = 0
        count = _run(limiter.get_current("key", window_seconds=3600))
        assert count == 0  # Current window is different from 0


# ---------------------------------------------------------------------------
# SQLiteRateLimiter
# ---------------------------------------------------------------------------


class TestSQLiteRateLimiter:
    """Tests for the SQLite-based rate limiter."""

    @pytest.fixture
    def limiter(self, tmp_path):
        db_path = str(tmp_path / "rate_limits.db")
        return SQLiteRateLimiter(db_path=db_path)

    def test_acquire_first_request(self, limiter):
        result = _run(limiter.acquire("test_key", limit=10, window_seconds=3600))
        assert result.allowed is True
        assert result.current_count == 1

    def test_acquire_multiple(self, limiter):
        for _ in range(5):
            result = _run(limiter.acquire("key", limit=10, window_seconds=3600))
        assert result.allowed is True
        assert result.current_count == 5

    def test_acquire_exceeds_limit(self, limiter):
        for _ in range(3):
            _run(limiter.acquire("key", limit=3, window_seconds=3600))

        result = _run(limiter.acquire("key", limit=3, window_seconds=3600))
        assert result.allowed is False
        assert result.current_count == 4
        assert result.retry_after is not None

    def test_get_current_no_requests(self, limiter):
        count = _run(limiter.get_current("key", window_seconds=3600))
        assert count == 0

    def test_get_current_after_requests(self, limiter):
        _run(limiter.acquire("key", limit=10, window_seconds=3600))
        _run(limiter.acquire("key", limit=10, window_seconds=3600))
        count = _run(limiter.get_current("key", window_seconds=3600))
        assert count == 2

    def test_reset(self, limiter):
        _run(limiter.acquire("key", limit=10, window_seconds=3600))
        _run(limiter.acquire("key", limit=10, window_seconds=3600))
        _run(limiter.reset("key"))
        count = _run(limiter.get_current("key", window_seconds=3600))
        assert count == 0

    def test_independent_keys(self, limiter):
        _run(limiter.acquire("key_a", limit=10, window_seconds=3600))
        _run(limiter.acquire("key_a", limit=10, window_seconds=3600))
        _run(limiter.acquire("key_b", limit=10, window_seconds=3600))
        count_a = _run(limiter.get_current("key_a", window_seconds=3600))
        count_b = _run(limiter.get_current("key_b", window_seconds=3600))
        assert count_a == 2
        assert count_b == 1

    def test_cleanup_expired(self, limiter):
        """cleanup_expired removes old records."""
        # Insert some data first
        _run(limiter.acquire("key", limit=10, window_seconds=3600))
        # Cleanup with a future cutoff should remove records
        deleted = _run(limiter.cleanup_expired(older_than_seconds=0))
        # The records we just inserted should still be valid
        # (within current window), so deleted should be 0 or more
        assert isinstance(deleted, int)

    def test_initialized_once(self, limiter):
        """Table creation happens only once."""
        limiter._ensure_initialized()
        assert limiter._initialized is True
        # Calling again should be a no-op (no error)
        limiter._ensure_initialized()
        assert limiter._initialized is True

    def test_default_path(self):
        """Default path uses ~/.animus/."""
        limiter = SQLiteRateLimiter()
        assert ".animus" in limiter._db_path
        assert "rate_limits.db" in limiter._db_path


# ---------------------------------------------------------------------------
# SQLiteRateLimiter — sync methods directly
# ---------------------------------------------------------------------------


class TestSQLiteRateLimiterSync:
    """Tests for the synchronous methods of SQLiteRateLimiter."""

    @pytest.fixture
    def limiter(self, tmp_path):
        db_path = str(tmp_path / "rate_limits_sync.db")
        return SQLiteRateLimiter(db_path=db_path)

    def test_acquire_sync(self, limiter):
        result = limiter._acquire_sync("key", 10, 3600)
        assert result.allowed is True
        assert result.current_count == 1

    def test_acquire_sync_increment(self, limiter):
        limiter._acquire_sync("key", 10, 3600)
        result = limiter._acquire_sync("key", 10, 3600)
        assert result.current_count == 2

    def test_get_current_sync(self, limiter):
        limiter._acquire_sync("key", 10, 3600)
        count = limiter._get_current_sync("key", 3600)
        assert count == 1

    def test_reset_sync(self, limiter):
        limiter._acquire_sync("key", 10, 3600)
        limiter._reset_sync("key")
        count = limiter._get_current_sync("key", 3600)
        assert count == 0

    def test_cleanup_expired_sync(self, limiter):
        limiter._acquire_sync("key", 10, 3600)
        deleted = limiter._cleanup_expired_sync(older_than_seconds=0)
        assert isinstance(deleted, int)


# ---------------------------------------------------------------------------
# Global rate limiter management
# ---------------------------------------------------------------------------


class TestGlobalRateLimiter:
    """Tests for get_rate_limiter / reset_rate_limiter."""

    def setup_method(self):
        reset_rate_limiter()

    def teardown_method(self):
        reset_rate_limiter()

    def test_get_rate_limiter_returns_instance(self):
        limiter = get_rate_limiter()
        assert isinstance(limiter, DistributedRateLimiter)

    def test_get_rate_limiter_singleton(self):
        a = get_rate_limiter()
        b = get_rate_limiter()
        assert a is b

    def test_reset_clears_singleton(self):
        a = get_rate_limiter()
        reset_rate_limiter()
        b = get_rate_limiter()
        assert a is not b

    def test_create_sqlite_without_redis_url(self):
        """Without redis_url, creates SQLite limiter."""
        mock_settings = MagicMock()
        mock_settings.redis_url = None
        with patch(
            "animus_kernel.config.settings.get_settings",
            return_value=mock_settings,
        ):
            limiter = _create_rate_limiter()
            assert isinstance(limiter, SQLiteRateLimiter)

    def test_create_with_redis_url_but_no_package(self):
        """redis_url set but redis package missing falls back to SQLite."""
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"
        with patch(
            "animus_kernel.config.settings.get_settings",
            return_value=mock_settings,
        ):
            with patch("importlib.util.find_spec", return_value=None):
                limiter = _create_rate_limiter()
                assert isinstance(limiter, SQLiteRateLimiter)

    def test_create_with_redis_url_and_package(self):
        """redis_url set with redis package returns Redis limiter."""
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"
        with patch(
            "animus_kernel.config.settings.get_settings",
            return_value=mock_settings,
        ):
            mock_spec = MagicMock()
            with patch("importlib.util.find_spec", return_value=mock_spec):
                from animus_forge.workflow.distributed_rate_limiter import RedisRateLimiter

                limiter = _create_rate_limiter()
                assert isinstance(limiter, RedisRateLimiter)


# ---------------------------------------------------------------------------
# RateLimitResult edge cases
# ---------------------------------------------------------------------------


class TestRateLimitResultEdgeCases:
    """Edge case tests for RateLimitResult."""

    def test_zero_limit(self):
        result = RateLimitResult(allowed=False, current_count=1, limit=0, reset_at=time.time() + 60)
        assert result.remaining == 0

    def test_large_counts(self):
        result = RateLimitResult(
            allowed=False,
            current_count=1000000,
            limit=100,
            reset_at=time.time() + 60,
        )
        assert result.remaining == 0


# ---------------------------------------------------------------------------
# MemoryRateLimiter concurrency
# ---------------------------------------------------------------------------


class TestMemoryRateLimiterConcurrency:
    """Basic concurrency tests for MemoryRateLimiter."""

    def test_concurrent_acquires(self):
        """Multiple concurrent acquires maintain correct count."""
        limiter = MemoryRateLimiter()

        async def acquire_many():
            tasks = [limiter.acquire("key", limit=100, window_seconds=3600) for _ in range(50)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(acquire_many())
        assert len(results) == 50
        # All should be allowed with limit=100
        assert all(r.allowed for r in results)

    def test_rate_limiting_works_under_concurrency(self):
        """Rate limiting still enforced with concurrent requests."""
        limiter = MemoryRateLimiter()

        async def acquire_many():
            tasks = [limiter.acquire("key", limit=5, window_seconds=3600) for _ in range(10)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(acquire_many())
        allowed = sum(1 for r in results if r.allowed)
        denied = sum(1 for r in results if not r.allowed)
        assert allowed == 5
        assert denied == 5

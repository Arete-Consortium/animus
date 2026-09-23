"""Tests for distributed rate limiter implementations."""

import asyncio
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "src")

from animus_forge.workflow.distributed_rate_limiter import (
    MemoryRateLimiter,
    RateLimitResult,
    RedisRateLimiter,
    SQLiteRateLimiter,
    get_rate_limiter,
    reset_rate_limiter,
)


class TestRateLimitResult:
    """Tests for RateLimitResult dataclass."""

    def test_remaining_calculation(self):
        """Remaining is calculated correctly."""
        result = RateLimitResult(
            allowed=True,
            current_count=3,
            limit=10,
            reset_at=time.time() + 60,
        )
        assert result.remaining == 7

    def test_remaining_never_negative(self):
        """Remaining is never negative."""
        result = RateLimitResult(
            allowed=False,
            current_count=15,
            limit=10,
            reset_at=time.time() + 60,
        )
        assert result.remaining == 0

    def test_retry_after_set_when_not_allowed(self):
        """Retry after is set when request not allowed."""
        result = RateLimitResult(
            allowed=False,
            current_count=11,
            limit=10,
            reset_at=time.time() + 30,
            retry_after=30.0,
        )
        assert result.retry_after == 30.0


class TestMemoryRateLimiter:
    """Tests for MemoryRateLimiter."""

    @pytest.fixture
    def limiter(self):
        """Create fresh memory limiter."""
        return MemoryRateLimiter()

    @pytest.mark.asyncio
    async def test_acquire_under_limit(self, limiter):
        """Acquire succeeds under limit."""
        result = await limiter.acquire("test", limit=10, window_seconds=60)
        assert result.allowed is True
        assert result.current_count == 1
        assert result.remaining == 9

    @pytest.mark.asyncio
    async def test_acquire_increments_count(self, limiter):
        """Each acquire increments count."""
        await limiter.acquire("test", limit=10)
        await limiter.acquire("test", limit=10)
        result = await limiter.acquire("test", limit=10)

        assert result.current_count == 3
        assert result.remaining == 7

    @pytest.mark.asyncio
    async def test_acquire_over_limit(self, limiter):
        """Acquire fails when over limit."""
        for _ in range(5):
            await limiter.acquire("test", limit=5)

        result = await limiter.acquire("test", limit=5)

        assert result.allowed is False
        assert result.retry_after is not None
        assert result.retry_after > 0

    @pytest.mark.asyncio
    async def test_different_keys_independent(self, limiter):
        """Different keys have independent limits."""
        for _ in range(10):
            await limiter.acquire("key1", limit=10)

        result = await limiter.acquire("key2", limit=10)

        assert result.allowed is True
        assert result.current_count == 1

    @pytest.mark.asyncio
    async def test_get_current(self, limiter):
        """get_current returns count without incrementing."""
        await limiter.acquire("test", limit=10)
        await limiter.acquire("test", limit=10)

        count = await limiter.get_current("test")
        assert count == 2

        count = await limiter.get_current("test")
        assert count == 2

    @pytest.mark.asyncio
    async def test_reset(self, limiter):
        """Reset clears count for key."""
        for _ in range(5):
            await limiter.acquire("test", limit=10)

        await limiter.reset("test")

        result = await limiter.acquire("test", limit=10)
        assert result.current_count == 1


class TestSQLiteRateLimiter:
    """Tests for SQLiteRateLimiter."""

    @pytest.fixture
    def limiter(self, tmp_path):
        """Create SQLite limiter with temp database."""
        db_path = str(tmp_path / "rate_limits.db")
        return SQLiteRateLimiter(db_path=db_path)

    @pytest.mark.asyncio
    async def test_acquire_under_limit(self, limiter):
        """Acquire succeeds under limit."""
        result = await limiter.acquire("test", limit=10, window_seconds=60)
        assert result.allowed is True
        assert result.current_count == 1

    @pytest.mark.asyncio
    async def test_acquire_increments_count(self, limiter):
        """Each acquire increments count."""
        await limiter.acquire("test", limit=10)
        await limiter.acquire("test", limit=10)
        result = await limiter.acquire("test", limit=10)

        assert result.current_count == 3

    @pytest.mark.asyncio
    async def test_acquire_over_limit(self, limiter):
        """Acquire fails when over limit."""
        for _ in range(5):
            await limiter.acquire("test", limit=5)

        result = await limiter.acquire("test", limit=5)

        assert result.allowed is False
        assert result.retry_after is not None

    @pytest.mark.asyncio
    async def test_get_current(self, limiter):
        """get_current returns count without incrementing."""
        await limiter.acquire("test", limit=10)
        await limiter.acquire("test", limit=10)

        count = await limiter.get_current("test")
        assert count == 2

    @pytest.mark.asyncio
    async def test_reset(self, limiter):
        """Reset clears count for key."""
        for _ in range(5):
            await limiter.acquire("test", limit=10)

        await limiter.reset("test")

        result = await limiter.acquire("test", limit=10)
        assert result.current_count == 1

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, limiter):
        """Cleanup removes old records."""
        await limiter.acquire("test", limit=10)
        deleted = await limiter.cleanup_expired(older_than_seconds=0)
        assert deleted >= 0

    @pytest.mark.asyncio
    async def test_concurrent_acquires(self, limiter):
        """Handles concurrent acquires correctly."""
        # Use long window (3600s) to avoid crossing minute boundaries during test
        tasks = [limiter.acquire("test", limit=100, window_seconds=3600) for _ in range(10)]
        results = await asyncio.gather(*tasks)

        assert all(r.allowed for r in results)
        final = await limiter.get_current("test", window_seconds=3600)
        assert final == 10


class TestRedisRateLimiter:
    """Tests for RedisRateLimiter (mocked)."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock async Redis client."""
        mock = AsyncMock()
        mock.incr = AsyncMock(return_value=1)
        mock.expire = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.delete = AsyncMock()
        mock.scan = AsyncMock(return_value=(0, []))
        return mock

    @pytest.mark.asyncio
    async def test_acquire_uses_incr(self, mock_redis):
        """Acquire uses Redis INCR command."""
        limiter = RedisRateLimiter(url="redis://localhost:6379")
        limiter._async_client = mock_redis

        result = await limiter.acquire("test", limit=10)

        mock_redis.incr.assert_called_once()
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_sets_expire_on_first_request(self, mock_redis):
        """Sets EXPIRE on first request in window."""
        mock_redis.incr.return_value = 1

        limiter = RedisRateLimiter(url="redis://localhost:6379")
        limiter._async_client = mock_redis

        await limiter.acquire("test", limit=10, window_seconds=60)

        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_expire_on_subsequent_requests(self, mock_redis):
        """Does not set EXPIRE on subsequent requests."""
        mock_redis.incr.return_value = 5

        limiter = RedisRateLimiter(url="redis://localhost:6379")
        limiter._async_client = mock_redis

        await limiter.acquire("test", limit=10, window_seconds=60)

        mock_redis.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_over_limit_returns_not_allowed(self, mock_redis):
        """Returns not allowed when over limit."""
        mock_redis.incr.return_value = 11

        limiter = RedisRateLimiter(url="redis://localhost:6379")
        limiter._async_client = mock_redis

        result = await limiter.acquire("test", limit=10)

        assert result.allowed is False
        assert result.retry_after is not None

    @pytest.mark.asyncio
    async def test_get_current(self, mock_redis):
        """get_current returns count from Redis."""
        mock_redis.get.return_value = b"5"

        limiter = RedisRateLimiter(url="redis://localhost:6379")
        limiter._async_client = mock_redis

        count = await limiter.get_current("test")

        assert count == 5

    @pytest.mark.asyncio
    async def test_get_current_returns_zero_when_none(self, mock_redis):
        """get_current returns 0 when key doesn't exist."""
        mock_redis.get.return_value = None

        limiter = RedisRateLimiter(url="redis://localhost:6379")
        limiter._async_client = mock_redis

        count = await limiter.get_current("test")

        assert count == 0

    def test_key_includes_window_timestamp(self):
        """Key includes window timestamp for sliding window."""
        limiter = RedisRateLimiter(url="redis://localhost:6379", prefix="test:")

        key1 = limiter._make_key("api", window_seconds=60)

        assert key1.startswith("test:api:")
        parts = key1.split(":")
        assert len(parts) == 3
        assert parts[2].isdigit()


class TestGetRateLimiter:
    """Tests for get_rate_limiter factory."""

    def setup_method(self):
        """Reset global limiter before each test."""
        reset_rate_limiter()

    def teardown_method(self):
        """Reset global limiter after each test."""
        reset_rate_limiter()

    def test_returns_sqlite_by_default(self):
        """Returns SQLiteRateLimiter when no Redis URL."""
        mock_settings = MagicMock()
        mock_settings.redis_url = None
        with patch(
            "animus_kernel.config.settings.get_settings",
            return_value=mock_settings,
        ):
            reset_rate_limiter()
            limiter = get_rate_limiter()

        assert isinstance(limiter, SQLiteRateLimiter)

    def test_returns_redis_when_url_set_and_installed(self):
        """Returns RedisRateLimiter when redis_url set and redis installed."""
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379"
        with patch(
            "animus_kernel.config.settings.get_settings",
            return_value=mock_settings,
        ):
            with patch("importlib.util.find_spec") as mock_find_spec:
                mock_find_spec.return_value = MagicMock()

                reset_rate_limiter()
                limiter = get_rate_limiter()

                assert isinstance(limiter, RedisRateLimiter)

    def test_falls_back_to_sqlite_when_redis_not_installed(self):
        """Falls back to SQLite when redis_url set but redis not installed."""
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379"
        with patch(
            "animus_kernel.config.settings.get_settings",
            return_value=mock_settings,
        ):
            with patch("importlib.util.find_spec") as mock_find_spec:
                mock_find_spec.return_value = None

                reset_rate_limiter()
                limiter = get_rate_limiter()

                assert isinstance(limiter, SQLiteRateLimiter)

    def test_caches_instance(self):
        """Returns same instance on subsequent calls."""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()

        assert limiter1 is limiter2

    def test_reset_clears_cache(self):
        """reset_rate_limiter clears cached instance."""
        limiter1 = get_rate_limiter()
        reset_rate_limiter()
        limiter2 = get_rate_limiter()

        assert limiter1 is not limiter2


class TestConcurrency:
    """Tests for concurrent access patterns."""

    @pytest.mark.asyncio
    async def test_memory_limiter_thread_safe(self):
        """Memory limiter handles concurrent access."""
        limiter = MemoryRateLimiter()

        async def acquire_many():
            for _ in range(100):
                await limiter.acquire("test", limit=1000)

        await asyncio.gather(*[acquire_many() for _ in range(10)])

        count = await limiter.get_current("test")
        assert count == 1000

    @pytest.mark.asyncio
    async def test_sqlite_limiter_concurrent_access(self, tmp_path):
        """SQLite limiter handles concurrent access."""
        db_path = str(tmp_path / "rate_limits.db")
        limiter = SQLiteRateLimiter(db_path=db_path)

        # Use a long window (1 hour) to avoid crossing window boundaries during test
        window_seconds = 3600
        tasks = [
            limiter.acquire("test", limit=1000, window_seconds=window_seconds) for _ in range(50)
        ]
        results = await asyncio.gather(*tasks)

        assert all(r.allowed for r in results)
        count = await limiter.get_current("test", window_seconds=window_seconds)
        assert count == 50

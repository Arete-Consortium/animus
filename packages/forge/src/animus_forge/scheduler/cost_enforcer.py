"""CostEnforcer — enforce budget ceilings and emit spend telemetry.

Tracks cumulative spend per mission (and globally) and blocks new tasks when
budgets are exhausted.  Spend data is fed by the scheduler after each task
completes; in a production system this would integrate with an LLM API cost
stream.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from animus_forge.state.backends import DatabaseBackend

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cost_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL,
    task_id TEXT,
    operation TEXT NOT NULL,  -- e.g. 'llm_call', 'sandbox', 'file_sync'
    provider TEXT,             -- e.g. 'openai', 'anthropic', 'local'
    model TEXT,
    usage_tokens_input INTEGER DEFAULT 0,
    usage_tokens_output INTEGER DEFAULT 0,
    cost_usd TEXT NOT NULL DEFAULT '0.00',
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cost_mission ON cost_events(mission_id);
CREATE INDEX IF NOT EXISTS idx_cost_recorded ON cost_events(recorded_at);
CREATE TABLE IF NOT EXISTS cost_budget_lock (
    lock_id INTEGER PRIMARY KEY,
    revision INTEGER NOT NULL DEFAULT 0
);
INSERT INTO cost_budget_lock (lock_id, revision) VALUES (1, 0)
    ON CONFLICT (lock_id) DO NOTHING;
CREATE TABLE IF NOT EXISTS cost_reservations (
    attempt_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    amount_usd TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'reserved'
        CHECK (status IN ('reserved', 'settled', 'released'))
);
CREATE INDEX IF NOT EXISTS idx_reservations_mission ON cost_reservations(mission_id, status);

"""

# Rough token pricing (per 1M tokens) — can be overridden via config
_DEFAULT_RATES: dict[str, dict[str, Decimal]] = {
    "openai": {
        "gpt-4o": Decimal("5.00"),
        "gpt-4o-mini": Decimal("0.15"),
    },
    "anthropic": {
        "claude-3-5-sonnet": Decimal("3.00"),
        "claude-3-haiku": Decimal("0.25"),
    },
    "local": {
        "default": Decimal("0.00"),
    },
}


class CostEnforcer:
    """Enforces mission-level and global spend limits.

    Args:
        backend: Shared ``DatabaseBackend``.
        default_mission_cap_usd: Default maximum USD per mission.
        global_cap_usd: Maximum USD across *all* missions in a window.
    """

    def __init__(
        self,
        backend: DatabaseBackend,
        *,
        default_mission_cap_usd: Decimal = Decimal("10.00"),
        global_cap_usd: Decimal = Decimal("100.00"),
    ):
        self._backend = backend
        self.default_mission_cap = default_mission_cap_usd
        self.global_cap = global_cap_usd
        self._rates = {provider: rates.copy() for provider, rates in _DEFAULT_RATES.items()}
        self._init_schema()

    def _init_schema(self) -> None:
        with self._backend.transaction():
            self._backend.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        mission_id: str,
        operation: str,
        *,
        task_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        tokens_input: int = 0,
        tokens_output: int = 0,
        cost_usd: Decimal | None = None,
    ) -> None:
        """Record a cost event.

        If ``cost_usd`` is supplied, use it directly; otherwise estimate
        from token counts and the rate card.
        """
        if cost_usd is None:
            cost_usd = self.estimate_cost(
                provider or "local",
                model or "default",
                tokens_input,
                tokens_output,
            )

        self._validate_amount(cost_usd)
        if tokens_input < 0 or tokens_output < 0:
            raise ValueError("Token counts must be nonnegative")
        with self._backend.transaction():
            self.lock_budget()
            self._backend.execute(
                """
                INSERT INTO cost_events
                    (mission_id, task_id, operation, provider, model,
                     usage_tokens_input, usage_tokens_output, cost_usd, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    task_id,
                    operation,
                    provider,
                    model,
                    tokens_input,
                    tokens_output,
                    str(cost_usd),
                    datetime.now().isoformat(),
                ),
            )

    def estimate_cost(
        self,
        provider: str,
        model: str,
        tokens_input: int,
        tokens_output: int,
    ) -> Decimal:
        """Estimate cost from rate card.

        Rates are stored as cost per *million* tokens.
        """
        rate = self._rates.get(provider, {}).get(model, Decimal("0.00"))
        total_tokens = tokens_input + tokens_output
        return rate * Decimal(total_tokens) / Decimal("1_000_000")

    def set_rate(self, provider: str, model: str, per_1m_tokens_usd: Decimal) -> None:
        """Override or add a rate card entry."""
        if provider not in self._rates:
            self._rates[provider] = {}
        self._rates[provider][model] = per_1m_tokens_usd
        logger.info("Rate set: %s/%s = %s per 1M tokens", provider, model, per_1m_tokens_usd)

    @staticmethod
    def _validate_amount(amount: Decimal) -> None:
        if not amount.is_finite() or amount < 0:
            raise ValueError("Cost must be finite and nonnegative")

    def lock_budget(self) -> None:
        """Serialize budget mutations inside the caller's transaction.

        This must be the first statement before any reads in dispatch/result
        transactions. A database row lock also coordinates separate processes.
        """
        self._backend.execute(
            "UPDATE cost_budget_lock SET revision = revision + 1 WHERE lock_id = 1"
        )

    def mission_spend(self, mission_id: str) -> Decimal:
        """Return exact decimal spend, without SQL floating-point aggregation."""
        rows = self._backend.fetchall(
            "SELECT cost_usd FROM cost_events WHERE mission_id = ?", (mission_id,)
        )
        return sum((Decimal(r["cost_usd"]) for r in rows), Decimal("0"))

    def global_spend(self, since: datetime | None = None) -> Decimal:
        query = "SELECT cost_usd FROM cost_events"
        params: tuple[str, ...] = ()
        if since:
            query += " WHERE recorded_at >= ?"
            params = (since.isoformat(),)
        rows = self._backend.fetchall(query, params)
        return sum((Decimal(r["cost_usd"]) for r in rows), Decimal("0"))

    def reserved(self, mission_id: str | None = None) -> Decimal:
        query = "SELECT amount_usd FROM cost_reservations WHERE status = 'reserved'"
        params: tuple[str, ...] = ()
        if mission_id is not None:
            query += " AND mission_id = ?"
            params = (mission_id,)
        return sum(
            (Decimal(r["amount_usd"]) for r in self._backend.fetchall(query, params)),
            Decimal("0"),
        )

    def mission_remaining(self, mission_id: str, cap: Decimal | None = None) -> Decimal:
        cap = self.default_mission_cap if cap is None else cap
        return max(Decimal("0"), cap - self.mission_spend(mission_id) - self.reserved(mission_id))

    def can_start_task(
        self,
        mission_id: str,
        estimated_cost: Decimal = Decimal("0.10"),
        *,
        mission_cap: Decimal | None = None,
    ) -> tuple[bool, str]:
        """Read-only check; use reserve() to atomically claim available budget."""
        self._validate_amount(estimated_cost)
        mission_cap = self.default_mission_cap if mission_cap is None else mission_cap
        if (
            self.mission_spend(mission_id) + self.reserved(mission_id) + estimated_cost
            > mission_cap
        ):
            return False, f"Mission {mission_id} budget exhausted ({mission_cap} USD)"
        if self.global_spend() + self.reserved() + estimated_cost > self.global_cap:
            return False, f"Global budget cap reached ({self.global_cap} USD)"
        return True, "ok"

    def reserve(
        self,
        attempt_id: str,
        mission_id: str,
        estimated_cost: Decimal,
        *,
        mission_cap: Decimal | None = None,
    ) -> tuple[bool, str]:
        """Reserve once per execution attempt, atomically across schedulers."""
        self._validate_amount(estimated_cost)
        with self._backend.transaction():
            self.lock_budget()
            if self._backend.fetchone(
                "SELECT attempt_id FROM cost_reservations WHERE attempt_id = ?", (attempt_id,)
            ):
                return False, "attempt_already_reserved"
            ok, reason = self.can_start_task(mission_id, estimated_cost, mission_cap=mission_cap)
            if not ok:
                return ok, reason
            self._backend.execute(
                "INSERT INTO cost_reservations (attempt_id, mission_id, amount_usd) VALUES (?, ?, ?)",
                (attempt_id, mission_id, str(estimated_cost)),
            )
        return True, "ok"

    def finish_reservation(self, attempt_id: str, *, settled: bool) -> None:
        """Release only after settlement or a confirmed dispatch that never ran.

        Expired/killed attempts with unknown usage retain their reservation for
        reconciliation; a missing result must not silently free their budget.
        """
        with self._backend.transaction():
            self.lock_budget()
            self._backend.execute(
                "UPDATE cost_reservations SET status = ? WHERE attempt_id = ? AND status = 'reserved'",
                ("settled" if settled else "released", attempt_id),
            )

    def spend_report(self, mission_id: str | None = None) -> dict[str, Any]:
        """Return a human-readable spend report."""
        if mission_id:
            rows = self._backend.fetchall(
                """
                SELECT operation, SUM(cost_usd) AS total,
                       SUM(usage_tokens_input) AS tokens_in,
                       SUM(usage_tokens_output) AS tokens_out
                FROM cost_events WHERE mission_id = ?
                GROUP BY operation
                """,
                (mission_id,),
            )
            return {
                "mission_id": mission_id,
                "total_spend_usd": str(self.mission_spend(mission_id)),
                "by_operation": [
                    {
                        "operation": r["operation"],
                        "spend_usd": str(Decimal(str(r["total"]))),
                        "tokens_in": r["tokens_in"],
                        "tokens_out": r["tokens_out"],
                    }
                    for r in rows
                ],
            }

        # Global report
        rows = self._backend.fetchall(
            """
            SELECT mission_id, SUM(cost_usd) AS total FROM cost_events
            GROUP BY mission_id
            ORDER BY total DESC
            """
        )
        return {
            "global_spend_usd": str(self.global_spend()),
            "global_cap_usd": str(self.global_cap),
            "by_mission": [
                {"mission_id": r["mission_id"], "spend_usd": str(Decimal(str(r["total"])))}
                for r in rows
            ],
        }

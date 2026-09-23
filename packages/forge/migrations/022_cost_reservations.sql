-- Durable dispatch reservations; initialize alongside CostEnforcer.
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

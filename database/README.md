# database/

Durable core — PostgreSQL schema, Alembic migrations, and bitemporal projection utilities.

## Quick Start

1. Ensure PostgreSQL is running (see infra/docker-compose.yml).
2. Copy infra/.env.example to infra/.env and fill in your credentials.
3. Export connection string:
   ```bash
   export ANIMUS_DATABASE_URL=<your-db-url>
   ```
   Replace `<your-db-url>` with your actual connection string.
4. Run migrations:
   ```bash
   cd database && alembic upgrade head
   ```

## Schema Overview

| Table | Purpose |
|---|---|
| object_registry | Canonical objects with bitemporal validity |
| event_ledger | Append-only log of significant system events |
| traceability | Links requirements → tests → evidence bundles |

## Bitemporal Fields

- **valid_from / valid_to**: When the row was true in the real world (world time).
- **recorded_at / superseded_at**: When the row was written to the system (transaction time).

## Migrations

Managed by Alembic. Add new revisions with:
```bash
alembic revision -m "description"
```

**Note**: `alembic.ini` contains a default placeholder URL.
Do **not** commit real credentials. Set the connection string via environment variable:
```bash
export DATABASE_URL="postgresql://..."
```
Or override `sqlalchemy.url` in a local `alembic-local.ini` that is `.gitignore`d.

## Tests

```bash
pytest database/tests/
```

## What Goes Here

- **Alembic migrations** (`migrations/versions/`) — PostgreSQL schema evolution
- **Schema DDL** (`schema/`) — CREATE TABLE scripts for object registry, event ledger, bitemporal projections
- **Seed data** (`seeds/`) — reference data, demo fixtures
- **Connection utilities** (`pool.py`, `session.py`) — SQLAlchemy or asyncpg helpers

## Technology

- **Primary**: PostgreSQL 15+ (durable authority)
- **Projections**: SQLite (lightweight, offline-capable views)
- **Migration tool**: Alembic

## Boundary vs packages/

`packages/kernel/` and `packages/core/` contain the **ORM models and query logic**.
`database/` contains the **migration definitions and raw DDL** — this is the schema-of-record for operators and DBAs.

## Owner

AreteDriver

## Registry backup and restore

Use PostgreSQL client tools (`pg_dump`, `pg_restore`, and `psql`) compatible with
the server version. The registry backup includes the entire dedicated Animus
database, including edge versions, evidence, ledger, outbox, and migration state.
Keep backups private and restore only archives from trusted sources.

```bash
# ANIMUS_DATABASE_URL identifies the dedicated source database.
python -m animus.durability.cli export-registry -o registry.dump

# ANIMUS_RESTORE_DATABASE_URL identifies a newly created empty database.
python -m animus.durability.cli restore-registry registry.dump
```

Keep the restore target offline from application writers and outbox workers
until verification is complete. The restore runs in one transaction and uses
the target role's ownership and privileges. Reapply any deployment-specific
grants before switching application traffic. The file-based `export --all`
command continues to archive the local data directory.

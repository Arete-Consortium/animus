# Legacy Chroma: inventory and retirement plan

Status: prepared for Stheno, the Linux desktop that runs the live Discord bot. No live
memory export, backend change, dependency removal, or data deletion has occurred.

## Evidence and remaining uncertainty

- The operator confirmed that the Discord bot runs on the Linux desktop Stheno
  and that Chroma was built into Animus as storage. A read-only SSH attempt from
  the Mac to Stheno timed out on port 22. This session has not inspected that
  host's running service, effective configuration, or data.
- The checked-in `tools/animus-discord.service` runs the Core bot as `arete` from
  `/home/arete/projects/animus`. This is a deployment template, not proof of the
  installed service. Its environment file must not be printed into logs/chat.
- `tools/animus_discord_bot.py` lazily constructs `MemoryLayer` using the configured
  backend and data directory. Core still defaults to `chroma`; its default data
  directory is `~/.animus`. The live environment may override that selection.
- Core's Chroma adapter tries HTTP at `localhost:8787`, then embedded storage at
  `<data_dir>/chroma`. Kernel's adapter uses embedded storage. A server can use a
  different persistence directory; backing up only the client's directory is
  insufficient. Both adapters can create directories/collections on construction.
- On the Mac, Docker metadata showed no Chroma container, and neither default
  Animus directory contained a `chroma` directory. This says nothing about the
  Linux desktop, custom paths, or another server.
- The legacy Core `[chroma]` audit resolves Chroma 1.5.9 and fails. The checked
  [code-injection advisory](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c)
  lists affected versions through 1.5.9 and no patched version. Recheck the
  advisory and [upstream releases](https://github.com/chroma-core/chroma/releases)
  before choosing an upgrade. Loopback access is not a vulnerability fix.

## First step on the Linux desktop: read-only inventory

Identify the actual bot unit, executable, checkout commit, interpreter, service
user, and working directory. For the checked-in system service name:

```sh
systemctl show animus-discord.service \
  --property=LoadState,ActiveState,MainPID,User,WorkingDirectory,FragmentPath
systemctl --user show chromadb.service \
  --property=LoadState,ActiveState,MainPID,WorkingDirectory,FragmentPath
ss -ltn '( sport = :8787 )'
```

A missing user unit does not rule out a system unit, container, or embedded
client. Run user-unit inspection as the service owner. Record only the effective
memory backend, data directory, collection name, Chroma client/server versions,
server persistence path, and whether the server is network-accessible. Inspect
environment/config locally with an allowlist; do not dump whole environment files,
process environments, or configuration containing credentials.

Do not instantiate `AnimusConfig`, `MemoryLayer`, or either Chroma store just to
inventory: configuration loading/store constructors may create state, and the
Core client can silently select a different mode if the server is unavailable.
Confirm the actual collection from the running deployment rather than assuming
the config field is honored; the Core bot does not pass a collection name to
`MemoryLayer`. Obtain authoritative counts and collection metadata without
printing document contents. Inspect all consumers before calling a store unused.

## Choose the path from that inventory

| Finding | Appropriate next change |
| --- | --- |
| Chroma is unused by every supported deployment | Preserve any historical store; remove runtime adapters, extras (including `[all]`), defaults and documentation that still advertise Chroma. Add explicit diagnostics for old configs and verify fresh installs. Retire the audit profile only with actual support removal. |
| Chroma contains active memories and semantic search is unnecessary | Rehearse migration to a separate JSON store; accept the substring-search behavior explicitly, verify data parity, then schedule a controlled cutover. |
| Active memories need semantic search | Keep production unchanged while selecting and testing a replacement retrieval implementation. A JSON or current durable-store switch does not preserve semantic retrieval. |
| Upstream publishes a patched compatible release | Test the patched client/server pair on a backup, verify API/data compatibility and all dependency audits, then prepare a separate deployment change. |

The present recommendation is **inventory, then a migration rehearsal**. There
is not enough evidence to choose unconditional removal or a replacement backend.
Hunter's SQL source-review service does not require personal Chroma memory.

## Migration rehearsal and acceptance

1. Locate every writer and the authoritative store. Prepare a consistent,
   restorable snapshot using the store's supported backup procedure. Record
   versions, paths, collection counts, checksums, and access permissions in a
   private manifest. Preserve the source and original service configuration.
2. Restore a copy into an isolated environment with no Discord publishing or
   provider credentials. Test that the backup actually opens. Keep memory data
   and exports out of Git, build artifacts, and chat output.
3. Export from that copy using a strict adapter: abort on any malformed record,
   count discrepancy, duplicate ID, or skipped metadata. Existing Chroma
   `_load_metadata()` catches errors and can leave a partial cache, so a successful
   `MemoryLayer.export_memories()` return alone does not prove completeness.
   Compare exported IDs/counts with the authoritative collection directly.
4. Import into a new, empty destination. Preserve IDs, content, arbitrary metadata,
   tags, memory type, provenance, source/confidence, sensitivity/tier, timestamps,
   access metadata, version and parent links. Compare canonical per-record hashes
   and all counts. Core's JSON export is an array; `LocalMemoryStore`'s on-disk
   file is an ID-keyed object. Do not copy the export directly to `memories.json`.
5. Verify representative recall queries, sensitivity filtering, version traversal,
   cold-start/restart behavior, and writes after reopening. JSON search is
   substring matching. The current durable adapter also lacks vector search and
   maps original timestamps to record timestamps while dropping `last_accessed`;
   it needs fidelity fixes before claiming lossless migration.
6. Test rollback in the rehearsal. For production cutover, stop writers, perform
   a final consistent export/delta, revalidate, then switch one service. Keep
   writes disabled during initial acceptance; if writes resume, reconcile them
   before rollback so restoring the old source does not lose new memories.
7. Remove Chroma from the supported runtime only after acceptance. Rebuild fresh
   environments and run dependency audits for every supported profile, plus the
   memory, bot, and Hunter regressions. Keep the preserved source/backup until a
   separate retention decision; no automatic deletion is part of retirement.

## Merge and deployment gates

Coverage repair is independent of memory retirement. Keep the legacy audit
blocking while vulnerable Chroma remains a supported dependency; do not add an
ignore or merely delete the failing job. A passing Core base audit does not clear
the Chroma profile. Production cutover requires the completed inventory,
successful rehearsal evidence, a chosen retrieval contract, and authorization
for the concrete service/data change.

# Hunter delivery reconciliation — 2026-09-24

The reviewed SQL stack and the independently advanced delivery checkout have
diverged. Continue from this inventory before implementing another presenter or
bot. The delivery checkout is preserved; do not reset it or copy its whole tree
over the SQL importer branch.

## Verified source-control state

- PR #136 (`64279c631b566e3fc7b700250e6d3fc1e39fd983`) contains the candidate-only,
  atomic SQL importer. Hosted CI run 35990857598 passed. Security run 35990857610
  failed only the optional Core Chroma dependency audit; the six base audits passed.
- The local `codex/hunter-os-delivery` checkout remains based on #135 (`00a78e7`)
  with extensive uncommitted changes. It already contains a presenter, curation,
  isolated chat, destination-bound publisher, Armor types, reviewed starter content,
  player builds, screenshots, conversation and journey fixes.
- This reconciliation slice promotes only the personal bot privacy guard into the
  SQL stack, adds dispatcher regressions and makes command synchronization opt-in.
  It does not replace the independently running Hunter application.

## Deployment evidence and its limits

The saved journey report describes `animus-hunter:journeys-20260924`, 91 automated
tests, nine installed-container adapter checks, and unobserved two-player human
acceptance. Its image is historical: a read-only Stheno inspection on this work
date returned `animus-hunter:retention-20260924-01a0d23c`, running, two restarts,
and a read-only root filesystem. Container state alone does not verify the current
image's source, features, restart cause or acceptance results. No logs, secrets,
player records or database contents were inspected for that check.

Local evidence is in the Discord workspace's
`artifacts/hunter-journeys-2026-09-24/README.md`, `regression-results.txt`,
`deployment-status.txt`, and `implementation.patch`. These are local operational
artifacts, not files promised to exist in a clean clone of this repository.

## Next reconciliation work

1. Capture and review the current retention release's source/deployment manifest,
   then map it to the preserved delivery checkout. Do not redeploy the older journey
   image merely because its report is easier to locate.
2. Reconcile the two importer implementations explicitly. The reviewed importer
   stages candidates and rejects replacement of protected rows. The delivery
   importer additionally exposes approval/curation APIs consumed by its publisher
   and starter tools. They are not interchangeable implementations of one API.
3. Promote Armor contracts, curation and presentation with their existing tests in
   coherent reviewable slices. Preserve the delivery layout's fourth Armor forum;
   the earlier three-forum, 58-post target is historical.
4. Promote the isolated Hunter runtime, publisher recovery controls and player
   journeys with their fixtures, catalogs and reproducible dependency/test setup.
   Tests currently stored only in operational artifacts must become CI inputs.
5. Run current-source regressions and the existing two-player acceptance script;
   keep mocked adapters, installed-container checks and human acceptance separate.

Source approval, dependency security and command/process ownership remain distinct
from SQL test success. Chroma is intentional personal storage; its failing audit
does not authorize deleting it or migrating live memory.

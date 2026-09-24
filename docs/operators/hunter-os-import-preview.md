# Hunter OS import preview

The offline preview converts the four staged legacy YAML candidates into the typed
Hunter schema and inventories all 101 forum text blocks. It produces a review
artifact; it does not read or change SQL, memory, Discord, n8n, or model providers.
It is the planning portion of step 3 in the
[SQL delivery plan](../projects/HUNTER_OS_SQL_AUDIT.md).

## Run from an installed Core package

```sh
python -m animus.hunter_os.import_preview \
  --as-of 2026-09-22 \
  --output hunter-import-preview.json
```

The audit date is required for reproducibility. The default input is the snapshot
bundled in the Core wheel. To preview a revised local snapshot, supply
`--source-root /path/to/sources`. Its layout must match the bundled
`provenance.json`, `records/*.yaml` and `forum/*.md` layout. The manifest lists every
source file with its declared origin commit/path and SHA-256. Every listed file
must exist, match its hash and be UTF-8; extra files, duplicate manifest keys,
links, unsupported paths and oversized inputs are refused. Source revision fields
are retained declarations, not a remote Git verification or fact check.

The output must be a new file outside the source bundle. The CLI writes the entire
JSON artifact before making it visible and refuses to overwrite existing files or
links. Exit `0` means the review artifact was produced, including held or
conflicting items; it does not mean approval. Exit `1` means source/output failure;
argument errors use argparse's exit `2`. Standard output contains counts only.

The Python API is `build_preview(source_root=None, *, as_of=date(...))` in
`animus.hunter_os.import_preview`; `to_json()` returns deterministic JSON.

## What the report preserves

- Exact UTF-8 source text for every file, the original manifest, origin metadata,
  and hashes. Decoding `raw_text` and encoding UTF-8 reconstructs the source bytes.
- Four proposed canonical payloads, explicit source-field mappings, unmapped field
  pointers, source approval/date claims, and the existing domain audit findings.
- Every Markdown block with its original heading, section index, line range, raw
  text and hash. Preambles and explicitly identified navigation blocks are
  distinguished from sections awaiting structured mapping. No heading is assumed
  to be a canonical entity. Fenced examples containing `##` stay inside their block.
- Held item counts and conversion conflicts, including malformed records, unmapped
  fields, duplicate canonical IDs, missing/ambiguous relationship targets and
  duplicate forum headings. This is structural reconciliation, not adjudication of
  contradictory game facts between YAML and prose.

## Current snapshot result

| Item | Count |
| --- | ---: |
| Source files | 7 |
| Legacy records / proposed typed payloads | 4 / 4 |
| Weapons / monsters / guide text blocks | 40 / 37 / 24 |
| Held items | 105 |
| Items with conversion conflicts | 0 |
| Approved items / registry writes | 0 / 0 |

`created`, `updated`, and `unchanged` are null, with
`registry_comparison="not_performed"`. There is no database baseline comparison.
Repeated runs with the same source bytes and audit date yield identical JSON;
this proves deterministic planning, not an idempotent SQL apply operation.

| Legacy identity | Proposed ID |
| --- | --- |
| `rathian` | `mhw-monster-rathian` |
| `hunting_horn` | `mhw-weapon-type-hunting-horn` |
| `combat_healer_hh_lbg` | `mhw-guide-combat-healer-hh-lbg` |
| `omega_planetes` | `mhw-special-encounter-omega-planetes` |

All four original `verified` labels and `2026-09-21` dates remain in
`source_claims`. Proposed payloads have `status="review"`, unknown verification
dates and a review reason. Cited manuals lack content hashes; the hash of a YAML
file must not be substituted as proof of a manual's contents. Source IDs are local
locators, not invented feature attribution. Omega's mechanic evidence remains
unknown and its incomplete phase timeline retains the existing audit warning.
Hunting Horn controls retain their action-to-platform layout. Combat Healer's
relationship resolves to the sole Hunting Horn candidate in this snapshot.

Only these four identities have explicit conversion rules. Different variants,
unknown identities, nonempty legacy phase notes and unrecognized fields require
further mapping. Unmapped content remains in the exact source text. Omega Savage
and normal/Guardian headings stay distinct. An operator must resolve all issues
and verify facts before any future approval/import path consumes a candidate.

The packaged snapshot duplicates `integrations/hunter_review/sources` deliberately
so the installed command works without a repository checkout. A regression test
requires exact file-set and byte parity. Update both copies and their manifests
together; formatting hooks exclude these hashed source files to preserve evidence.

## Validation and remaining work

The local Python 3.12 run passed all 46 preview regressions and 85 existing Hunter
tests; 28 existing PostgreSQL cases were skipped because that run did not configure
a test database. Regressions cover complete reconciliation, raw-text round trips,
determinism, strict inputs, provenance mapping, identity/relationship conflicts,
source mutation, manifest validation and output preservation. A separately built
wheel installed in a fresh environment ran from outside the checkout with Python
isolated mode. Its two CLI runs produced byte-identical 155,731-byte reports
(SHA-256 `855ab50743c672b31e5cf35ea0c25fe7568ed517ff9aca2d83f33559ed739069`).

The full local Core suite then passed **3,869 tests, with 81 skips** in 261.69 seconds. Applicable pre-commit hooks, Ruff, formatting, docs, boundary and version checks passed. The Core mypy ratchet remained within its unchanged allowance (251 / 269), with no diagnostics in the new modules. Independent review findings were fixed and the follow-up review found no remaining issues.

No live migration or publication was performed. The [operator SQL importer](hunter-os-sql-import.md) now implements atomic candidate
staging with expected-version/fingerprint checks and unchanged replay. Presenter/chat integration, source approval, Stheno access, live schema and
memory-backend inspection, and the legacy Chroma audit remain cutover gates.

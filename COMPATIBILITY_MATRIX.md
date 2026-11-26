# Animus Compatibility Matrix

**Source metadata reviewed:** 2026-11-26 (North Star PR #163). Historical regression verification: 2026-07-19. No fresh runtime qualification is implied by this metadata review.

## Packages

| Package | Distribution Name | Source Version | Historical Maturity | Notes |
|---|---|---|---|---|
| `core` | `animus-core` | 2.3.0 | Production/Stable | Root version; CLI + memory operational |
| `forge` | `animus-forge` | 1.9.0 | Production/Stable | Workflow orchestration; extracted kernel in 2026-03 |
| `bootstrap` | `animus-bootstrap` | 0.8.0 | Alpha | Install daemon + dashboard |
| `quorum` | `animus-quorum` | 1.2.0 | Production/Stable | Rust core + Python bindings; name mismatch documented in ADR-001 |
| `types` | `animus-types` | 0.1.0 | Beta | Zero-prod-deps shared types; now includes 20 generated schema models |
| `kernel` | `animus-kernel` | 0.1.1 | Alpha | Extracted from Forge 2026-03 |
| `pwa` | `animus-pwa` (npm) | 0.1.0 | Alpha | TypeScript frontend |
| `contracts` | `animus-contracts` | 0.1.0 | Alpha | Pure JSON schemas + runtime validator |

## Compatibility Promise

The following ranges describe the declared dependency constraints. `scripts/check_compatibility.py` checks selected constraints; it does not prove runtime interoperability or cover every dependency.

| Consumer | Requires | Declared Range |
|---|---|---|
| `core` 2.3.x | `types` | `>=0.1.0,<1` |
| `forge` 1.9.x | `types` | `>=0.1.0,<1` |
| `forge` 1.9.x | `quorum` | `>=1.1.0,<2` |
| `forge` 1.9.x | `kernel` | `>=0.1.0,<1` |
| `kernel` 0.1.x | `types` | `>=0.1.0,<1` |

**No compatibility promise** yet for:
- `kernel` — internal API still evolving; Forge declares a dependency, but runtime compatibility beyond qualified combinations is not established
- `contracts` — schema-only; version pinned by consumer
- `pwa` — frontend; coupled to bootstrap API, not versioned together

## Inter-Package Dependencies

```
core ────────► types (animus-types>=0.1.0,<1)
forge ───────► types (animus-types>=0.1.0,<1)
forge ───────► quorum (animus-quorum>=1.1.0,<2)
forge ───────► kernel (animus-kernel>=0.1.0,<1)
bootstrap ───► (none declared in pyproject.toml; runtime coupling to core/types)
kernel ──────► types (animus-types>=0.1.0,<1)
quorum ──────► (none — Rust + standalone Python)
pwa ─────────► (none — TypeScript frontend)
contracts ───► (none — pure JSON)
```

## Known Incompatibilities / Risks

| Risk | Impact | Mitigation |
|---|---|---|
| `kernel` at 0.1.1 vs `forge` at 1.9.0 | Medium | Kernel was extracted from Forge 1.9.0; they share code lineage. Qualify compatibility at the exact candidate. |
| `quorum` PyPI name `animus-quorum` | Low | Name mismatch is historical (Convergent project predecessor). Package imports as `convergent` not `animus_quorum`. Documented in ADR-001. |
| No SemVer enforcement across packages | Medium | Each package versions independently. Breaking changes in `types` require coordinated bumps in `core`/`forge`/`bootstrap`. |

## When to Bump Versions

- **Major bump (X.y.z)**: Breaking API change in public interface
- **Minor bump (x.Y.z)**: New feature, backward-compatible
- **Patch bump (x.y.Z)**: Bugfix, backward-compatible
- **All packages**: Only when a cross-cutting change affects multiple packages

## Unified Version Target

The roadmap Phase 0 calls for version alignment. No unified version is enforced today. Options:

1. **Keep independent** — each package evolves at its own pace (current state)
2. **Lockstep bump** — all packages share a monorepo version (e.g. 2.4.0 together)
3. **Compatibility ranges** — specify `types>=0.1.0,<1` in downstream packages (partially implemented)

Recommended: Option 3 until Phase 2 Durable Core stabilizes, then evaluate Option 2.

## Verification

Run this command to confirm the matrix is still accurate:

```bash
python scripts/check_compatibility.py
```

A PASS establishes only the checks implemented by the script. Inspect the package manifests and run relevant integration tests before asserting runtime compatibility. All seven primary Python package manifests declare Python >=3.12. Independent package versions do not establish publication.

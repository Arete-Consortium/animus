# Package Architecture

> Dependency map, per-package purpose, and version matrix.

---

## Source version matrix (metadata reviewed 2026-11-26)

These are declared source versions, not publication or runtime qualification claims. See the [compatibility matrix](../../COMPATIBILITY_MATRIX.md) and current CI for evidence.

| Package | Distribution | Source version | Runtime requirement |
|---|---|---|---|
| [Core](../packages/core/README.md) | `animus-core` | 2.3.0 | Python >=3.12 |
| [Forge](../packages/forge/README.md) | `animus-forge` | 1.9.0 | Python >=3.12 |
| [Bootstrap](../packages/bootstrap/README.md) | `animus-bootstrap` | 0.8.0 | Python >=3.12 |
| [Quorum](../packages/quorum/README.md) | `animus-quorum` (import `convergent`) | 1.2.0 | Python >=3.12 |
| [Kernel](../packages/kernel/README.md) | `animus-kernel` | 0.1.1 | Python >=3.12 |
| [Types](../packages/types/README.md) | `animus-types` | 0.1.0 | Python >=3.12 |
| [Contracts](../packages/contracts/README.md) | `animus-contracts` | 0.1.0 | Python >=3.12 |
| [PWA](../packages/pwa/README.md) | `animus-pwa` | 0.1.0 | Node.js |

The optional [Forgehand context-provider pilot](../../packages/forgehand-context/README.md) is separately installed alongside Forgehand. It is not a required dependency of the Animus stack.

## Declared internal dependencies

```text
Core   -> Types
Forge  -> Types, Kernel, Quorum
Kernel -> Types
```

Arrows point from consumers to their declared dependencies. Bootstrap runtime integrations and the PWA API relationship are not equivalent to Python package dependencies. Consult the individual manifests for the complete external and optional dependency sets.

## Installation Order

```bash
# 1. Types first (sibling dependency)
pip install -e packages/types/

# 2. Any combination
pip install -e packages/core/
pip install -e packages/quorum/ -e packages/kernel/ -e packages/forge/
pip install -e packages/quorum/
pip install -e packages/bootstrap/
pip install -e packages/kernel/
```

---

## See Also

- [Packages](../packages/README.md) — Per-package documentation
- [Getting Started → Installation](../getting-started/installation.md)
- [Architecture → Overview](overview.md)

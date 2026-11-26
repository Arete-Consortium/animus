# Installation

> Install Animus packages independently. Each solves one problem and can be used on its own.

---

## Requirements

| Package | Python | Notes |
|---|---|---|
| Core | ≥3.12 | Exocortex engine |
| Forge | ≥3.12 | Orchestration (heavier deps) |
| Bootstrap | ≥3.12 | Daemon + dashboard |
| Quorum | ≥3.12 | Coordination protocol |
| Kernel | ≥3.12 | Standalone builder engine |
| Types | ≥3.12 | Shared schemas (install first) |
| Contracts | ≥3.12 | Canonical schemas and validation |

## Install All Packages

```bash
# Install shared types FIRST — it's a sibling dependency, not on PyPI
pip install -e packages/types/

# Then install any combination
pip install -e packages/core/
pip install -e packages/quorum/ -e packages/kernel/ -e packages/forge/
pip install -e packages/quorum/
pip install -e packages/bootstrap/
pip install -e packages/kernel/
```

## Verify

```bash
python -c "import animus; print('Core OK')"
python -c "import animus_forge; print('Forge OK')"
python -c "import animus_bootstrap; print('Bootstrap OK')"
python -c "import convergent; print('Quorum OK')"
python -c "import animus_kernel; print('Kernel OK')"
```

---

## See Also

- [Quickstart](quickstart.md) — Get running in 10 minutes
- [Concepts](concepts.md) — Understand the mental models
- [Operators → Configuration](../operators/configuration.md) — Configure after install

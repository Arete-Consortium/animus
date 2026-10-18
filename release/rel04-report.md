# REL-04 Report — Align Python Support Claims and Fix docs-deploy.yml

**Repository:** `AreteDriver/animus`
**Date:** 2026-08-01
**Commit:** `712994deb4ddba359f0b0931fef131c0edeff25a`
**Scope:** Package metadata and documentation deployment workflow.

---

## Problem

1. Python `requires-python` claims were inconsistent across the monorepo:
   - root: `>=3.10`
   - types/quorum: `>=3.10`
   - contracts/kernel/bootstrap: `>=3.11`
   - core: `>=3.10`
   - forge: `>=3.12`
   The full local stack effectively required Python 3.12, but the metadata allowed partial installs on lower versions.
2. Classifiers listed 3.10/3.11/3.12 on packages that now target the 3.12 stack.
3. `docs-deploy.yml` referenced non-existent action versions `actions/checkout@v7` and `actions/setup-python@v7`.
4. Bootstrap and Quorum still carried placeholder `your-org` author/URL metadata from the project template.

## Changes

- Root `pyproject.toml`: `requires-python = ">=3.12"`.
- `packages/types/pyproject.toml`: `requires-python = ">=3.12"`, classifier updated to 3.12 only.
- `packages/contracts/pyproject.toml`: `requires-python = ">=3.12"`, classifier updated to 3.12 only.
- `packages/kernel/pyproject.toml`: `requires-python = ">=3.12"`, classifier updated to 3.12 only.
- `packages/bootstrap/pyproject.toml`: `requires-python = ">=3.12"`, classifier updated to 3.12 only, author and URLs corrected to `AreteDriver/animus`.
- `packages/quorum/pyproject.toml`: `requires-python = ">=3.12"`, classifier updated to 3.12 only, author and URLs corrected to `AreteDriver/animus`.
- `packages/forge/pyproject.toml`: author and URLs corrected to `AreteDriver/animus`; removed untested Python 3.13 classifier.
- `packages/types/pyproject.toml`: author corrected to `AreteDriver`.
- `packages/core/pyproject.toml`: `requires-python = ">=3.12"`, classifier updated to 3.12 only.
- `packages/forge/pyproject.toml`: already `>=3.12`, no change.
- `.github/workflows/docs-deploy.yml`: `actions/checkout@v7` → `actions/checkout@v4`, `actions/setup-python@v7` → `actions/setup-python@v5`.
- `release/package-matrix.yaml`: updated all `requires_python` and `python_floor` values to `>=3.12`, marked REL-04 notes closed.

## Verification

- `grep "requires-python"` across all `pyproject.toml` files returns only `>=3.12`.
- No remaining `your-org` references in `packages/bootstrap/pyproject.toml` or `packages/quorum/pyproject.toml`.
- `docs-deploy.yml` references valid action versions.
- Ruff clean on changed files.

## Notes

- GitHub Pages deployment remains blocked for private repositories per `animus-mkdocs-deployment-blocked` memory; this commit fixes only the invalid action version references.
- Some per-package `tool.ruff.target-version` and `tool.mypy.python_version` remain at their original values (e.g. `py310`, `py311`) because bumping them would change lint/type-check behavior. They can be aligned later if desired.

## Remaining work

- Re-run clean-room wheelhouse isolated install once `animus-types` is published to PyPI.
- Decide on GitHub Pages alternative (public repo, paid plan, or Netlify/Cloudflare) and update deployment workflow accordingly.

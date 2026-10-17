# REL-03 Report — Move Forge Runtime State to Platform Directories

**Repository:** `AreteDriver/animus`
**Date:** 2026-08-01
**Commit:** TBD
**Scope:** `packages/forge` runtime state directories.

---

## Problem

`animus_forge.config.settings.Settings` defaulted `base_dir`, `logs_dir`, `workflows_dir`, `schedules_dir`, `webhooks_dir`, `jobs_dir`, and `plugins_dir` to paths inside the package source tree (`Path(__file__).parent.parent / ...`). When `animus-forge` is installed as a wheel, these paths resolve to `site-packages/animus_forge/...`. The `model_post_init` method creates these directories at import time, which fails on read-only installs and is improper for runtime state.

## Changes

- `packages/forge/src/animus_forge/config/settings.py`
  - New default `base_dir` is `Path.home() / ".animus"`.
  - Runtime directory fields (`logs_dir`, `workflows_dir`, `schedules_dir`, `webhooks_dir`, `jobs_dir`, `plugins_dir`) keep their old package-relative default factories for backward compatibility with explicit env overrides, but are relocated to subdirectories of `base_dir` in `model_post_init` when they still equal the old package-relative defaults.
  - `prompts_dir` and `skills_dir` remain package-relative because they reference static assets shipped with the package.
  - Added `_PACKAGE_SRC`, `_OLD_BASE_DIR_DEFAULT`, and `_PKG_RUNTIME_DIR_DEFAULTS` constants so relocation is exact and deterministic.

## Verification

- `pytest packages/forge/tests/test_config_settings.py` — 86 passed.
- `pytest packages/forge/tests/test_config_yaml.py` — 45 passed.
- `pytest packages/forge/tests/test_logging_config.py` — passed.
- `pytest packages/forge/tests/test_scheduler_lease.py packages/forge/tests/test_scheduler_runtime_baseline.py packages/forge/tests/test_scheduler_phase5.py packages/forge/tests/test_workspace.py` — passed.
- Manual check: `Settings(_env_file=None)` produces:
  - `base_dir = ~/.animus`
  - `logs_dir = ~/.animus/logs`
  - `workflows_dir = ~/.animus/workflows`
  - `plugins_dir = ~/.animus/plugins/custom`
  - `prompts_dir` and `skills_dir` still inside the package tree.
- Manual check: `Settings(_env_file=None, base_dir="/tmp/custom")` relocates runtime subdirs to `/tmp/custom/{logs,workflows,...}`.
- Ruff clean on changed files.

## Remaining work

- `skills_dir` may also need relocation if the skill evolver writes to it at runtime; left for a future packaging pass because the matrix note did not include skills.
- REL-04: align Python support claims and fix `docs-deploy.yml`.
- Re-run clean-room wheelhouse isolated install once `animus-types` is published to PyPI.

"""Self-modification tools — read, write, and patch Animus source code."""

from __future__ import annotations

import difflib
import logging
import os
from pathlib import Path

from animus_bootstrap.intelligence.tools.executor import ToolDefinition

logger = logging.getLogger(__name__)


def _validated_source_root(candidate: Path) -> Path | None:
    """Return a canonical Animus checkout root, or ``None`` when invalid."""
    try:
        resolved = candidate.expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    marker = resolved / "packages" / "bootstrap" / "pyproject.toml"
    return resolved if marker.is_file() else None


def _discover_animus_root() -> Path | None:
    """Discover an explicit or source-tree Animus checkout.

    Installed wheels are not source checkouts.  In that layout this returns
    ``None`` so self-modification tools are not registered rather than
    accidentally treating a broad filesystem ancestor as the sandbox.
    """
    configured = os.environ.get("ANIMUS_SOURCE_ROOT")
    if configured:
        root = _validated_source_root(Path(configured))
        if root is None:
            logger.error("ANIMUS_SOURCE_ROOT is not a validated Animus checkout")
        return root

    for parent in Path(__file__).resolve().parents:
        root = _validated_source_root(parent)
        if root is not None:
            return root
    return None


# Sandbox to a validated Animus monorepo only. Wheels fail closed by default.
_ANIMUS_ROOT: Path | None = _discover_animus_root()


def _require_animus_root() -> Path:
    if _ANIMUS_ROOT is None:
        raise ValueError(
            "Animus source root is unavailable; set ANIMUS_SOURCE_ROOT to a validated checkout"
        )
    return _ANIMUS_ROOT


def _resolve_animus_path(path: str) -> Path:
    """Resolve a path relative to the animus monorepo root.

    Raises ValueError if the resolved path escapes the sandbox.
    """
    root = _require_animus_root()
    relative = Path(path)
    if relative.is_absolute():
        raise ValueError(f"Path '{path}' must be relative to the Animus source root")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(
            f"Path '{path}' (resolved: {resolved}) escapes the animus root: {root}"
        ) from None
    return resolved


async def _code_read(path: str) -> str:
    """Read a source file from the animus monorepo."""
    try:
        resolved = _resolve_animus_path(path)
    except ValueError as exc:
        return f"Permission denied: {exc}"

    try:
        content = resolved.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"File not found: {resolved}"
    except IsADirectoryError:
        return f"Path is a directory: {resolved}"
    except OSError as exc:
        return f"Read error: {exc}"

    return content


async def _code_write(path: str, content: str) -> str:
    """Write content to a source file in the animus monorepo."""
    try:
        resolved = _resolve_animus_path(path)
    except ValueError as exc:
        return f"Permission denied: {exc}"

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
    except PermissionError:
        return f"OS permission denied: {resolved}"
    except OSError as exc:
        return f"Write error: {exc}"

    logger.info("Self-modification: wrote %d bytes to %s", len(content), resolved)
    return f"Wrote {len(content)} bytes to {path}"


async def _code_patch(path: str, old: str, new: str, dry_run: bool = False) -> str:
    """Apply a search-and-replace patch to a source file.

    Finds the first occurrence of ``old`` in the file and replaces it with
    ``new``.  Returns a unified diff preview of the change.

    If ``dry_run`` is True, returns the diff without writing to disk.
    """
    try:
        resolved = _resolve_animus_path(path)
    except ValueError as exc:
        return f"Permission denied: {exc}"

    try:
        original = resolved.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"File not found: {resolved}"
    except OSError as exc:
        return f"Read error: {exc}"

    if old not in original:
        return f"Search string not found in {path}"

    patched = original.replace(old, new, 1)

    # Generate a unified diff for the caller to review
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        patched.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    )
    diff_text = "".join(diff)

    if dry_run:
        return f"[DRY RUN] Diff for {path}:\n{diff_text}"

    try:
        resolved.write_text(patched, encoding="utf-8")
    except OSError as exc:
        return f"Write error: {exc}"

    logger.info("Self-modification: patched %s", resolved)
    return f"Patched {path}:\n{diff_text}"


async def _code_list(path: str = "", pattern: str = "*.py") -> str:
    """List files under a directory in the animus monorepo."""
    try:
        root = _require_animus_root()
        resolved = _resolve_animus_path(path or ".")
    except ValueError as exc:
        return f"Permission denied: {exc}"

    if not resolved.is_dir():
        return f"Not a directory: {resolved}"

    files = sorted(resolved.glob(pattern))
    if not files:
        return f"No files matching '{pattern}' in {path or '.'}"

    # Return relative paths, cap at 100 entries
    lines = []
    for f in files[:100]:
        try:
            rel = f.relative_to(root)
        except ValueError:
            continue
        lines.append(str(rel))

    if len(files) > 100:
        lines.append(f"... and {len(files) - 100} more")

    return "\n".join(lines)


def get_code_edit_tools() -> list[ToolDefinition]:
    """Return self-modification tool definitions. All require approval."""
    if _ANIMUS_ROOT is None:
        logger.warning("Self-modification tools disabled: no validated Animus source root")
        return []
    return [
        ToolDefinition(
            name="code_read",
            description=(
                "Read a source file from the Animus codebase. "
                "Path is relative to the monorepo root."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to the animus monorepo root.",
                    },
                },
                "required": ["path"],
            },
            handler=_code_read,
            category="self_modification",
            permission="approve",
        ),
        ToolDefinition(
            name="code_write",
            description=(
                "Write content to a source file in the Animus codebase. "
                "Creates parent directories as needed. Requires approval."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to the animus monorepo root.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content to write.",
                    },
                },
                "required": ["path", "content"],
            },
            handler=_code_write,
            category="self_modification",
            permission="approve",
        ),
        ToolDefinition(
            name="code_patch",
            description=(
                "Apply a search-and-replace patch to a source file. "
                "Finds the first occurrence of 'old' and replaces it with 'new'. "
                "Returns a unified diff preview. Use dry_run=true to preview "
                "without writing. Requires approval."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to the animus monorepo root.",
                    },
                    "old": {
                        "type": "string",
                        "description": "Exact text to search for.",
                    },
                    "new": {
                        "type": "string",
                        "description": "Replacement text.",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "Preview diff without writing. Default false.",
                        "default": False,
                    },
                },
                "required": ["path", "old", "new"],
            },
            handler=_code_patch,
            category="self_modification",
            permission="approve",
        ),
        ToolDefinition(
            name="code_list",
            description=(
                "List files matching a glob pattern in the Animus codebase. "
                "Defaults to listing Python files at the repo root."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to repo root. Empty for root.",
                        "default": "",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match files.",
                        "default": "*.py",
                    },
                },
            },
            handler=_code_list,
            category="self_modification",
            permission="approve",
        ),
    ]

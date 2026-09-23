#!/usr/bin/env python3
"""Run Forge's four resource-limit checks in a disposable Linux container.

Usage: python scripts/verify-code-sandbox.py --image <existing-local-python-image>
The image must include Python and pydantic. Nothing is pulled or installed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path


def verify(source: Path) -> None:
    # Load only the evaluation module, avoiding application startup and services.
    package = types.ModuleType("sandbox_probe")
    package.__path__ = [str(source)]
    sys.modules[package.__name__] = package
    spec = importlib.util.spec_from_file_location("sandbox_probe.metrics", source / "metrics.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metric_type = module.CodeExecutionMetric
    assert metric_type(timeout=2)._execute_python("while True:\n    pass\n") == ("TIMEOUT", False)
    out, ok = metric_type(timeout=8)._execute_python(
        "x = bytearray(1024 * 1024 * 1024)\nprint('allocated', len(x))\n"
    )
    assert not ok and out != "TIMEOUT" and "allocated" not in out, (out, ok)
    metric = metric_type(timeout=5)
    out, ok = metric._execute_python("print(6 * 7)\n")
    assert ok and "42" in out, (out, ok)
    case = module.EvalCase(input="test", expected="test")
    for code in ("raise RuntimeError('boom')", "import sys; sys.exit(7)", "1 / 0"):
        assert metric.score(f"```python\n{code}\n```", None, case) == 0.0
    assert metric.score("```python\nprint('hi')\n```", None, case) == 1.0
    print(
        json.dumps(dict.fromkeys(("timeout", "memory_limit", "normal_code", "crash_scoring"), True))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", help="Existing local Linux image with Python and pydantic")
    parser.add_argument("--inside", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside:
        if sys.platform != "linux":
            parser.error("Resource-limit verification requires Linux")
        verify(args.inside)
        return 0
    if not args.image:
        parser.error("--image is required; images are never pulled automatically")
    docker = shutil.which("docker")
    if not docker:
        parser.error("Docker CLI is unavailable; start Docker Desktop and add its CLI to PATH")

    def run(*argv: str) -> str:
        return subprocess.check_output([docker, *argv], text=True, timeout=60).strip()

    run("image", "inspect", args.image)
    container_id = None
    try:
        with tempfile.TemporaryDirectory(prefix="animus-sandbox-probe-") as directory:
            bundle = Path(directory)
            evaluation = (
                Path(__file__).resolve().parents[1] / "packages/forge/src/animus_forge/evaluation"
            )
            for filename in ("base.py", "metrics.py"):
                shutil.copy2(evaluation / filename, bundle / filename)
            shutil.copy2(__file__, bundle / "verify.py")
            container_id = run(
                "create",
                "--pull",
                "never",
                "--network",
                "none",
                "--memory",
                "1g",
                "--memory-swap",
                "1g",
                "--pids-limit",
                "64",
                "--cpus",
                "1",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--entrypoint",
                "python",
                args.image,
                "/probe/verify.py",
                "--inside",
                "/probe",
            )
            run("cp", f"{bundle}/.", f"{container_id}:/probe")
        run("start", container_id)
        deadline = time.monotonic() + 40
        while run("inspect", "--format", "{{.State.Running}}", container_id) == "true":
            if time.monotonic() >= deadline:
                raise TimeoutError("Sandbox verification exceeded its wall-clock limit")
            time.sleep(0.25)
        print(run("logs", container_id))
        return int(run("inspect", "--format", "{{.State.ExitCode}}", container_id))
    finally:
        if container_id:
            run("rm", "--force", container_id)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (subprocess.TimeoutExpired, TimeoutError) as exc:
        print(f"Sandbox verification could not finish: {exc}", file=sys.stderr)
        print(
            "Check Docker Desktop startup before retrying; no sandbox check passed.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

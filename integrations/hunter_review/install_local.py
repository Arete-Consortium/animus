"""Provision one scoped credential and the bounded local review container.

Run after building animus-hunter-review:local. Existing credentials are reused;
no existing credential is exported. The n8n workflow is installed through MCP.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / ".local"
CONTAINER = "animus-hunter-review"


def replace_service(run: Callable[..., str]) -> None:
    """Prepare fresh snapshots, then switch containers with rollback on failure."""
    existing = run("ps", "-a", "--filter", f"name=^/{CONTAINER}$", "--format", "{{.Names}}")
    if existing:
        label = run(
            "inspect", "--format", '{{index .Config.Labels "com.animus.component"}}', CONTAINER
        )
        if label != "hunter-review":
            raise RuntimeError("Existing container name belongs to another service")
    suffix = secrets.token_hex(6)
    helper = f"hunter-review-install-{suffix}"
    candidate = f"{CONTAINER}-next-{suffix}"
    backup = f"{CONTAINER}-rollback-{suffix}"
    sources = f"animus-hunter-review-sources-{suffix}"
    config = f"animus-hunter-review-config-{suffix}"
    uid, gid = os.getuid(), os.getgid()
    helper_created = candidate_created = old_stopped = old_renamed = switched = False
    try:
        run(
            "create",
            "--name",
            helper,
            "--network",
            "none",
            "--user",
            "0:0",
            "--mount",
            f"type=volume,src={sources},dst=/sources",
            "--mount",
            f"type=volume,src={config},dst=/config",
            "--mount",
            "type=volume,src=animus-hunter-review-state,dst=/state",
            "--entrypoint",
            "python",
            "animus-hunter-review:local",
            "-c",
            "import time; time.sleep(180)",
        )
        helper_created = True
        run("start", helper)
        run("cp", "-a", f"{ROOT / 'sources'}/.", f"{helper}:/sources")
        run("cp", "-a", f"{LOCAL / 'config'}/.", f"{helper}:/config")
        run(
            "exec",
            helper,
            "python",
            "-c",
            "import os; "
            f"[os.chown(p, {uid}, {gid}) "
            "for p in ['/state', '/config', '/config/connector.token']]; "
            "os.chmod('/state', 0o700); os.chmod('/config', 0o700); "
            "os.chmod('/config/connector.token', 0o600)",
        )
        # Validate as the runtime UID, without writing review history.
        run(
            "exec",
            "--user",
            f"{uid}:{gid}",
            helper,
            "python",
            "-c",
            "from pathlib import Path; from integrations.hunter_review.review import scan; "
            "scan(Path('/sources')); "
            "assert len(Path('/config/connector.token').read_text().strip()) >= 32",
        )
        run(
            "create",
            "--name",
            candidate,
            "--label",
            "com.animus.component=hunter-review",
            "--pull",
            "never",
            "--restart",
            "unless-stopped",
            "--network",
            "n8n_default",
            "--network-alias",
            "hunter-review",
            "--publish",
            "127.0.0.1:8788:8788",
            "--user",
            f"{uid}:{gid}",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            "--memory",
            "512m",
            "--memory-swap",
            "512m",
            "--pids-limit",
            "32",
            "--cpus",
            "0.5",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--mount",
            f"type=volume,src={sources},dst=/sources,readonly",
            "--mount",
            f"type=volume,src={config},dst=/config,readonly",
            "--mount",
            "type=volume,src=animus-hunter-review-state,dst=/state",
            "animus-hunter-review:local",
        )
        candidate_created = True
        if existing:
            run("stop", CONTAINER)
            old_stopped = True
            run("rename", CONTAINER, backup)
            old_renamed = True
        run("rename", candidate, CONTAINER)
        switched = True
        run("start", CONTAINER)
        run(
            "exec",
            CONTAINER,
            "python",
            "-c",
            """
import time
import urllib.request
for attempt in range(20):
    try:
        urllib.request.urlopen('http://127.0.0.1:8788/healthz', timeout=1)
        break
    except OSError:
        time.sleep(.25)
else:
    raise RuntimeError('Review service failed readiness')
""",
        )
    except Exception:
        # Never clear or mutate the previous snapshot volumes during replacement.
        if candidate_created:
            run("rm", "-f", CONTAINER if switched else candidate)
        if old_renamed:
            run("rename", backup, CONTAINER)
        if old_stopped:
            run("start", CONTAINER)
        raise
    finally:
        if helper_created:
            run("rm", "-f", helper)
    if old_renamed:
        run("rm", backup)
    # Previous source/config volumes are retained; review history uses its original volume.


def main() -> None:
    docker = shutil.which("docker")
    if not docker:
        raise SystemExit("Docker CLI must be on PATH")

    def run(*args: str, stdin: str | None = None) -> str:
        result = subprocess.run(
            [docker, *args], input=stdin, text=True, capture_output=True, timeout=60
        )
        if result.returncode:
            # Import failure messages could contain submitted credentials.
            raise RuntimeError(f"Docker operation failed: {args[0]}")
        return result.stdout.strip()

    LOCAL.mkdir(mode=0o700, exist_ok=True)
    for name in ("config", "state"):
        (LOCAL / name).mkdir(mode=0o700, exist_ok=True)
    token_path = LOCAL / "config/connector.token"
    if not token_path.exists():
        with token_path.open("x") as stream:
            os.chmod(token_path, 0o600)
            stream.write(secrets.token_urlsafe(32) + "\n")
    token = token_path.read_text().strip()
    record_path = LOCAL / "installation.json"
    if record_path.exists():
        record = json.loads(record_path.read_text())
    else:
        record = {"credential_id": secrets.token_hex(8), "container": CONTAINER}
        record_path.write_text(json.dumps(record, indent=2) + "\n")
    credential = [
        {
            "id": record["credential_id"],
            "name": "Hunter Review - Local Only",
            "type": "httpHeaderAuth",
            "data": {"name": "Authorization", "value": f"Bearer {token}"},
        }
    ]
    directory = None
    try:
        directory = run(
            "exec",
            "-i",
            "n8n-n8n-1",
            "node",
            "-e",
            """
const fs = require('fs');
const directory = fs.mkdtempSync('/tmp/hunter-review-credential-');
fs.chmodSync(directory, 0o700);
fs.writeFileSync(directory + '/credential.json', fs.readFileSync(0), {mode: 0o600});
console.log(directory);
""",
            stdin=json.dumps(credential),
        )
        if not re.fullmatch(r"/tmp/hunter-review-credential-[A-Za-z0-9]+", directory):
            raise RuntimeError("Unexpected credential import location")
        run(
            "exec", "n8n-n8n-1", "n8n", "import:credentials", f"--input={directory}/credential.json"
        )
    finally:
        if directory and re.fullmatch(r"/tmp/hunter-review-credential-[A-Za-z0-9]+", directory):
            run(
                "exec",
                "n8n-n8n-1",
                "node",
                "-e",
                "require('fs').rmSync(process.argv[1], {recursive:true, force:true})",
                directory,
            )
    replace_service(run)
    print(
        json.dumps(
            {
                "service": CONTAINER,
                "credential_id": record["credential_id"],
                "health_url": "http://localhost:8788/healthz",
            }
        )
    )


if __name__ == "__main__":
    main()

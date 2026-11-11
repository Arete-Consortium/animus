# Project Status

| Attribute | Value |
|-----------|-------|
| Status | **HOLD — partially operational on Stheno** |
| Last verified | 2026-11-11 |
| Active release | Bootstrap `62e51043a5676ebcd9cff1654836f76f1545952d` |
| Local inference | Verified through Animus with Ollama `qwen3.8:27b` |
| Browser chat | Verified locally at desktop and phone-sized viewports |
| Mobile/Tailscale | Not routed to Animus; real-device access unverified |
| Governed delegation | Blocked by Forgehand persisted-contract/schema drift |
| Candidate branch | `codex/stheno-local-ai-integration` (not deployed) |

## Verified working

- Bootstrap 0.8.0 is active on Stheno at loopback `127.0.0.1:7700`.
- The PWA loads, renders persisted conversation history, and completed an exact-marker chat round trip through local inference.
- Desktop and 390x844 responsive layouts render the Chat, Capture, Status, Personas, and Citizens navigation.
- Bootstrap conversation and semantic-memory records survived a service restart.
- Ollama is local-only and unloads models after idle; no model was active at the latest observation.
- Forgehand status evidence demonstrates that Governor retains completion authority: a compatible run had passing criteria but remained stopped because Governor returned `done=False`.

## Present in code but not operational

- Forge, Kernel, and Quorum are not installed in either active Animus environment.
- Kernel-backed PWA checkpoints are unavailable; Bootstrap conversation history is the only verified browser continuity mechanism.
- The existing Bootstrap `ForgeBackend` is an unrelated chat-style HTTP backend, not the independent Forgehand runtime.
- No Animus adapter currently exposes Forgehand submit, status, evidence, safe stop, or resume operations.
- MCP Manager's repository is present, but its virtualenv launcher cannot import `mcp_manager`.

## Qualification blockers

1. **Authentication:** loopback `auto` mode trusts proxy/tunnel traffic. An intentionally invalid token reached persisted history through an SSH tunnel. Candidate code makes `always` mode authenticate loopback HTTP and WebSocket requests, but it is not deployed or configured.
2. **Forgehand compatibility:** recent persisted runs contain contract fields rejected by the installed 0.1.0 schema, so status and resume are unreliable. Forgehand also has pre-existing tracked and untracked work that this assignment must preserve.
3. **Mobile routing:** Tailscale Serve currently targets another local service, not Animus. No network configuration was changed.
4. **Resume semantics:** browser history persists, but Kernel checkpoints are unavailable and long-running Forgehand restart/resume is not qualified.
5. **Release evidence:** the newest security/integration candidate has only targeted local validation. It has not passed a fresh full regression suite, independent review, deployment, or real-device acceptance.
6. **Host reliability:** the previous boot ended abruptly at 2026-11-10 23:20:11 and the next boot began at 2026-11-11 03:34:35. Journald explicitly reported unclean system and user journals. No orderly system shutdown, kernel OOM kill, thermal trip, watchdog reset, panic, or disk I/O error was found in the retained journal, so external power loss or a hard reset is the leading explanation but not proven. Two unrelated broken services (`arete-bot` and `animus-discord`) are also restarting every 10 seconds and had exceeded 4,400 restarts before the outage; service changes require separate approval.
7. **Token handling:** the PWA persists a long-lived bearer token in Web Storage and sends it in the WebSocket handshake URL. Tailscale and strict XSS controls reduce exposure, but browser extensions, URL logging, exported profiles, or an XSS flaw could disclose it. A short-lived WebSocket ticket and less persistent browser credential model remain future hardening work.

Historical source-test counts in older status documents remain useful development
evidence, but they are not treated as proof of the active Stheno deployment.

## Install

```bash
git clone https://github.com/your-org/animus.git && cd animus
pip install -e packages/types/ -e "packages/core/[dev]" -e packages/kernel/ -e packages/contracts/
python -m animus.cli architect --focus codebase
```

> Full walkthrough: [`docs/user-scenarios/v2.3-first-run.md`](docs/user-scenarios/v2.3-first-run.md)

# Animus Core

Personal AI exocortex with persistent memory, multi-model cognitive layer, and MCP server.

## Features

- **Persistent memory** — episodic, semantic, procedural (ChromaDB or SQLite)
- **Multi-model cognitive layer** — Ollama, Anthropic, OpenAI with streaming
- **Dual-model routing** — Claude brain + Ollama hands (auto-detected)
- **40+ CLI commands** — memory, tasks, entities, learning, integrations
- **MCP server** — 9 tools for Claude Code integration
- **Tool sandbox** — write_roots restriction, command sandboxing
- **Agent loop** — constrained tool use with approval callbacks

## Install

```bash
pip install animus-core
# New installs using JSON memory (no Chroma dependency):
export ANIMUS_MEMORY_BACKEND=json
```

With optional providers:
```bash
pip install "animus-core[anthropic,openai,mcp,api]"
```

ChromaDB is now an optional legacy backend: existing Chroma deployments require
`pip install "animus-core[chroma]"`. Their configured backend and stored memories
are unchanged. Missing Chroma raises an actionable error instead of silently
opening an empty JSON store. Changing backends is not a migration.

The SQL/Hunter profile uses `animus-core[postgres]` and does not install Chroma.
Chroma's outstanding upstream vulnerabilities are still checked by a separate,
blocking security job; see [the CI repair notes](../../docs/CI_REPAIR.md).

## Usage

```bash
# Interactive CLI
python -m animus

# MCP server for Claude Code
python -m animus.mcp_server
```

## Part of the Animus Monorepo

- [Animus Forge](https://github.com/AreteDriver/animus/tree/main/packages/forge) — multi-agent orchestration
- [Animus Quorum](https://pypi.org/project/convergentAI/) — coordination protocol
- [Animus Bootstrap](https://github.com/AreteDriver/animus/tree/main/packages/bootstrap) — system daemon

## License

MIT

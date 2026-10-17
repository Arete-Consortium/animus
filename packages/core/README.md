# Animus Core

Personal AI exocortex with persistent memory, multi-model cognitive layer, and MCP server.

## Features

- **Persistent memory** — episodic, semantic, procedural (local JSON or durable SQL)
- **Multi-model cognitive layer** — Ollama, Anthropic, OpenAI with streaming
- **Dual-model routing** — Claude brain + Ollama hands (auto-detected)
- **40+ CLI commands** — memory, tasks, entities, learning, integrations
- **MCP server** — 9 tools for Claude Code integration
- **Tool sandbox** — write_roots restriction, command sandboxing
- **Agent loop** — constrained tool use with approval callbacks

## Install

```bash
pip install animus-core
# Local JSON memory is the default and has no external database dependency.
```

With optional providers:
```bash
pip install "animus-core[anthropic,openai,mcp,api]"
```

ChromaDB is retired from the supported Core runtime because no patched upstream
release is available. A legacy `memory.backend: chroma` setting fails closed and
does not open an empty replacement store. Preserve the source data and follow the
[retirement plan](../../docs/operators/chroma-retirement-plan.md) before changing
the configured backend; changing the setting alone is not a migration.

The SQL/Hunter profile uses `animus-core[postgres]`. Core's security job verifies
that a supported base install does not reintroduce the retired `chromadb` package;
see [the CI repair notes](../../docs/CI_REPAIR.md).

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

# Animus Core

Personal AI exocortex with persistent memory, multi-model cognitive layer, and MCP server.

## Features

- **Persistent memory** — episodic, semantic, and procedural through local JSON
  or a configured durable SQL store
- **Multi-model cognitive layer** — Ollama, Anthropic, OpenAI with streaming
- **Dual-model routing** — Claude brain + Ollama hands (auto-detected)
- **40+ CLI commands** — memory, tasks, entities, learning, integrations
- **MCP server** — 9 tools for Claude Code integration
- **Tool sandbox** — write_roots restriction, command sandboxing
- **Agent loop** — constrained tool use with approval callbacks

## Install

```bash
pip install animus-core
```

With optional providers:
```bash
pip install "animus[anthropic,openai,mcp,api]"
```

## Usage

```bash
# Interactive CLI
python -m animus

# MCP server for Claude Code
python -m animus.mcp_server
```

Legacy Core Chroma configurations fail closed because no patched upstream
release is available. Existing data must follow the
[Chroma retirement plan](../../operators/chroma-retirement-plan.md) before an
operator selects a supported backend; Core does not silently open an empty
replacement store.

## Part of the Animus Monorepo

- [Animus Forge](https://github.com/your-org/animus/tree/main/packages/forge) — multi-agent orchestration
- [Animus Quorum](https://pypi.org/project/convergentAI/) — coordination protocol
- [Animus Bootstrap](https://github.com/your-org/animus/tree/main/packages/bootstrap) — system daemon

## License

MIT

# Quickstart

> Get Animus installed and running in under 10 minutes.

---

## Prerequisites

- Python 3.12+
- Git
- A local LLM via [Ollama](https://ollama.com)

## Install

```bash
# Clone the repo
git clone https://github.com/Arete-Consortium/animus.git
cd animus

# Install shared types first
pip install -e packages/types/

# Install the packages you need
pip install -e packages/core/
pip install -e packages/bootstrap/
```

## Run

```bash
# Start the Bootstrap daemon and dashboard
animus-bootstrap install

# Or run Core directly
python -m animus
```

The Bootstrap wizard will guide you through API keys, identity setup, and memory backend configuration. The dashboard opens at `http://localhost:7700`.

---

## Next Steps

- [Installation Guide](installation.md) — Per-package install details
- [Concepts](concepts.md) — Core mental models
- [Contributing Setup](../contributing/setup.md) — For developers

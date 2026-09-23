"""Ollama-first configuration patch for Animus public release.

Applies changes to make Ollama the enforced default provider.
Cloud providers (Anthropic, OpenAI) are opt-in only via explicit env var.

Usage:
    cd ~/projects/animus
    git apply scripts/ollama_first_config.patch
"""

from pathlib import Path


def patch_main_py():
    """Patch __main__.py to remove auto-swap logic."""
    path = Path("packages/core/animus/__main__.py")
    if not path.exists():
        print(f"SKIP: {path} not found")
        return

    content = path.read_text()

    # Remove the auto-swap block (lines 526-539 in original)
    old_block = """    # Dual-model routing: if primary is Ollama and ANTHROPIC_API_KEY is set,
    # use Claude as primary brain and Ollama as local hands (or vice versa).
    fallback_config: ModelConfig | None = None
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if model_config.provider.value == "ollama" and anthropic_key:
        # Swap: Claude becomes primary, Ollama becomes fallback
        fallback_config = model_config
        model_config = ModelConfig.anthropic("claude-sonnet-4-20250514")
        model_config.api_key = anthropic_key
    elif model_config.provider.value == "anthropic":
        # Add Ollama fallback for cheap tasks
        ollama_model = os.environ.get("OLLAMA_MODEL", "deepseek-coder-v2")
        fallback_config = ModelConfig.ollama(ollama_model)
        fallback_config.base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
"""

    new_block = """    # Ollama-first: cloud providers are opt-in only.
    # Set ANIMUS_CLOUD_PROVIDER=anthropic|openai to enable cloud.
    fallback_config: ModelConfig | None = None
    cloud_provider = os.environ.get("ANIMUS_CLOUD_PROVIDER", "").lower()
    if cloud_provider == "anthropic":
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if not anthropic_key:
            raise ValueError("ANIMUS_CLOUD_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        fallback_config = model_config  # Ollama becomes fallback
        model_config = ModelConfig.anthropic("claude-sonnet-4-20250514")
        model_config.api_key = anthropic_key
    elif cloud_provider == "openai":
        openai_key = os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            raise ValueError("ANIMUS_CLOUD_PROVIDER=openai requires OPENAI_API_KEY")
        fallback_config = model_config
        model_config = ModelConfig.openai("gpt-4o")
        model_config.api_key = openai_key
    # Default: Ollama remains primary, no fallback
"""

    if old_block not in content:
        print(f"SKIP: {path} already patched or block not found")
        return

    content = content.replace(old_block, new_block)
    path.write_text(content)
    print(f"PATCHED: {path}")


def patch_config_py():
    """Patch config.py to document the opt-in model."""
    path = Path("packages/core/animus/config.py")
    if not path.exists():
        print(f"SKIP: {path} not found")
        return

    content = path.read_text()

    old_doc = """    Supports three providers:
      - "ollama"    — local models via Ollama (default)
      - "anthropic" — Claude models via Anthropic API
      - "openai"    — OpenAI models, or any OpenAI-compatible endpoint
                      (LM Studio, vLLM, Together, Groq, etc.) via openai_base_url
    """

    new_doc = """    OLLAMA-FIRST DEFAULT:
      - Ollama is the primary provider. No API keys required.
      - Cloud providers are OPT-IN via ANIMUS_CLOUD_PROVIDER env var.

    Supported providers:
      - "ollama"    — local models via Ollama (default, zero cost)
      - "anthropic" — Claude models via Anthropic API (opt-in)
      - "openai"    — OpenAI models, or any OpenAI-compatible endpoint
                      (LM Studio, vLLM, Together, Groq, etc.) via openai_base_url
    """

    if old_doc not in content:
        print(f"SKIP: {path} doc block not found")
        return

    content = content.replace(old_doc, new_doc)
    path.write_text(content)
    print(f"PATCHED: {path}")


def patch_readme():
    """Update README.md with Ollama-first install instructions."""
    path = Path("README.md")
    if not path.exists():
        print(f"SKIP: {path} not found")
        return

    content = path.read_text()

    # Find the first ## Installation or ## Getting Started section
    if "## Quick Start" in content:
        marker = "## Quick Start"
    elif "## Installation" in content:
        marker = "## Installation"
    elif "## Getting Started" in content:
        marker = "## Getting Started"
    else:
        print("SKIP: No install section found in README.md")
        return

    ollama_block = """
### Prerequisites (Ollama — local, zero cost)

1. Install Ollama: https://ollama.com/download
2. Pull a model: `ollama pull qwen3:32b` or `ollama pull llama3.1:8b`
3. Verify: `ollama run qwen3:32b "Say hello"`

### Optional — Cloud provider (opt-in)

Set `ANIMUS_CLOUD_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=sk-...`
for fallback to Claude when local model is unavailable.

"""

    if "Ollama — local" in content:
        print("SKIP: README.md already mentions Ollama-first")
        return

    content = content.replace(marker, ollama_block + marker)
    path.write_text(content)
    print(f"PATCHED: {path}")


def main():
    print("=" * 50)
    print("OLLAMA-FIRST CONFIG PATCH")
    print("=" * 50)
    patch_main_py()
    patch_config_py()
    patch_readme()
    print("=" * 50)
    print("Done. Review changes with: git diff")
    print(
        "Commit with: git add -A && git commit -m "
        "'feat(config): Ollama-first default, cloud opt-in'"
    )


if __name__ == "__main__":
    main()

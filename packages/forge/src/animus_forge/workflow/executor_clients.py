"""Kernel circuit breakers and Forge-owned API client factories."""

from animus_kernel.executor.executor_clients import *  # noqa: F401,F403

_claude_client = None
_openai_client = None


def _get_claude_client():
    global _claude_client
    if _claude_client is None:
        try:
            from animus_forge.api_clients.claude_code_client import ClaudeCodeClient

            _claude_client = ClaudeCodeClient()
        except Exception:
            _claude_client = False
    return _claude_client if _claude_client else None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        try:
            from animus_forge.api_clients.openai_client import OpenAIClient

            _openai_client = OpenAIClient()
        except Exception:
            _openai_client = False
    return _openai_client if _openai_client else None

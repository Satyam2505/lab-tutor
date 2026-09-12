"""Swappable LLM backends.

Shared infrastructure rather than a role-owned package: `rag/` uses it to
phrase diagnoses and `summaries/` uses it for transcript sanity checks and
trajectory summaries. Nothing in `tier1_compute/` may import it.

Two backends, selected by `LABTUTOR_LLM_BACKEND`:

* ``hosted`` -- any OpenAI-compatible chat-completions endpoint. The
  provider is a URL in the environment, never a hardcoded name, so
  Cerebras/Groq/OpenAI/Together are all the same code path. This is what
  the pilot runs on.
* ``ollama`` -- a local Ollama server. Development and offline testing
  only; see README "Inference backends" for why it is not the pilot
  target.
"""

from backend.llm.client import (
    LLMBackend,
    LLMUnavailable,
    get_backend,
    reset_backend_cache,
)

__all__ = ["LLMBackend", "LLMUnavailable", "get_backend", "reset_backend_cache"]

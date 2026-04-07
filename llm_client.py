"""
LLM client factory for the Knowledge Graph pipeline.

Supports two backends:

  anthropic  — Anthropic Claude API (default)
               Requires: ANTHROPIC_API_KEY env var

  external   — OpenAI-compatible API (AcademicCloud)
               Requires: EXTERNAL_API_TOKEN env var
               Available models: openai-gpt-oss-120b, qwen3-235b-a22b, glm-4.7

Select backend via the LLM_BACKEND environment variable:

    LLM_BACKEND=anthropic  python llm_processor.py ...   # default
    LLM_BACKEND=external   python llm_processor.py ...

The returned client presents the same interface regardless of backend:

    client.messages.create(
        model=..., max_tokens=..., system=..., messages=[...], temperature=...
    )
    # → response.content[0].text  (always)

This means no other module needs to change when switching backends.
"""

import logging
import os
import sys
from typing import Any, List, Dict

from config import (
    LLM_BACKEND,
    EXTERNAL_API_URL,
    EXTERNAL_API_MODELS,
    EXTERNAL_DEFAULT_MODEL,
    ANTHROPIC_DEFAULT_MODEL,
    DEFAULT_MODEL,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unified response wrapper
# ---------------------------------------------------------------------------

class _TextContent:
    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


class UnifiedResponse:
    """
    Wraps either an Anthropic or OpenAI response to expose
    ``response.content[0].text`` uniformly.
    """

    def __init__(self, text: str) -> None:
        self.content = [_TextContent(text)]


# ---------------------------------------------------------------------------
# Unified messages interface
# ---------------------------------------------------------------------------

class _UnifiedMessages:
    """
    Presents ``create(**kwargs)`` matching Anthropic's ``client.messages.create``
    signature, translating to the correct underlying call.
    """

    def __init__(self, backend: str, raw_client: Any) -> None:
        self._backend = backend
        self._raw = raw_client

    def create(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
    ) -> UnifiedResponse:
        if self._backend == "anthropic":
            # Anthropic returns its own response object which already has
            # .content[0].text — pass it through unchanged.
            return self._raw.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                temperature=temperature,
            )

        # OpenAI-compatible: prepend system message and call chat.completions
        openai_messages = [{"role": "system", "content": system}] + messages
        response = self._raw.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=openai_messages,
            temperature=temperature,
        )
        text = response.choices[0].message.content
        return UnifiedResponse(text)


class UnifiedLLMClient:
    """
    Unified LLM client.  Use ``client.messages.create(...)`` exactly as you
    would with the Anthropic SDK; responses always expose ``.content[0].text``.
    """

    def __init__(self, backend: str, raw_client: Any) -> None:
        self._backend = backend
        self.messages = _UnifiedMessages(backend, raw_client)

    def __repr__(self) -> str:
        return f"UnifiedLLMClient(backend={self._backend!r}, model={DEFAULT_MODEL!r})"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_llm_client() -> UnifiedLLMClient:
    """
    Create and return a ``UnifiedLLMClient`` based on the ``LLM_BACKEND``
    environment variable (default: ``"anthropic"``).

    Exits with a helpful error message if required credentials are missing.
    """
    backend = LLM_BACKEND

    if backend == "anthropic":
        try:
            import anthropic
        except ImportError:
            logger.error("anthropic package not installed. Run: pip install anthropic")
            sys.exit(1)

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file or export it in your shell."
            )
            sys.exit(1)

        raw = anthropic.Anthropic(api_key=api_key)
        logger.info("LLM backend: Anthropic  |  model: %s", DEFAULT_MODEL)
        return UnifiedLLMClient("anthropic", raw)

    if backend == "external":
        try:
            from openai import OpenAI
        except ImportError:
            logger.error("openai package not installed. Run: pip install openai")
            sys.exit(1)

        api_key = os.environ.get("EXTERNAL_API_TOKEN")
        if not api_key:
            logger.error(
                "EXTERNAL_API_TOKEN is not set. "
                "Add it to your .env file or export it in your shell."
            )
            sys.exit(1)

        if DEFAULT_MODEL not in EXTERNAL_API_MODELS:
            logger.warning(
                "KG_MODEL=%r is not in the known external model list %s. "
                "Proceeding anyway — check the model name if you get errors.",
                DEFAULT_MODEL,
                EXTERNAL_API_MODELS,
            )

        raw = OpenAI(base_url=EXTERNAL_API_URL, api_key=api_key)
        logger.info(
            "LLM backend: external (%s)  |  model: %s", EXTERNAL_API_URL, DEFAULT_MODEL
        )
        return UnifiedLLMClient("external", raw)

    logger.error(
        "Unknown LLM_BACKEND=%r. Valid values: 'anthropic', 'external'.", backend
    )
    sys.exit(1)

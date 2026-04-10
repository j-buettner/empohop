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
import time
from typing import Any, List, Dict, Optional

from config import (
    EXTERNAL_API_URL,
    EXTERNAL_API_MODELS,
    EXTERNAL_DEFAULT_MODEL,
    ANTHROPIC_DEFAULT_MODEL,
    DEFAULT_MODEL,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limit monitor (attached to the httpx client via response hooks)
# ---------------------------------------------------------------------------

class RateLimitMonitor:
    """
    Captures rate-limit headers from every httpx response and exposes a
    ``wait_if_needed()`` method that sleeps when remaining capacity is low.

    On the first response the monitor logs all x-ratelimit-* headers so we
    can see exactly what the API returns and tune thresholds accordingly.
    """

    # Pause when fewer than this many requests remain in the current window.
    LOW_WATERMARK = 3

    def __init__(self) -> None:
        self.remaining: Optional[int] = None
        self.reset_after_seconds: Optional[float] = None
        self._first_response = True

    # httpx event hook — called after every response
    def on_response(self, response) -> None:
        headers = response.headers

        if self._first_response:
            rl_headers = {k: v for k, v in headers.items() if "ratelimit" in k.lower() or "retry" in k.lower()}
            if rl_headers:
                logger.info("Rate-limit headers from API: %s", rl_headers)
            else:
                logger.info("No rate-limit headers detected in API response.")
            self._first_response = False

        # Try common header name variants
        remaining_str = (
            headers.get("x-ratelimit-remaining-requests")
            or headers.get("x-ratelimit-remaining")
            or headers.get("ratelimit-remaining")
        )
        reset_str = (
            headers.get("x-ratelimit-reset-requests")
            or headers.get("x-ratelimit-reset")
            or headers.get("ratelimit-reset")
            or headers.get("retry-after")
        )

        # Prefer the per-minute counter — it is the tightest limit
        remaining_minute = headers.get("x-ratelimit-remaining-minute")
        if remaining_minute is not None:
            try:
                self.remaining = int(remaining_minute)
            except ValueError:
                pass
        elif remaining_str is not None:
            try:
                self.remaining = int(remaining_str)
            except ValueError:
                pass

        if reset_str is not None:
            self.reset_after_seconds = self._parse_reset(reset_str)

    def wait_if_needed(self) -> None:
        """Call before each API request — sleeps if remaining capacity is low."""
        if self.remaining is None:
            return
        if self.remaining <= self.LOW_WATERMARK:
            wait = self.reset_after_seconds if self.reset_after_seconds else 60.0
            logger.warning(
                "Rate limit low (remaining=%d). Pausing %.1fs before next call.",
                self.remaining, wait,
            )
            time.sleep(wait)
            self.remaining = None
            self.reset_after_seconds = None

    @staticmethod
    def _parse_reset(value: str) -> float:
        """Parse reset header — may be seconds (int/float) or ISO 8601 duration like '1s'."""
        value = value.strip()
        # ISO 8601 duration e.g. "500ms", "1s", "2m30s"
        import re
        m = re.match(r"(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?(?:(\d+)ms)?$", value, re.IGNORECASE)
        if m and any(m.groups()):
            minutes = float(m.group(1) or 0)
            seconds = float(m.group(2) or 0)
            millis  = float(m.group(3) or 0)
            return minutes * 60 + seconds + millis / 1000
        try:
            return float(value)
        except ValueError:
            return 60.0


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

    def __init__(self, backend: str, raw_client: Any, rate_monitor: RateLimitMonitor) -> None:
        self._backend = backend
        self._raw = raw_client
        self._monitor = rate_monitor

    def create(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
    ) -> UnifiedResponse:
        self._monitor.wait_if_needed()

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
        text = response.choices[0].message.content or ""
        # Strip <think>...</think> chain-of-thought blocks emitted by qwen3 and
        # similar reasoning models before the actual response content.
        import re as _re
        text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()
        return UnifiedResponse(text)


class UnifiedLLMClient:
    """
    Unified LLM client.  Use ``client.messages.create(...)`` exactly as you
    would with the Anthropic SDK; responses always expose ``.content[0].text``.

    Attributes:
        model        — the model name that will be used for API calls
        backend      — "anthropic" or "external"
        rate_monitor — RateLimitMonitor (call .wait_if_needed() before each request)
    """

    def __init__(
        self,
        backend: str,
        raw_client: Any,
        model: str,
        rate_monitor: Optional[RateLimitMonitor] = None,
    ) -> None:
        self._backend = backend
        self.model = model
        self.rate_monitor = rate_monitor or RateLimitMonitor()
        self.messages = _UnifiedMessages(backend, raw_client, self.rate_monitor)

    def __repr__(self) -> str:
        return f"UnifiedLLMClient(backend={self._backend!r}, model={self.model!r})"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_llm_client(backend: str = None, model: str = None) -> UnifiedLLMClient:
    """
    Create and return a ``UnifiedLLMClient``.

    Args:
        backend: ``"anthropic"`` or ``"external"``.  Falls back to the
                 ``LLM_BACKEND`` environment variable, then ``"anthropic"``.
        model:   Model name to use.  Falls back to the ``KG_MODEL`` environment
                 variable, then the per-backend default.

    Exits with a clear error message if required credentials are missing.
    """
    # Resolve backend
    if backend is None:
        backend = os.environ.get("LLM_BACKEND", "anthropic").lower()

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

        resolved_model = model or os.environ.get("KG_MODEL", ANTHROPIC_DEFAULT_MODEL)
        raw = anthropic.Anthropic(api_key=api_key)
        logger.info("LLM backend: anthropic  |  model: %s", resolved_model)
        return UnifiedLLMClient("anthropic", raw, resolved_model)

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

        resolved_model = model or os.environ.get("KG_MODEL", EXTERNAL_DEFAULT_MODEL)
        if resolved_model not in EXTERNAL_API_MODELS:
            logger.warning(
                "model=%r is not in the known external model list %s. "
                "Proceeding anyway — check the model name if you get errors.",
                resolved_model,
                EXTERNAL_API_MODELS,
            )

        import httpx
        monitor = RateLimitMonitor()
        http_client = httpx.Client(event_hooks={"response": [monitor.on_response]})
        raw = OpenAI(base_url=EXTERNAL_API_URL, api_key=api_key, http_client=http_client)
        logger.info("LLM backend: external (%s)  |  model: %s", EXTERNAL_API_URL, resolved_model)
        return UnifiedLLMClient("external", raw, resolved_model, monitor)

    logger.error(
        "Unknown backend=%r. Valid values: 'anthropic', 'external'.", backend
    )
    sys.exit(1)

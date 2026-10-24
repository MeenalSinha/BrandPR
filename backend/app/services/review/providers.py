"""Model-provider abstraction. The review engine depends only on `LLMProvider.complete`.

A provider returns raw text. Parsing and validation of that text happens in ai.py, so every provider
(real or fake) goes through the same checks. Provider errors never contain the API key.
"""
import logging
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger("brandpr.review.provider")


class ProviderError(Exception):
    code = "provider_error"


class ProviderUnavailable(ProviderError):
    """The model service could not be reached or rejected the request."""

    code = "provider_unavailable"


class ProviderInvalidOutput(ProviderError):
    """The model answered, but not in the structure the backend requires."""

    code = "provider_invalid_output"


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, *, system: str, user: str) -> str: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.model = settings.llm_model
        self._key = settings.llm_api_key
        self._url = settings.llm_base_url.rstrip("/") + "/v1/messages"
        self._max_tokens = settings.llm_max_output_tokens
        self._client = client or httpx.Client(timeout=settings.llm_timeout_seconds)

    def complete(self, *, system: str, user: str) -> str:
        try:
            response = self._client.post(
                self._url,
                headers={"x-api-key": self._key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": self.model, "max_tokens": self._max_tokens, "system": system, "messages": [{"role": "user", "content": user}]},
            )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable("The AI provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("The AI provider could not be reached.") from exc
        if response.status_code >= 400:
            logger.warning("Provider returned HTTP %s", response.status_code)
            raise ProviderUnavailable(f"The AI provider rejected the request (HTTP {response.status_code}).")
        try:
            body = response.json()
            return "".join(b.get("text", "") for b in body["content"] if b.get("type") == "text")
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderInvalidOutput("The AI provider returned an unreadable response.") from exc


def build_provider(settings: Settings | None = None) -> LLMProvider | None:
    """None means no credentials are configured: the engine then runs in clearly labelled limited mode."""
    settings = settings or get_settings()
    if not settings.llm_api_key.strip():
        return None
    return AnthropicProvider(settings)

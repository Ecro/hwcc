"""LLM provider abstraction for benchmarking."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from hwcc.exceptions import BenchmarkError

__all__ = [
    "AnthropicProvider",
    "BaseBenchProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "ProviderResponse",
    "create_provider",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderResponse:
    """Response from an LLM provider."""

    text: str
    tokens_used: int
    latency_ms: float


class BaseBenchProvider(ABC):
    """Abstract base class for benchmark LLM providers."""

    @abstractmethod
    def query(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        """Send a query to the LLM and return the response.

        Args:
            system_prompt: System message with optional hardware context.
            user_prompt: The benchmark question.

        Returns:
            ProviderResponse with text, token count, and latency.

        Raises:
            BenchmarkError: If the API call fails.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model name being used."""


class AnthropicProvider(BaseBenchProvider):
    """Anthropic Claude API provider."""

    def __init__(self, model: str = "claude-sonnet-4-6", temperature: float = 0.0) -> None:
        try:
            import anthropic
        except ImportError as e:
            msg = "anthropic package required: pip install anthropic"
            raise BenchmarkError(msg) from e

        self._client = anthropic.Anthropic()
        self._model = model
        self._temperature = temperature

    def query(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        t0 = time.monotonic()
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                temperature=self._temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as e:
            msg = f"Anthropic API error: {e}"
            raise BenchmarkError(msg) from e

        latency = (time.monotonic() - t0) * 1000
        text = response.content[0].text if response.content else ""
        tokens = 0
        if response.usage:
            tokens = response.usage.input_tokens + response.usage.output_tokens

        return ProviderResponse(text=text, tokens_used=tokens, latency_ms=latency)

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model


class OpenAIProvider(BaseBenchProvider):
    """OpenAI API provider."""

    def __init__(self, model: str = "gpt-4o", temperature: float = 0.0) -> None:
        try:
            import openai
        except ImportError as e:
            msg = "openai package required: pip install openai"
            raise BenchmarkError(msg) from e

        self._client = openai.OpenAI()
        self._model = model
        self._temperature = temperature

    def query(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        t0 = time.monotonic()
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=256,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as e:
            msg = f"OpenAI API error: {e}"
            raise BenchmarkError(msg) from e

        latency = (time.monotonic() - t0) * 1000
        text = ""
        if response.choices:
            text = response.choices[0].message.content or ""
        tokens = 0
        if response.usage:
            tokens = (response.usage.prompt_tokens or 0) + (response.usage.completion_tokens or 0)

        return ProviderResponse(text=text, tokens_used=tokens, latency_ms=latency)

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model


class OllamaProvider(BaseBenchProvider):
    """Ollama local LLM provider."""

    def __init__(
        self,
        model: str = "llama3.1",
        temperature: float = 0.0,
        host: str = "http://localhost:11434",
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._host = host.rstrip("/")

    def query(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        try:
            import httpx
        except ImportError as e:
            msg = "httpx package required: pip install httpx"
            raise BenchmarkError(msg) from e

        t0 = time.monotonic()
        try:
            resp = httpx.post(
                f"{self._host}/api/chat",
                json={
                    "model": self._model,
                    "stream": False,
                    "options": {"temperature": self._temperature},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=120.0,
            )
            resp.raise_for_status()
        except Exception as e:
            msg = f"Ollama API error: {e}"
            raise BenchmarkError(msg) from e

        latency = (time.monotonic() - t0) * 1000
        data = resp.json()
        text = data.get("message", {}).get("content", "")
        tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)

        return ProviderResponse(text=text, tokens_used=tokens, latency_ms=latency)

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model


def create_provider(
    provider_name: str,
    model: str = "",
    temperature: float = 0.0,
    **kwargs: str,
) -> BaseBenchProvider:
    """Factory function to create an LLM provider.

    Args:
        provider_name: "anthropic", "openai", or "ollama".
        model: Model name (uses provider default if empty).
        temperature: Sampling temperature.
        **kwargs: Additional provider-specific arguments.

    Returns:
        Configured provider instance.

    Raises:
        BenchmarkError: If the provider name is unknown.
    """
    if provider_name == "anthropic":
        return AnthropicProvider(
            model=model or "claude-sonnet-4-6",
            temperature=temperature,
        )
    if provider_name == "openai":
        return OpenAIProvider(
            model=model or "gpt-4o",
            temperature=temperature,
        )
    if provider_name == "ollama":
        return OllamaProvider(
            model=model or "llama3.1",
            temperature=temperature,
            host=kwargs.get("host", "http://localhost:11434"),
        )

    msg = f"Unknown provider: {provider_name!r}. Supported: anthropic, openai, ollama"
    raise BenchmarkError(msg)

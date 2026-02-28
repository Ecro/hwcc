"""OpenAI-compatible embedding provider.

Works with any server implementing the OpenAI /v1/embeddings API:
OpenAI, LiteLLM proxy, vLLM, Ollama (OpenAI-compat mode), etc.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from hwcc.embed.base import BaseEmbedder
from hwcc.exceptions import EmbeddingError
from hwcc.types import EmbeddedChunk

if TYPE_CHECKING:
    from hwcc.config import HwccConfig
    from hwcc.types import Chunk

__all__ = ["OpenAICompatEmbedder"]

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAICompatEmbedder(BaseEmbedder):
    """Embedding provider using any OpenAI-compatible /v1/embeddings endpoint.

    Supports both cloud APIs (with API key) and local servers (without API key).

    Config fields used::

        [embedding]
        model = "text-embedding-3-small"
        provider = "openai"
        api_key_env = "OPENAI_API_KEY"   # env var name; empty = no auth
        base_url = ""                     # empty = https://api.openai.com/v1
        batch_size = 64
    """

    _DEFAULT_TIMEOUT = 120  # seconds

    def __init__(self, config: HwccConfig) -> None:
        self._model = config.embedding.model
        self._base_url = (config.embedding.base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._batch_size = config.embedding.batch_size
        self._dimension: int | None = None

        if self._batch_size < 1:
            raise EmbeddingError(f"batch_size must be >= 1, got {self._batch_size}")

        # Resolve API key from environment variable
        self._api_key: str | None = None
        if config.embedding.api_key_env:
            self._api_key = os.environ.get(config.embedding.api_key_env)
            if not self._api_key:
                logger.warning(
                    "API key env var %s is not set; requests may fail",
                    config.embedding.api_key_env,
                )

    def embed_chunks(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        """Generate embeddings for a batch of chunks.

        Args:
            chunks: Chunks to embed.

        Returns:
            List of EmbeddedChunk with vectors attached.

        Raises:
            EmbeddingError: If the API returns an error.
        """
        if not chunks:
            return []

        all_results: list[EmbeddedChunk] = []

        for batch_start in range(0, len(chunks), self._batch_size):
            batch = chunks[batch_start : batch_start + self._batch_size]
            texts = [c.content for c in batch]
            vectors = self._call_embeddings(texts)

            for chunk, vec in zip(batch, vectors, strict=True):
                all_results.append(EmbeddedChunk(chunk=chunk, embedding=tuple(vec)))

        logger.info(
            "Embedded %d chunks via OpenAI-compatible API (%s)", len(all_results), self._model
        )
        return all_results

    def embed_query(self, text: str) -> list[float]:
        """Generate an embedding for a search query.

        Args:
            text: Query text.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            EmbeddingError: If embedding generation fails.
        """
        vectors = self._call_embeddings([text])
        return vectors[0]

    @property
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors.

        Warning:
            First access makes a network call to probe the model.
            Use after at least one ``embed_chunks()`` or ``embed_query()`` call
            to avoid an extra API request.
        """
        if self._dimension is None:
            vec = self.embed_query("dimension probe")
            self._dimension = len(vec)
        return self._dimension

    def _call_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Call the /v1/embeddings endpoint.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors, ordered by input index.

        Raises:
            EmbeddingError: On connection or API errors.
        """
        url = f"{self._base_url}/embeddings"
        payload = json.dumps({"model": self._model, "input": texts}).encode("utf-8")

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = Request(url, data=payload, headers=headers)

        try:
            with urlopen(req, timeout=self._DEFAULT_TIMEOUT) as resp:
                body = resp.read()
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise EmbeddingError(f"Embedding API returned invalid JSON from {url}") from e
        except (ConnectionError, URLError) as e:
            raise EmbeddingError(
                f"Embedding API not reachable at {self._base_url}. Error: {e}"
            ) from e
        except HTTPError as e:
            raise EmbeddingError(f"Embedding API error (HTTP {e.code}): {e.reason}") from e

        # Sort by index to ensure correct order (OpenAI spec includes "index" per item)
        raw_items = data.get("data", [])
        if raw_items and all("index" in item for item in raw_items):
            raw_items = sorted(raw_items, key=lambda x: x["index"])

        try:
            embeddings: list[list[float]] = [item["embedding"] for item in raw_items]
        except (KeyError, TypeError) as e:
            raise EmbeddingError(
                f"Unexpected response format from {url}: missing 'embedding' field"
            ) from e

        if len(embeddings) != len(texts):
            raise EmbeddingError(
                f"API returned {len(embeddings)} embeddings for {len(texts)} inputs"
            )

        # Track dimension from first result
        if embeddings and self._dimension is None:
            self._dimension = len(embeddings[0])

        return embeddings

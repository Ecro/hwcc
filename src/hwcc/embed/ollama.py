"""Ollama embedding provider using the /api/embed endpoint.

Default provider for hwcc — uses locally running Ollama with nomic-embed-text.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from hwcc.embed.base import BaseEmbedder
from hwcc.exceptions import EmbeddingError
from hwcc.types import EmbeddedChunk

if TYPE_CHECKING:
    from hwcc.config import HwccConfig
    from hwcc.types import Chunk

__all__ = ["OllamaEmbedder"]

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaEmbedder(BaseEmbedder):
    """Embedding provider using a local Ollama instance.

    Calls the ``/api/embed`` endpoint with batch support.
    Default model is ``nomic-embed-text`` (768 dimensions).

    Config fields used::

        [embedding]
        model = "nomic-embed-text"
        provider = "ollama"
        base_url = ""           # empty = http://localhost:11434
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

    def embed_chunks(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        """Generate embeddings for a batch of chunks via Ollama.

        Splits into batches of ``batch_size`` to avoid overwhelming the server.

        Args:
            chunks: Chunks to embed.

        Returns:
            List of EmbeddedChunk with vectors attached.

        Raises:
            EmbeddingError: If Ollama is not reachable or returns an error.
        """
        if not chunks:
            return []

        all_results: list[EmbeddedChunk] = []

        for batch_start in range(0, len(chunks), self._batch_size):
            batch = chunks[batch_start : batch_start + self._batch_size]
            texts = [c.content for c in batch]
            vectors = self._call_embed(texts)

            for chunk, vec in zip(batch, vectors, strict=True):
                all_results.append(EmbeddedChunk(chunk=chunk, embedding=tuple(vec)))

        logger.info("Embedded %d chunks via Ollama (%s)", len(all_results), self._model)
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
        vectors = self._call_embed([text])
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

    def _call_embed(self, texts: list[str]) -> list[list[float]]:
        """Call the Ollama /api/embed endpoint.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors.

        Raises:
            EmbeddingError: On connection or API errors.
        """
        url = f"{self._base_url}/api/embed"
        payload = json.dumps({"model": self._model, "input": texts}).encode("utf-8")
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})

        try:
            with urlopen(req, timeout=self._DEFAULT_TIMEOUT) as resp:
                body = resp.read()
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise EmbeddingError(f"Ollama returned invalid JSON from {url}") from e
        except (ConnectionError, URLError) as e:
            raise EmbeddingError(
                f"Ollama not reachable at {self._base_url}. Is Ollama running? Error: {e}"
            ) from e
        except HTTPError as e:
            raise EmbeddingError(f"Ollama API error (HTTP {e.code}): {e.reason}") from e

        embeddings: list[list[float]] = data.get("embeddings", [])
        if len(embeddings) != len(texts):
            raise EmbeddingError(
                f"Ollama returned {len(embeddings)} embeddings for {len(texts)} inputs"
            )

        # Track dimension from first result
        if embeddings and self._dimension is None:
            self._dimension = len(embeddings[0])

        return embeddings

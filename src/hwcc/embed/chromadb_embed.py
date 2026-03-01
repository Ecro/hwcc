"""ChromaDB built-in embedding provider using ONNX runtime.

Zero-dependency embedding (ChromaDB is already a project dependency).
Uses the all-MiniLM-L6-v2 model via ONNX — no GPU, no server, no API key.
Model is auto-downloaded on first use (~80MB).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from hwcc.embed.base import BaseEmbedder
from hwcc.exceptions import EmbeddingError
from hwcc.types import EmbeddedChunk

if TYPE_CHECKING:
    from hwcc.config import HwccConfig
    from hwcc.types import Chunk

__all__ = ["ChromaDBEmbedder"]

logger = logging.getLogger(__name__)


class ChromaDBEmbedder(BaseEmbedder):
    """Embedding provider using ChromaDB's built-in ONNX embedding function.

    Uses ``all-MiniLM-L6-v2`` (384 dimensions) via ONNX runtime.
    No external server or API key required — runs entirely locally.

    This is the default embedding provider for hwcc.

    Config fields used::

        [embedding]
        provider = "chromadb"
        model = "all-MiniLM-L6-v2"
    """

    _FIXED_MODEL = "all-MiniLM-L6-v2"

    def __init__(self, config: HwccConfig) -> None:
        if config.embedding.model and config.embedding.model != self._FIXED_MODEL:
            logger.warning(
                "ChromaDB provider only supports %s, ignoring model=%r",
                self._FIXED_MODEL,
                config.embedding.model,
            )

        try:
            self._ef = DefaultEmbeddingFunction()
        except Exception as e:
            raise EmbeddingError(f"Failed to initialize ChromaDB embedding function: {e}") from e

        self._dimension: int | None = None
        logger.info("ChromaDBEmbedder initialized (ONNX %s)", self._FIXED_MODEL)

    def embed_chunks(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        """Generate embeddings for a batch of chunks.

        Args:
            chunks: Chunks to embed.

        Returns:
            List of EmbeddedChunk with vectors attached.

        Raises:
            EmbeddingError: If embedding generation fails.
        """
        if not chunks:
            return []

        texts = [c.content for c in chunks]

        try:
            vectors = self._ef(texts)
        except Exception as e:
            raise EmbeddingError(f"ChromaDB embedding failed: {e}") from e

        if len(vectors) != len(texts):
            raise EmbeddingError(
                f"ChromaDB returned {len(vectors)} embeddings for {len(texts)} inputs"
            )

        results: list[EmbeddedChunk] = []
        for chunk, vec in zip(chunks, vectors, strict=True):
            results.append(EmbeddedChunk(chunk=chunk, embedding=tuple(float(v) for v in vec)))

        if results and self._dimension is None:
            self._dimension = len(results[0].embedding)

        logger.info("Embedded %d chunks via ChromaDB (ONNX)", len(results))
        return results

    def embed_query(self, text: str) -> list[float]:
        """Generate an embedding for a search query.

        Args:
            text: Query text.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            EmbeddingError: If embedding generation fails.
        """
        try:
            vectors = self._ef([text])
        except Exception as e:
            raise EmbeddingError(f"ChromaDB query embedding failed: {e}") from e

        if not vectors or len(vectors) != 1:
            raise EmbeddingError("ChromaDB returned unexpected result for single query")

        vec = list(vectors[0])

        if self._dimension is None:
            self._dimension = len(vec)

        return vec

    @property
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors (384 for MiniLM)."""
        if self._dimension is None:
            vec = self.embed_query("dimension probe")
            self._dimension = len(vec)
        return self._dimension

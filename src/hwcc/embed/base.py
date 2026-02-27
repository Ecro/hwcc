"""Abstract base class for embedding providers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hwcc.types import Chunk, EmbeddedChunk

__all__ = ["BaseEmbedder"]

logger = logging.getLogger(__name__)


class BaseEmbedder(ABC):
    """Base class for all embedding providers.

    Subclasses generate vector embeddings for chunks and queries.
    """

    @abstractmethod
    def embed_chunks(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        """Generate embeddings for a batch of chunks.

        Args:
            chunks: Chunks to embed.

        Returns:
            List of EmbeddedChunk with vectors attached.

        Raises:
            EmbeddingError: If embedding generation fails.
        """

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Generate an embedding for a search query.

        Args:
            text: Query text.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            EmbeddingError: If embedding generation fails.
        """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors."""

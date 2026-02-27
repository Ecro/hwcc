"""Abstract base class for vector stores."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hwcc.types import EmbeddedChunk, SearchResult

__all__ = ["BaseStore"]

logger = logging.getLogger(__name__)


class BaseStore(ABC):
    """Base class for all vector stores.

    Subclasses persist embedded chunks and support similarity search.
    """

    @abstractmethod
    def add(self, chunks: list[EmbeddedChunk], doc_id: str) -> int:
        """Add embedded chunks to the store.

        Args:
            chunks: Embedded chunks to store.
            doc_id: Document ID these chunks belong to.

        Returns:
            Number of chunks added.

        Raises:
            StoreError: If storage fails.
        """

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        where: dict[str, str] | None = None,
    ) -> list[SearchResult]:
        """Search for similar chunks by embedding.

        Args:
            query_embedding: Query vector.
            k: Number of results to return.
            where: Optional metadata filters.

        Returns:
            List of search results sorted by relevance.

        Raises:
            StoreError: If search fails.
        """

    @abstractmethod
    def delete(self, doc_id: str) -> int:
        """Delete all chunks for a document.

        Args:
            doc_id: Document ID to remove.

        Returns:
            Number of chunks deleted.

        Raises:
            StoreError: If deletion fails.
        """

    @abstractmethod
    def count(self) -> int:
        """Return the total number of chunks in the store."""

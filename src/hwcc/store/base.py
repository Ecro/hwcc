"""Abstract base class for vector stores."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hwcc.types import Chunk, ChunkMetadata, EmbeddedChunk, SearchResult

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
    def get_chunk_metadata(
        self,
        where: dict[str, str] | None = None,
    ) -> list[ChunkMetadata]:
        """Get metadata for all chunks matching filters (no embedding needed).

        Unlike ``search()``, this method does not require a query embedding.
        It returns metadata for all matching chunks, useful for the compile
        stage to discover peripheral names, document types, etc.

        Args:
            where: Optional metadata filters (e.g., ``{"doc_type": "svd"}``).

        Returns:
            List of ChunkMetadata for matching chunks.

        Raises:
            StoreError: If the query fails.
        """

    @abstractmethod
    def get_chunks(
        self,
        where: dict[str, str] | None = None,
    ) -> list[Chunk]:
        """Get chunks with content matching filters (no embedding needed).

        Unlike ``search()``, returns chunks by metadata filter without
        requiring a query embedding. Useful for the compile stage to
        retrieve document content by type, peripheral, etc.

        Args:
            where: Optional metadata filters (e.g., ``{"doc_type": "svd"}``).

        Returns:
            List of Chunk objects with content and metadata.

        Raises:
            StoreError: If the query fails.
        """

    @abstractmethod
    def count(self) -> int:
        """Return the total number of chunks in the store."""

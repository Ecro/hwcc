"""Search engine for querying indexed hardware documentation.

Wraps the embedder and vector store to provide a high-level search API.
Used by the ``hwcc search`` CLI command and (future) MCP server.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hwcc.embed.base import BaseEmbedder
    from hwcc.store.base import BaseStore
    from hwcc.types import SearchResult

__all__ = ["SearchEngine"]

logger = logging.getLogger(__name__)


class SearchEngine:
    """High-level search over indexed hardware documentation.

    Composes an embedder (for query vectorization) with a vector store
    (for similarity search).  Filter parameters are translated to
    ChromaDB ``where`` clauses.

    Usage::

        engine = SearchEngine(embedder=embedder, store=store)
        results = engine.search("GPIO configuration", k=5, chip="STM32F407")
    """

    def __init__(self, embedder: BaseEmbedder, store: BaseStore) -> None:
        self._embedder = embedder
        self._store = store

    def search(
        self,
        query: str,
        k: int = 5,
        chip: str = "",
        doc_type: str = "",
        peripheral: str = "",
    ) -> tuple[list[SearchResult], float]:
        """Embed a query and search the vector store.

        Args:
            query: Natural language search query.
            k: Maximum number of results to return.
            chip: Filter by chip name (exact match).
            doc_type: Filter by document type (exact match).
            peripheral: Filter by peripheral name (exact match).

        Returns:
            Tuple of (search results sorted by relevance, elapsed seconds).

        Raises:
            EmbeddingError: If query embedding fails.
            StoreError: If the vector search fails.
        """
        start = time.monotonic()

        query_embedding = self._embedder.embed_query(query)
        where = self._build_where(chip=chip, doc_type=doc_type, peripheral=peripheral)

        results = self._store.search(query_embedding, k=k, where=where)

        elapsed = time.monotonic() - start
        logger.info(
            "Search for %r returned %d results in %.2fs",
            query,
            len(results),
            elapsed,
        )
        return results, elapsed

    @staticmethod
    def _build_where(
        chip: str = "",
        doc_type: str = "",
        peripheral: str = "",
    ) -> dict[str, Any] | None:
        """Build a ChromaDB ``where`` clause from filter parameters.

        Args:
            chip: Filter by chip name.
            doc_type: Filter by document type.
            peripheral: Filter by peripheral name.

        Returns:
            A ChromaDB where dict, or None if no filters specified.
        """
        filters: list[dict[str, str]] = []
        if chip:
            filters.append({"chip": chip})
        if doc_type:
            filters.append({"doc_type": doc_type})
        if peripheral:
            filters.append({"peripheral": peripheral})

        if not filters:
            return None
        if len(filters) == 1:
            return filters[0]
        return {"$and": filters}

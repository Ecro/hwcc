"""ChromaDB vector store using PersistentClient.

Stores embedded chunks with metadata for similarity search.
Uses file-based persistence — no server required.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import chromadb

from hwcc.exceptions import StoreError
from hwcc.store.base import BaseStore
from hwcc.types import Chunk, ChunkMetadata, EmbeddedChunk, SearchResult

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__ = ["ChromaStore"]

logger = logging.getLogger(__name__)


class ChromaStore(BaseStore):
    """Vector store backed by ChromaDB with file-based persistence.

    Uses ``chromadb.PersistentClient`` so no external server is needed.
    All data lives in the ``persist_path`` directory.

    Usage::

        store = ChromaStore(persist_path=project_root / ".rag" / "chroma")
        store.add(embedded_chunks, doc_id="board_svd")
        results = store.search(query_embedding, k=5, where={"chip": "STM32F407"})
    """

    def __init__(self, persist_path: Path, collection_name: str = "hwcc") -> None:
        self._persist_path = persist_path
        self._collection_name = collection_name

        try:
            self._client = chromadb.PersistentClient(path=str(persist_path))
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
            )
        except Exception as e:
            raise StoreError(f"Failed to initialize ChromaDB at {persist_path}: {e}") from e

        logger.info(
            "ChromaDB store initialized at %s (collection=%s)", persist_path, collection_name
        )

    def add(self, chunks: list[EmbeddedChunk], doc_id: str) -> int:
        """Add embedded chunks to ChromaDB.

        Args:
            chunks: Embedded chunks to store.
            doc_id: Document ID these chunks belong to.

        Returns:
            Number of chunks added.

        Raises:
            StoreError: If storage fails.
        """
        if not chunks:
            return 0

        ids = [c.chunk.chunk_id for c in chunks]
        embeddings = [list(c.embedding) for c in chunks]
        documents = [c.chunk.content for c in chunks]
        metadatas = [
            {
                "doc_id": c.chunk.metadata.doc_id,
                "doc_type": c.chunk.metadata.doc_type,
                "chip": c.chunk.metadata.chip,
                "section_path": c.chunk.metadata.section_path,
                "page": c.chunk.metadata.page,
                "chunk_level": c.chunk.metadata.chunk_level,
                "peripheral": c.chunk.metadata.peripheral,
                "content_type": c.chunk.metadata.content_type,
                "token_count": c.chunk.token_count,
            }
            for c in chunks
        ]

        try:
            self._collection.add(
                ids=ids,
                embeddings=embeddings,  # type: ignore[arg-type]
                documents=documents,
                metadatas=metadatas,  # type: ignore[arg-type]
            )
        except Exception as e:
            raise StoreError(f"Failed to add {len(chunks)} chunks for {doc_id}: {e}") from e

        logger.info("Added %d chunks for doc_id=%s", len(chunks), doc_id)
        return len(chunks)

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
            where: Optional metadata filters (e.g. ``{"chip": "STM32F407"}``).

        Returns:
            List of search results sorted by relevance.

        Raises:
            StoreError: If search fails.
        """
        total = self.count()
        if total == 0:
            return []

        # Clamp k to total collection size (ChromaDB raises if k > total count).
        # When a where filter is active, ChromaDB may return fewer than actual_k results.
        actual_k = min(k, total)

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],  # type: ignore[arg-type]
                n_results=actual_k,
                where=where,  # type: ignore[arg-type]
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            err_name = type(e).__name__
            if where is not None and "NotEnough" in err_name:
                # When k exceeds the number of documents matching the filter,
                # some ChromaDB versions raise NotEnoughElements. Fall back
                # to counting filtered matches, then re-query with correct limit.
                logger.debug("Filtered search (k=%d) failed, retrying: %s", actual_k, e)
                try:
                    matching = self._collection.get(where=where, include=[])  # type: ignore[arg-type]
                    match_count = len(matching["ids"])
                    if match_count == 0:
                        return []
                    results = self._collection.query(
                        query_embeddings=[query_embedding],  # type: ignore[arg-type]
                        n_results=min(actual_k, match_count),
                        where=where,  # type: ignore[arg-type]
                        include=["documents", "metadatas", "distances"],
                    )
                except Exception as retry_err:
                    raise StoreError(f"Search failed: {retry_err}") from retry_err
            else:
                raise StoreError(f"Search failed: {e}") from e

        # ChromaDB returns batched results — we query with one embedding
        raw_ids = results.get("ids")
        raw_docs = results.get("documents")
        raw_metas = results.get("metadatas")
        raw_dists = results.get("distances")

        if not raw_ids or not raw_docs or not raw_metas or not raw_dists:
            return []

        ids = raw_ids[0]
        documents = raw_docs[0]
        metadatas = raw_metas[0]
        distances = raw_dists[0]

        search_results: list[SearchResult] = []
        for chunk_id, doc, meta, dist in zip(ids, documents, metadatas, distances, strict=True):
            chunk_meta = self._meta_from_dict(meta)
            token_val = meta.get("token_count", 0) if meta else 0
            chunk = Chunk(
                chunk_id=chunk_id,
                content=doc or "",
                token_count=int(token_val) if token_val is not None else 0,  # type: ignore[arg-type]
                metadata=chunk_meta,
            )
            # Convert distance to similarity score (higher = more similar)
            score = 1.0 / (1.0 + dist)
            search_results.append(SearchResult(chunk=chunk, score=score, distance=dist))

        return search_results

    def delete(self, doc_id: str) -> int:
        """Delete all chunks for a document.

        Args:
            doc_id: Document ID to remove.

        Returns:
            Number of chunks deleted.

        Raises:
            StoreError: If deletion fails.
        """
        try:
            existing = self._collection.get(
                where={"doc_id": doc_id},
                include=[],
            )
            count = len(existing["ids"])

            if count == 0:
                return 0

            self._collection.delete(where={"doc_id": doc_id})
        except Exception as e:
            raise StoreError(f"Failed to delete chunks for {doc_id}: {e}") from e

        logger.info("Deleted %d chunks for doc_id=%s", count, doc_id)
        return count

    def get_chunk_metadata(
        self,
        where: dict[str, str] | None = None,
    ) -> list[ChunkMetadata]:
        """Get metadata for all chunks matching filters (no embedding needed).

        Args:
            where: Optional metadata filters (e.g., ``{"doc_type": "svd"}``).

        Returns:
            List of ChunkMetadata for matching chunks.

        Raises:
            StoreError: If the query fails.
        """
        try:
            # Returns all matching chunks. For very large stores (>100k chunks),
            # consider adding pagination or a dedicated peripheral query.
            results = self._collection.get(
                where=where,  # type: ignore[arg-type]
                include=["metadatas"],
            )
        except Exception as e:
            raise StoreError(f"Failed to get chunk metadata: {e}") from e

        raw_metas = results.get("metadatas")
        if not raw_metas:
            return []

        metadata_list: list[ChunkMetadata] = []
        for meta in raw_metas:
            if meta is None:
                continue
            metadata_list.append(self._meta_from_dict(meta))

        return metadata_list

    def get_chunks(
        self,
        where: dict[str, str] | None = None,
    ) -> list[Chunk]:
        """Get chunks with content matching filters (no embedding needed).

        Args:
            where: Optional metadata filters (e.g., ``{"doc_type": "svd"}``).

        Returns:
            List of Chunk objects with content and metadata.

        Raises:
            StoreError: If the query fails.
        """
        try:
            results = self._collection.get(
                where=where,  # type: ignore[arg-type]
                include=["documents", "metadatas"],
            )
        except Exception as e:
            raise StoreError(f"Failed to get chunks: {e}") from e

        ids = results.get("ids", [])
        documents = results.get("documents")
        metadatas = results.get("metadatas")

        chunks: list[Chunk] = []
        for chunk_id, doc, meta in zip(
            ids,
            documents or [],
            metadatas or [],
            strict=True,
        ):
            chunk_meta = self._meta_from_dict(meta)
            token_val = meta.get("token_count", 0) if meta else 0
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    content=doc or "",
                    token_count=int(token_val) if token_val is not None else 0,  # type: ignore[arg-type]
                    metadata=chunk_meta,
                )
            )

        return chunks

    def count(self) -> int:
        """Return the total number of chunks in the store."""
        try:
            return self._collection.count()
        except Exception as e:
            raise StoreError(f"Failed to count chunks: {e}") from e

    @staticmethod
    def _meta_from_dict(meta: Mapping[str, object] | None) -> ChunkMetadata:
        """Reconstruct a ChunkMetadata from a ChromaDB metadata dict."""
        if not meta:
            return ChunkMetadata(doc_id="")
        page_val = meta.get("page", 0)
        return ChunkMetadata(
            doc_id=str(meta.get("doc_id", "")),
            doc_type=str(meta.get("doc_type", "")),
            chip=str(meta.get("chip", "")),
            section_path=str(meta.get("section_path", "")),
            page=int(page_val) if page_val is not None else 0,  # type: ignore[call-overload]
            chunk_level=str(meta.get("chunk_level", "detail")),
            peripheral=str(meta.get("peripheral", "")),
            content_type=str(meta.get("content_type", "")),
        )

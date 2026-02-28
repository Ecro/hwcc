"""Tests for hwcc.store.chroma module — ChromaDB vector store."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hwcc.exceptions import StoreError
from hwcc.store.chroma import ChromaStore
from hwcc.types import Chunk, ChunkMetadata, EmbeddedChunk, SearchResult

if TYPE_CHECKING:
    from pathlib import Path


# --- Helpers ---


def _make_metadata(
    doc_id: str = "doc1",
    doc_type: str = "datasheet",
    chip: str = "STM32F407",
    section_path: str = "GPIO/Registers",
    page: int = 42,
    chunk_level: str = "detail",
    peripheral: str = "GPIOA",
    content_type: str = "register_map",
) -> ChunkMetadata:
    return ChunkMetadata(
        doc_id=doc_id,
        doc_type=doc_type,
        chip=chip,
        section_path=section_path,
        page=page,
        chunk_level=chunk_level,
        peripheral=peripheral,
        content_type=content_type,
    )


def _make_embedded_chunk(
    chunk_id: str = "c1",
    content: str = "GPIOA MODER register",
    token_count: int = 10,
    embedding: tuple[float, ...] = (0.1, 0.2, 0.3),
    **meta_kwargs: object,
) -> EmbeddedChunk:
    meta = _make_metadata(**meta_kwargs)  # type: ignore[arg-type]
    chunk = Chunk(chunk_id=chunk_id, content=content, token_count=token_count, metadata=meta)
    return EmbeddedChunk(chunk=chunk, embedding=embedding)


def _make_store(tmp_path: Path, collection_name: str = "test") -> ChromaStore:
    return ChromaStore(persist_path=tmp_path / "chroma", collection_name=collection_name)


# --- Init Tests ---


class TestChromaStoreInit:
    def test_init_creates_store(self, tmp_path: Path):
        store = _make_store(tmp_path)
        assert store.count() == 0

    def test_init_with_custom_collection_name(self, tmp_path: Path):
        store = _make_store(tmp_path, collection_name="my_project")
        assert store.count() == 0


# --- Add Tests ---


class TestChromaStoreAdd:
    def test_add_empty_returns_zero(self, tmp_path: Path):
        store = _make_store(tmp_path)
        assert store.add([], "doc1") == 0

    def test_add_stores_chunks(self, tmp_path: Path):
        store = _make_store(tmp_path)
        chunks = [
            _make_embedded_chunk(chunk_id="c1", content="chunk 1"),
            _make_embedded_chunk(chunk_id="c2", content="chunk 2"),
        ]
        count = store.add(chunks, "doc1")
        assert count == 2
        assert store.count() == 2

    def test_add_stores_documents(self, tmp_path: Path):
        store = _make_store(tmp_path)
        chunks = [_make_embedded_chunk(chunk_id="c1", content="GPIOA MODER register")]
        store.add(chunks, "doc1")

        # Search should return the stored document content
        results = store.search([0.1, 0.2, 0.3], k=1)
        assert len(results) == 1
        assert results[0].chunk.content == "GPIOA MODER register"

    def test_add_stores_metadata(self, tmp_path: Path):
        """All ChunkMetadata fields should round-trip through ChromaDB."""
        store = _make_store(tmp_path)
        chunks = [
            _make_embedded_chunk(
                chunk_id="c1",
                content="register map",
                doc_id="svd_doc",
                doc_type="svd",
                chip="STM32F407",
                section_path="GPIO/Registers",
                page=42,
                chunk_level="detail",
                peripheral="GPIOA",
                content_type="register_map",
            )
        ]
        store.add(chunks, "svd_doc")

        results = store.search([0.1, 0.2, 0.3], k=1)
        assert len(results) == 1
        meta = results[0].chunk.metadata
        assert meta.doc_id == "svd_doc"
        assert meta.doc_type == "svd"
        assert meta.chip == "STM32F407"
        assert meta.section_path == "GPIO/Registers"
        assert meta.page == 42
        assert meta.chunk_level == "detail"
        assert meta.peripheral == "GPIOA"
        assert meta.content_type == "register_map"

    def test_add_incremental(self, tmp_path: Path):
        """Adding chunks from different docs should accumulate."""
        store = _make_store(tmp_path)
        chunks1 = [_make_embedded_chunk(chunk_id="c1", doc_id="doc1")]
        chunks2 = [_make_embedded_chunk(chunk_id="c2", doc_id="doc2")]

        store.add(chunks1, "doc1")
        assert store.count() == 1

        store.add(chunks2, "doc2")
        assert store.count() == 2

    def test_add_preserves_token_count(self, tmp_path: Path):
        store = _make_store(tmp_path)
        chunks = [_make_embedded_chunk(chunk_id="c1", token_count=99)]
        store.add(chunks, "doc1")

        results = store.search([0.1, 0.2, 0.3], k=1)
        assert results[0].chunk.token_count == 99


# --- Search Tests ---


class TestChromaStoreSearch:
    def test_search_returns_results(self, tmp_path: Path):
        store = _make_store(tmp_path)
        chunks = [
            _make_embedded_chunk(chunk_id="c1", content="GPIOA MODER"),
            _make_embedded_chunk(chunk_id="c2", content="USART1 CR1"),
        ]
        store.add(chunks, "doc1")

        results = store.search([0.1, 0.2, 0.3], k=2)
        assert len(results) == 2
        assert all(isinstance(r, SearchResult) for r in results)

    def test_search_with_chip_filter(self, tmp_path: Path):
        """where={'chip': 'STM32F407'} should filter results."""
        store = _make_store(tmp_path)
        stm_chunk = _make_embedded_chunk(
            chunk_id="c1",
            content="STM32 GPIO",
            chip="STM32F407",
            embedding=(0.1, 0.2, 0.3),
        )
        ti_chunk = _make_embedded_chunk(
            chunk_id="c2",
            content="TPS65218 LDO",
            chip="TPS65218",
            embedding=(0.1, 0.2, 0.3),
        )
        store.add([stm_chunk], "stm_doc")
        store.add([ti_chunk], "ti_doc")

        results = store.search([0.1, 0.2, 0.3], k=10, where={"chip": "STM32F407"})
        assert len(results) == 1
        assert results[0].chunk.metadata.chip == "STM32F407"

    def test_search_respects_k(self, tmp_path: Path):
        store = _make_store(tmp_path)
        chunks = [_make_embedded_chunk(chunk_id=f"c{i}", content=f"chunk {i}") for i in range(5)]
        store.add(chunks, "doc1")

        results = store.search([0.1, 0.2, 0.3], k=2)
        assert len(results) == 2

    def test_search_empty_collection(self, tmp_path: Path):
        store = _make_store(tmp_path)
        results = store.search([0.1, 0.2, 0.3], k=5)
        assert results == []

    def test_search_with_filter_no_matches(self, tmp_path: Path):
        """A filter that matches nothing should return an empty list."""
        store = _make_store(tmp_path)
        chunks = [_make_embedded_chunk(chunk_id="c1", chip="STM32F407")]
        store.add(chunks, "doc1")

        results = store.search([0.1, 0.2, 0.3], k=5, where={"chip": "NRF52840"})
        assert results == []

    def test_search_result_has_score_and_distance(self, tmp_path: Path):
        store = _make_store(tmp_path)
        chunks = [_make_embedded_chunk(chunk_id="c1")]
        store.add(chunks, "doc1")

        results = store.search([0.1, 0.2, 0.3], k=1)
        assert len(results) == 1
        assert results[0].score > 0
        assert results[0].distance >= 0

    def test_search_reconstructs_chunk_metadata(self, tmp_path: Path):
        """SearchResult should contain a fully-formed Chunk with metadata."""
        store = _make_store(tmp_path)
        chunks = [
            _make_embedded_chunk(
                chunk_id="c1",
                content="register data",
                token_count=25,
                doc_id="doc1",
                chip="STM32F407",
            )
        ]
        store.add(chunks, "doc1")

        results = store.search([0.1, 0.2, 0.3], k=1)
        result = results[0]

        assert isinstance(result.chunk, Chunk)
        assert result.chunk.chunk_id == "c1"
        assert result.chunk.content == "register data"
        assert result.chunk.token_count == 25
        assert isinstance(result.chunk.metadata, ChunkMetadata)
        assert result.chunk.metadata.doc_id == "doc1"
        assert result.chunk.metadata.chip == "STM32F407"


# --- Delete Tests ---


class TestChromaStoreDelete:
    def test_delete_by_doc_id(self, tmp_path: Path):
        store = _make_store(tmp_path)
        chunks = [
            _make_embedded_chunk(chunk_id="c1", doc_id="doc1"),
            _make_embedded_chunk(chunk_id="c2", doc_id="doc1"),
        ]
        store.add(chunks, "doc1")
        assert store.count() == 2

        deleted = store.delete("doc1")
        assert deleted == 2
        assert store.count() == 0

    def test_delete_nonexistent_returns_zero(self, tmp_path: Path):
        store = _make_store(tmp_path)
        assert store.delete("nonexistent") == 0

    def test_delete_reduces_count(self, tmp_path: Path):
        """Deleting one doc should not affect chunks from other docs."""
        store = _make_store(tmp_path)
        store.add([_make_embedded_chunk(chunk_id="c1", doc_id="doc1")], "doc1")
        store.add([_make_embedded_chunk(chunk_id="c2", doc_id="doc2")], "doc2")
        assert store.count() == 2

        store.delete("doc1")
        assert store.count() == 1

        # Remaining chunk should be from doc2
        results = store.search([0.1, 0.2, 0.3], k=10)
        assert len(results) == 1
        assert results[0].chunk.metadata.doc_id == "doc2"


# --- Count Tests ---


class TestChromaStoreCount:
    def test_count_empty(self, tmp_path: Path):
        store = _make_store(tmp_path)
        assert store.count() == 0

    def test_count_after_add(self, tmp_path: Path):
        store = _make_store(tmp_path)
        chunks = [
            _make_embedded_chunk(chunk_id="c1"),
            _make_embedded_chunk(chunk_id="c2"),
            _make_embedded_chunk(chunk_id="c3"),
        ]
        store.add(chunks, "doc1")
        assert store.count() == 3


# --- Persistence Tests ---


class TestChromaStorePersistence:
    def test_data_persists_across_instances(self, tmp_path: Path):
        """Data should survive creating a new ChromaStore with the same path."""
        persist_path = tmp_path / "chroma"

        # First instance: add data
        store1 = ChromaStore(persist_path=persist_path, collection_name="test")
        store1.add([_make_embedded_chunk(chunk_id="c1")], "doc1")
        assert store1.count() == 1

        # Second instance: data should be there
        store2 = ChromaStore(persist_path=persist_path, collection_name="test")
        assert store2.count() == 1

        results = store2.search([0.1, 0.2, 0.3], k=1)
        assert len(results) == 1
        assert results[0].chunk.chunk_id == "c1"


# --- Error Handling Tests ---


class TestChromaStoreErrors:
    def test_add_wraps_chromadb_errors(self, tmp_path: Path):
        """Mismatched embedding dimensions should raise StoreError."""
        store = _make_store(tmp_path)
        chunk_3d = _make_embedded_chunk(chunk_id="c1", embedding=(0.1, 0.2, 0.3))
        store.add([chunk_3d], "doc1")

        # Adding a chunk with different embedding dimension should fail
        chunk_5d = _make_embedded_chunk(chunk_id="c2", embedding=(0.1, 0.2, 0.3, 0.4, 0.5))
        with pytest.raises(StoreError):
            store.add([chunk_5d], "doc1")

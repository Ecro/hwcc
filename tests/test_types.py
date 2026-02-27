"""Tests for hwcc.types module — pipeline data contracts."""

from __future__ import annotations

import dataclasses

import pytest

from hwcc.types import (
    Chunk,
    ChunkMetadata,
    EmbeddedChunk,
    ParseResult,
    SearchResult,
)


class TestChunkMetadata:
    def test_frozen(self):
        meta = ChunkMetadata(doc_id="test")
        with pytest.raises(dataclasses.FrozenInstanceError):
            meta.doc_id = "changed"  # type: ignore[misc]

    def test_defaults(self):
        meta = ChunkMetadata(doc_id="test")
        assert meta.doc_type == ""
        assert meta.chip == ""
        assert meta.page == 0
        assert meta.chunk_level == "detail"
        assert meta.peripheral == ""

    def test_all_fields(self):
        meta = ChunkMetadata(
            doc_id="ds_stm32f407",
            doc_type="datasheet",
            chip="STM32F407",
            section_path="SPI > Config",
            page=42,
            chunk_level="summary",
            peripheral="SPI1",
            content_type="register_description",
        )
        assert meta.doc_id == "ds_stm32f407"
        assert meta.chip == "STM32F407"
        assert meta.page == 42


class TestParseResult:
    def test_frozen(self):
        result = ParseResult(doc_id="test", content="hello")
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.content = "changed"  # type: ignore[misc]

    def test_minimal(self):
        result = ParseResult(doc_id="test", content="# Hello")
        assert result.doc_id == "test"
        assert result.content == "# Hello"
        assert result.doc_type == ""
        assert result.metadata == ()

    def test_with_metadata_tuple(self):
        result = ParseResult(
            doc_id="test",
            content="body",
            metadata=(("chip", "STM32F407"), ("vendor", "ST")),
        )
        assert len(result.metadata) == 2
        assert result.metadata[0] == ("chip", "STM32F407")


class TestChunk:
    def test_frozen(self):
        meta = ChunkMetadata(doc_id="test")
        chunk = Chunk(chunk_id="c1", content="text", token_count=10, metadata=meta)
        with pytest.raises(dataclasses.FrozenInstanceError):
            chunk.content = "changed"  # type: ignore[misc]

    def test_fields(self):
        meta = ChunkMetadata(doc_id="test", peripheral="SPI1")
        chunk = Chunk(chunk_id="c1", content="SPI config", token_count=42, metadata=meta)
        assert chunk.chunk_id == "c1"
        assert chunk.token_count == 42
        assert chunk.metadata.peripheral == "SPI1"


class TestEmbeddedChunk:
    def test_frozen(self):
        meta = ChunkMetadata(doc_id="test")
        chunk = Chunk(chunk_id="c1", content="text", token_count=10, metadata=meta)
        embedded = EmbeddedChunk(chunk=chunk, embedding=(0.1, 0.2, 0.3))
        with pytest.raises(dataclasses.FrozenInstanceError):
            embedded.embedding = (0.4, 0.5)  # type: ignore[misc]

    def test_embedding_is_tuple(self):
        meta = ChunkMetadata(doc_id="test")
        chunk = Chunk(chunk_id="c1", content="text", token_count=10, metadata=meta)
        embedded = EmbeddedChunk(chunk=chunk, embedding=(0.1, 0.2, 0.3))
        assert isinstance(embedded.embedding, tuple)
        assert len(embedded.embedding) == 3

    def test_default_empty_embedding(self):
        meta = ChunkMetadata(doc_id="test")
        chunk = Chunk(chunk_id="c1", content="text", token_count=10, metadata=meta)
        embedded = EmbeddedChunk(chunk=chunk)
        assert embedded.embedding == ()


class TestSearchResult:
    def test_fields(self):
        meta = ChunkMetadata(doc_id="test")
        chunk = Chunk(chunk_id="c1", content="text", token_count=10, metadata=meta)
        result = SearchResult(chunk=chunk, score=0.95, distance=0.05)
        assert result.score == 0.95
        assert result.distance == 0.05

    def test_default_distance(self):
        meta = ChunkMetadata(doc_id="test")
        chunk = Chunk(chunk_id="c1", content="text", token_count=10, metadata=meta)
        result = SearchResult(chunk=chunk, score=0.9)
        assert result.distance == 0.0

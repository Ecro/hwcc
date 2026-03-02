"""Tests for the hwcc.search module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hwcc.exceptions import EmbeddingError, StoreError
from hwcc.search import SearchEngine, build_where
from hwcc.types import Chunk, ChunkMetadata, SearchResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    score: float = 0.85,
    content: str = "GPIOA MODER register description",
    chip: str = "STM32F407",
    peripheral: str = "GPIOA",
    doc_type: str = "svd",
) -> SearchResult:
    meta = ChunkMetadata(
        doc_id="doc1",
        doc_type=doc_type,
        chip=chip,
        peripheral=peripheral,
    )
    chunk = Chunk(chunk_id="c1", content=content, token_count=10, metadata=meta)
    return SearchResult(chunk=chunk, score=score, distance=1.0 / score - 1.0)


def _make_engine(
    results: list[SearchResult] | None = None,
    query_embedding: list[float] | None = None,
) -> tuple[SearchEngine, MagicMock, MagicMock]:
    """Create a SearchEngine with mocked embedder and store."""
    embedder = MagicMock()
    embedder.embed_query.return_value = query_embedding or [0.1, 0.2, 0.3]

    store = MagicMock()
    store.search.return_value = results if results is not None else []

    engine = SearchEngine(embedder=embedder, store=store)
    return engine, embedder, store


# ---------------------------------------------------------------------------
# Tests: build_where
# ---------------------------------------------------------------------------


class TestBuildWhere:
    """Tests for the ChromaDB where clause builder."""

    def test_no_filters_returns_none(self) -> None:
        result = build_where()
        assert result is None

    def test_single_chip_filter(self) -> None:
        result = build_where(chip="STM32F407")
        assert result == {"chip": "STM32F407"}

    def test_single_doc_type_filter(self) -> None:
        result = build_where(doc_type="svd")
        assert result == {"doc_type": "svd"}

    def test_single_peripheral_filter(self) -> None:
        result = build_where(peripheral="GPIOA")
        assert result == {"peripheral": "GPIOA"}

    def test_single_content_type_filter(self) -> None:
        result = build_where(content_type="register_description")
        assert result == {"content_type": "register_description"}

    def test_two_filters_uses_and(self) -> None:
        result = build_where(chip="STM32F407", doc_type="svd")
        assert result is not None
        assert "$and" in result
        filters = result["$and"]
        assert {"chip": "STM32F407"} in filters
        assert {"doc_type": "svd"} in filters

    def test_three_filters_uses_and(self) -> None:
        result = build_where(
            chip="STM32F407",
            doc_type="svd",
            peripheral="GPIOA",
        )
        assert result is not None
        assert "$and" in result
        filters = result["$and"]
        assert len(filters) == 3

    def test_four_filters_uses_and(self) -> None:
        result = build_where(
            chip="STM32F407",
            doc_type="svd",
            peripheral="GPIOA",
            content_type="register_description",
        )
        assert result is not None
        assert "$and" in result
        filters = result["$and"]
        assert len(filters) == 4

    def test_empty_strings_ignored(self) -> None:
        result = build_where(chip="", doc_type="svd", peripheral="")
        assert result == {"doc_type": "svd"}


# ---------------------------------------------------------------------------
# Tests: search()
# ---------------------------------------------------------------------------


class TestSearchEngine:
    """Tests for the SearchEngine.search method."""

    def test_search_calls_embedder_and_store(self) -> None:
        engine, embedder, store = _make_engine()

        engine.search("GPIO config")

        embedder.embed_query.assert_called_once_with("GPIO config")
        store.search.assert_called_once()

    def test_search_passes_query_embedding_to_store(self) -> None:
        engine, embedder, store = _make_engine(query_embedding=[0.5, 0.6, 0.7])

        engine.search("GPIO config")

        call_args = store.search.call_args
        assert call_args[0][0] == [0.5, 0.6, 0.7]  # first positional arg

    def test_search_passes_k_to_store(self) -> None:
        engine, _, store = _make_engine()

        engine.search("GPIO config", k=10)

        call_args = store.search.call_args
        assert call_args[1]["k"] == 10 or call_args[0][1] == 10

    def test_search_passes_no_filters_as_none(self) -> None:
        engine, _, store = _make_engine()

        engine.search("GPIO config")

        call_args = store.search.call_args
        assert call_args[1].get("where") is None

    def test_search_passes_chip_filter(self) -> None:
        engine, _, store = _make_engine()

        engine.search("GPIO config", chip="STM32F407")

        call_args = store.search.call_args
        assert call_args[1]["where"] == {"chip": "STM32F407"}

    def test_search_passes_combined_filters(self) -> None:
        engine, _, store = _make_engine()

        engine.search("GPIO", chip="STM32F407", doc_type="svd")

        call_args = store.search.call_args
        where = call_args[1]["where"]
        assert "$and" in where

    def test_search_returns_results_and_timing(self) -> None:
        expected = [_make_result()]
        engine, _, _ = _make_engine(results=expected)

        results, elapsed = engine.search("GPIO config")

        assert results == expected
        assert elapsed >= 0.0

    def test_search_returns_empty_for_no_matches(self) -> None:
        engine, _, _ = _make_engine(results=[])

        results, elapsed = engine.search("nonexistent")

        assert results == []
        assert elapsed >= 0.0

    def test_search_propagates_embedding_error(self) -> None:
        engine, embedder, _ = _make_engine()
        embedder.embed_query.side_effect = EmbeddingError("model failed")

        with pytest.raises(EmbeddingError, match="model failed"):
            engine.search("GPIO config")

    def test_search_propagates_store_error(self) -> None:
        engine, _, store = _make_engine()
        store.search.side_effect = StoreError("store failed")

        with pytest.raises(StoreError, match="store failed"):
            engine.search("GPIO config")

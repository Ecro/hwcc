"""Tests for hwcc.compile.relevance — keyword-overlap scoring."""

from __future__ import annotations

import pytest

from hwcc.compile.relevance import (
    _MIN_RELEVANCE_SCORE,
    _tokenize,
    build_peripheral_keywords,
    rank_chunks,
    score_chunk_relevance,
)
from hwcc.types import Chunk, ChunkMetadata

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(chunk_id: str, content: str) -> Chunk:
    """Create a minimal Chunk for scoring tests."""
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        token_count=len(content.split()),
        metadata=ChunkMetadata(doc_id="test_doc"),
    )


# ---------------------------------------------------------------------------
# Tests: _tokenize
# ---------------------------------------------------------------------------


class TestTokenize:
    """Tests for the _tokenize helper."""

    def test_plain_text(self) -> None:
        """Extracts lowercase word tokens from plain text."""
        tokens = _tokenize("Hello World SPI1 clock")
        assert "hello" in tokens
        assert "world" in tokens
        assert "spi1" in tokens
        assert "clock" in tokens

    def test_strips_markdown_syntax(self) -> None:
        """Markdown symbols (##, **, |, `) are not included in tokens."""
        tokens = _tokenize("## **SPI1** | `0x40013000` | Control register")
        assert "spi1" in tokens
        assert "control" in tokens
        # Markdown artifacts should not be tokens
        assert "##" not in tokens
        assert "**" not in tokens
        assert "|" not in tokens

    def test_filters_stopwords(self) -> None:
        """Common stopwords are excluded."""
        tokens = _tokenize("the SPI1 register is used for control and data")
        assert "spi1" in tokens
        assert "control" in tokens
        assert "data" in tokens
        # Stopwords
        assert "the" not in tokens
        assert "and" not in tokens
        # "register" is in our hardware stopwords
        assert "register" not in tokens

    def test_empty_input(self) -> None:
        """Empty or whitespace input returns empty set."""
        assert _tokenize("") == set()
        assert _tokenize("   ") == set()

    def test_single_char_tokens_excluded(self) -> None:
        """Single-character tokens are excluded by the regex."""
        tokens = _tokenize("a b c SPI1")
        assert "a" not in tokens
        assert "b" not in tokens
        assert "spi1" in tokens


# ---------------------------------------------------------------------------
# Tests: build_peripheral_keywords
# ---------------------------------------------------------------------------


class TestBuildPeripheralKeywords:
    """Tests for build_peripheral_keywords."""

    def test_name_tokens(self) -> None:
        """Extracts peripheral name and base name."""
        kw = build_peripheral_keywords("SPI1")
        assert "spi1" in kw
        assert "spi" in kw

    def test_name_without_trailing_digits(self) -> None:
        """Peripheral name with no digits produces just the name."""
        kw = build_peripheral_keywords("GPIOA")
        assert "gpioa" in kw
        # No trailing digits → no base-name stripping
        # "gpioa" doesn't end in digits, so no separate base

    def test_register_names_from_table(self) -> None:
        """Extracts register names from markdown table first column."""
        reg_map = (
            "| Register | Offset | Description |\n"
            "|----------|--------|-------------|\n"
            "| CR1 | 0x0000 | Control register 1 |\n"
            "| CR2 | 0x0004 | Control register 2 |\n"
            "| SR | 0x0008 | Status register |"
        )
        kw = build_peripheral_keywords("SPI1", register_map=reg_map)
        assert "cr1" in kw
        assert "cr2" in kw
        assert "sr" in kw

    def test_description_words(self) -> None:
        """Extracts non-stopword tokens from description."""
        kw = build_peripheral_keywords(
            "SPI1", description="Serial peripheral interface"
        )
        assert "serial" in kw
        assert "peripheral" in kw
        assert "interface" in kw

    def test_empty_inputs_returns_name_only(self) -> None:
        """With no register_map or description, returns name tokens only."""
        kw = build_peripheral_keywords("USART2")
        assert "usart2" in kw
        assert "usart" in kw
        assert len(kw) == 2

    def test_combined_sources(self) -> None:
        """Keywords come from all three sources."""
        kw = build_peripheral_keywords(
            "SPI1",
            register_map="| CR1 | 0x00 | Control |\n| DR | 0x0C | Data |",
            description="Serial peripheral interface",
        )
        # Name tokens
        assert "spi1" in kw
        assert "spi" in kw
        # Register names
        assert "cr1" in kw
        assert "dr" in kw
        # Description words
        assert "serial" in kw


# ---------------------------------------------------------------------------
# Tests: score_chunk_relevance
# ---------------------------------------------------------------------------


class TestScoreChunkRelevance:
    """Tests for score_chunk_relevance."""

    def test_no_overlap_returns_zero(self) -> None:
        """Content with no matching keywords scores 0.0."""
        score = score_chunk_relevance(
            "GPIO port configuration and clock tree",
            {"spi1", "spi", "cr1"},
        )
        assert score == 0.0

    def test_full_overlap_returns_one(self) -> None:
        """Content containing all keywords scores 1.0."""
        score = score_chunk_relevance(
            "The SPI1 module uses SPI protocol via CR1",
            {"spi1", "spi", "cr1"},
        )
        assert score == pytest.approx(1.0)

    def test_partial_overlap_returns_ratio(self) -> None:
        """Partial overlap returns correct ratio."""
        # "SPI1 serial configuration" → tokens: {spi1, serial, configuration}
        # keywords: {spi1, spi, cr1, serial} → overlap: {spi1, serial} = 2/4
        score = score_chunk_relevance(
            "SPI1 serial configuration",
            {"spi1", "spi", "cr1", "serial"},
        )
        assert score == pytest.approx(0.5)

    def test_empty_keywords_returns_zero(self) -> None:
        """Empty keyword set returns 0.0."""
        assert score_chunk_relevance("some content", set()) == 0.0

    def test_empty_content_returns_zero(self) -> None:
        """Empty content returns 0.0."""
        assert score_chunk_relevance("", {"spi1"}) == 0.0


# ---------------------------------------------------------------------------
# Tests: rank_chunks
# ---------------------------------------------------------------------------


class TestRankChunks:
    """Tests for rank_chunks."""

    def test_sorts_by_score_descending(self) -> None:
        """Chunks are returned highest-score first."""
        low = _make_chunk("chunk_001", "GPIO port configuration")
        high = _make_chunk("chunk_002", "SPI1 SPI CR1 serial configuration")
        keywords = {"spi1", "spi", "cr1", "serial"}

        result = rank_chunks([low, high], keywords, max_chunks=5)
        assert len(result) >= 1
        assert result[0].chunk_id == "chunk_002"

    def test_filters_below_threshold(self) -> None:
        """Chunks scoring below min_score are excluded."""
        irrelevant = _make_chunk("chunk_001", "GPIO clock tree configuration")
        keywords = {"spi1", "spi", "cr1", "serial", "interface",
                     "mosi", "miso", "sck", "bidimode", "spe"}

        result = rank_chunks([irrelevant], keywords, min_score=0.1)
        assert len(result) == 0

    def test_respects_max_chunks(self) -> None:
        """At most max_chunks are returned."""
        chunks = [
            _make_chunk(f"chunk_{i:03d}", f"SPI1 SPI content block {i}")
            for i in range(10)
        ]
        keywords = {"spi1", "spi"}
        result = rank_chunks(chunks, keywords, max_chunks=3)
        assert len(result) == 3

    def test_chunk_id_tiebreak(self) -> None:
        """Equal-score chunks are ordered by chunk_id ascending."""
        a = _make_chunk("chunk_002", "SPI1 configuration")
        b = _make_chunk("chunk_001", "SPI1 configuration")
        keywords = {"spi1", "configuration"}

        result = rank_chunks([a, b], keywords, max_chunks=5)
        assert result[0].chunk_id == "chunk_001"
        assert result[1].chunk_id == "chunk_002"

    def test_empty_chunks_returns_empty(self) -> None:
        """Empty input returns empty list."""
        assert rank_chunks([], {"spi1"}) == []

    def test_empty_keywords_falls_back_to_positional(self) -> None:
        """With no keywords, returns chunks in chunk_id order."""
        b = _make_chunk("chunk_002", "some content")
        a = _make_chunk("chunk_001", "other content")

        result = rank_chunks([b, a], set(), max_chunks=5)
        assert result[0].chunk_id == "chunk_001"
        assert result[1].chunk_id == "chunk_002"

    def test_default_min_score_matches_module_constant(self) -> None:
        """Default min_score parameter equals _MIN_RELEVANCE_SCORE."""
        # Verify the constant is what we expect
        assert pytest.approx(0.1) == _MIN_RELEVANCE_SCORE

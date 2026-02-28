"""Tests for the MarkdownChunker."""

from __future__ import annotations

import pytest

from hwcc.chunk.markdown import (
    MarkdownChunker,
    _extract_atomic_blocks,
    _SectionTracker,
    count_tokens,
)
from hwcc.config import ChunkConfig, HwccConfig, default_config
from hwcc.types import ParseResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def chunker() -> MarkdownChunker:
    return MarkdownChunker()


@pytest.fixture
def config() -> HwccConfig:
    return default_config()


def _make_result(content: str, doc_id: str = "test_doc", **kwargs) -> ParseResult:
    """Helper to create a ParseResult with given content."""
    return ParseResult(doc_id=doc_id, content=content, **kwargs)


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_simple_text(self):
        tokens = count_tokens("Hello, world!")
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_longer_text_has_more_tokens(self):
        short = count_tokens("Hello")
        long = count_tokens("Hello, this is a much longer sentence with many words.")
        assert long > short


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


class TestChunkConfig:
    def test_default_values(self):
        cfg = ChunkConfig()
        assert cfg.max_tokens == 512
        assert cfg.overlap_tokens == 50
        assert cfg.min_tokens == 50

    def test_config_in_hwcc_config(self):
        cfg = default_config()
        assert hasattr(cfg, "chunk")
        assert cfg.chunk.max_tokens == 512


# ---------------------------------------------------------------------------
# Empty and trivial inputs
# ---------------------------------------------------------------------------


class TestEmptyInput:
    def test_empty_content_returns_empty(self, chunker, config):
        result = _make_result("")
        chunks = chunker.chunk(result, config)
        assert chunks == []

    def test_whitespace_only_returns_empty(self, chunker, config):
        result = _make_result("   \n\n\t  \n  ")
        chunks = chunker.chunk(result, config)
        assert chunks == []


# ---------------------------------------------------------------------------
# Single chunk (content fits within max_tokens)
# ---------------------------------------------------------------------------


class TestSingleChunk:
    def test_short_content_single_chunk(self, chunker, config):
        result = _make_result("This is a short document.")
        chunks = chunker.chunk(result, config)
        assert len(chunks) == 1
        assert "short document" in chunks[0].content

    def test_single_chunk_token_count(self, chunker, config):
        text = "Hello, this is a test document with some content."
        result = _make_result(text)
        chunks = chunker.chunk(result, config)
        assert len(chunks) == 1
        assert chunks[0].token_count == count_tokens(chunks[0].content)
        assert chunks[0].token_count > 0


# ---------------------------------------------------------------------------
# Multi-chunk splitting
# ---------------------------------------------------------------------------


class TestMultiChunkSplitting:
    def test_long_content_splits(self, chunker):
        """Content exceeding max_tokens should be split into multiple chunks."""
        config = default_config()
        config.chunk.max_tokens = 50  # Small limit to force splitting
        config.chunk.overlap_tokens = 0

        # Generate content that exceeds 50 tokens
        paragraphs = [f"Paragraph {i}. " + "word " * 30 for i in range(5)]
        content = "\n\n".join(paragraphs)

        result = _make_result(content)
        chunks = chunker.chunk(result, config)
        assert len(chunks) > 1

    def test_chunks_respect_max_tokens(self, chunker):
        """Each non-atomic chunk should be within max_tokens budget."""
        config = default_config()
        config.chunk.max_tokens = 100
        config.chunk.overlap_tokens = 0  # No overlap for simpler assertion

        paragraphs = [f"Section {i}. " + "word " * 40 for i in range(10)]
        content = "\n\n".join(paragraphs)

        result = _make_result(content)
        chunks = chunker.chunk(result, config)

        for chunk in chunks:
            assert chunk.token_count <= config.chunk.max_tokens


# ---------------------------------------------------------------------------
# Overlap
# ---------------------------------------------------------------------------


class TestOverlap:
    def test_overlap_present_between_chunks(self, chunker):
        """Consecutive chunks should share overlap text."""
        config = default_config()
        config.chunk.max_tokens = 60
        config.chunk.overlap_tokens = 10
        config.chunk.min_tokens = 0  # Don't merge

        # Create content that will split into at least 2 chunks
        paragraphs = [f"Paragraph number {i}. " + "word " * 25 for i in range(5)]
        content = "\n\n".join(paragraphs)

        result = _make_result(content)
        chunks = chunker.chunk(result, config)

        if len(chunks) >= 2:
            # The end of chunk 0 should appear at the start of chunk 1
            # (because of overlap)
            chunk0_words = chunks[0].content.split()
            chunk1_content = chunks[1].content
            # At least some words from the end of chunk 0 should be in chunk 1
            last_words = " ".join(chunk0_words[-3:])
            assert last_words in chunk1_content or len(chunks) == 1

    def test_no_overlap_when_zero(self, chunker):
        """With overlap_tokens=0, chunks should not overlap."""
        config = default_config()
        config.chunk.max_tokens = 50
        config.chunk.overlap_tokens = 0
        config.chunk.min_tokens = 0

        content = "First paragraph with some words.\n\nSecond paragraph with other words."
        result = _make_result(content)
        chunks = chunker.chunk(result, config)
        # Just verify it doesn't crash
        assert len(chunks) >= 1

    def test_overlap_respects_max_tokens(self, chunker):
        """Chunks with overlap should still be within max_tokens budget."""
        config = default_config()
        config.chunk.max_tokens = 100
        config.chunk.overlap_tokens = 20
        config.chunk.min_tokens = 0

        paragraphs = [f"Section {i}. " + "word " * 40 for i in range(10)]
        content = "\n\n".join(paragraphs)

        result = _make_result(content)
        chunks = chunker.chunk(result, config)

        for chunk in chunks:
            assert chunk.token_count <= config.chunk.max_tokens

    def test_overlap_not_added_to_atomic_blocks(self, chunker):
        """Atomic blocks (tables, code) should not receive overlap prefix."""
        config = default_config()
        config.chunk.max_tokens = 100
        config.chunk.overlap_tokens = 20
        config.chunk.min_tokens = 0

        # Prose followed by a code block — the code block should not get overlap
        content = (
            "Some introductory text with enough words to fill a chunk. " * 5
            + "\n\n"
            + "```c\n"
            + "void init_gpio(void) {\n"
            + "    GPIOA->MODER |= (1 << 10);\n"
            + "}\n"
            + "```\n"
        )

        result = _make_result(content)
        chunks = chunker.chunk(result, config)

        # Find the code chunk
        code_chunks = [c for c in chunks if "init_gpio" in c.content]
        assert len(code_chunks) >= 1
        # Code chunk should start with the code fence, not overlap text
        for cc in code_chunks:
            assert cc.content.startswith("```")


# ---------------------------------------------------------------------------
# Table preservation
# ---------------------------------------------------------------------------


class TestTablePreservation:
    def test_table_not_split(self, chunker):
        """Markdown tables should never be split across chunks."""
        config = default_config()
        config.chunk.max_tokens = 50
        config.chunk.overlap_tokens = 0

        table = (
            "| Register | Offset | Reset |\n"
            "|----------|--------|-------|\n"
            "| CR1      | 0x00   | 0x0000 |\n"
            "| CR2      | 0x04   | 0x0000 |\n"
            "| SR       | 0x08   | 0x0002 |\n"
            "| DR       | 0x0C   | 0x0000 |\n"
        )
        content = f"Some intro text.\n\n{table}\n\nSome outro text."

        result = _make_result(content)
        chunks = chunker.chunk(result, config)

        # Find the chunk containing the table
        table_chunks = [c for c in chunks if "|-------" in c.content]
        assert len(table_chunks) >= 1

        # The entire table should be in one chunk
        for tc in table_chunks:
            assert "CR1" in tc.content
            assert "DR" in tc.content

    def test_table_content_type(self, chunker, config):
        """Chunks containing tables should have content_type='table'."""
        table = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        result = _make_result(table)
        chunks = chunker.chunk(result, config)
        assert len(chunks) == 1
        assert chunks[0].metadata.content_type == "table"


# ---------------------------------------------------------------------------
# Code block preservation
# ---------------------------------------------------------------------------


class TestCodeBlockPreservation:
    def test_fenced_code_not_split(self, chunker):
        """Fenced code blocks should never be split."""
        config = default_config()
        config.chunk.max_tokens = 50
        config.chunk.overlap_tokens = 0

        code = "```c\nvoid init(void) {\n    RCC->APB1ENR |= RCC_APB1ENR_SPI2EN;\n}\n```"
        content = f"Some text before.\n\n{code}\n\nSome text after."

        result = _make_result(content)
        chunks = chunker.chunk(result, config)

        # Find chunk with code
        code_chunks = [c for c in chunks if "RCC->APB1ENR" in c.content]
        assert len(code_chunks) == 1
        assert "```c" in code_chunks[0].content
        assert "```" in code_chunks[0].content

    def test_code_content_type(self, chunker, config):
        """Chunks containing code should have content_type='code'."""
        code = "```python\nprint('hello')\n```"
        result = _make_result(code)
        chunks = chunker.chunk(result, config)
        assert len(chunks) == 1
        assert chunks[0].metadata.content_type == "code"


# ---------------------------------------------------------------------------
# Heading boundary splitting
# ---------------------------------------------------------------------------


class TestHeadingBoundaries:
    def test_splits_at_h2_boundaries(self, chunker):
        """Chunker should prefer splitting at heading boundaries."""
        config = default_config()
        config.chunk.max_tokens = 60
        config.chunk.overlap_tokens = 0
        config.chunk.min_tokens = 0

        content = (
            "# Main Title\n\n"
            "## Section A\n\n" + "Word " * 40 + "\n\n## Section B\n\n" + "Word " * 40
        )

        result = _make_result(content)
        chunks = chunker.chunk(result, config)

        # Should split at section boundaries
        assert len(chunks) >= 2

        # At least one chunk should start with a heading
        heading_starts = [c for c in chunks if c.content.strip().startswith("#")]
        assert len(heading_starts) >= 1

    def test_splits_at_heading_at_start_of_text(self, chunker):
        """Content starting with a heading (no preceding newline) should still split."""
        config = default_config()
        config.chunk.max_tokens = 60
        config.chunk.overlap_tokens = 0
        config.chunk.min_tokens = 0

        # Text starts directly with # (no newline prefix)
        content = "# Peripheral A\n\n" + "Word " * 40 + "\n\n# Peripheral B\n\n" + "Word " * 40

        result = _make_result(content)
        chunks = chunker.chunk(result, config)

        # Should split at the H1 boundary
        assert len(chunks) >= 2
        assert chunks[0].content.strip().startswith("# Peripheral A")


# ---------------------------------------------------------------------------
# Section path tracking
# ---------------------------------------------------------------------------


class TestSectionPath:
    def test_section_path_from_headings(self, chunker, config):
        """Section path should track heading hierarchy."""
        content = (
            "# SPI\n\n"
            "SPI peripheral description.\n\n"
            "## Configuration\n\n"
            "How to configure SPI.\n\n"
            "### DMA\n\n"
            "DMA configuration for SPI."
        )

        result = _make_result(content)
        chunks = chunker.chunk(result, config)

        # With default 512 tokens, this should be a single chunk
        assert len(chunks) >= 1
        # The section path should reflect the deepest heading hierarchy
        last_chunk = chunks[-1]
        assert "SPI" in last_chunk.metadata.section_path

    def test_section_tracker_stack(self):
        """SectionTracker should maintain proper heading hierarchy."""
        tracker = _SectionTracker()

        tracker.update("# SPI\n\nSome content")
        assert tracker.path == "SPI"

        tracker.update("## Configuration\n\nMore content")
        assert tracker.path == "SPI > Configuration"

        tracker.update("### DMA\n\nDMA stuff")
        assert tracker.path == "SPI > Configuration > DMA"

        # H2 should pop H3
        tracker.update("## Registers\n\nRegister map")
        assert tracker.path == "SPI > Registers"


# ---------------------------------------------------------------------------
# Metadata propagation
# ---------------------------------------------------------------------------


class TestMetadataPropagation:
    def test_doc_id_propagated(self, chunker, config):
        result = _make_result("Some content.", doc_id="my_doc_123")
        chunks = chunker.chunk(result, config)
        assert len(chunks) == 1
        assert chunks[0].metadata.doc_id == "my_doc_123"

    def test_doc_type_propagated(self, chunker, config):
        result = _make_result("Some content.", doc_type="datasheet")
        chunks = chunker.chunk(result, config)
        assert chunks[0].metadata.doc_type == "datasheet"

    def test_chip_propagated(self, chunker, config):
        result = _make_result("Some content.", chip="STM32F407")
        chunks = chunker.chunk(result, config)
        assert chunks[0].metadata.chip == "STM32F407"


# ---------------------------------------------------------------------------
# Chunk ID uniqueness
# ---------------------------------------------------------------------------


class TestChunkIdUniqueness:
    def test_chunk_ids_are_unique(self, chunker):
        """All chunk IDs in a document should be unique."""
        config = default_config()
        config.chunk.max_tokens = 50
        config.chunk.overlap_tokens = 0

        paragraphs = [f"Paragraph {i}. " + "word " * 20 for i in range(10)]
        content = "\n\n".join(paragraphs)

        result = _make_result(content)
        chunks = chunker.chunk(result, config)

        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "Chunk IDs are not unique"

    def test_chunk_id_contains_doc_id(self, chunker, config):
        result = _make_result("Some content.", doc_id="my_doc")
        chunks = chunker.chunk(result, config)
        assert "my_doc" in chunks[0].chunk_id


# ---------------------------------------------------------------------------
# Min tokens merging
# ---------------------------------------------------------------------------


class TestMinTokensMerging:
    def test_tiny_chunks_merged(self, chunker):
        """Chunks below min_tokens should be merged with neighbors."""
        config = default_config()
        config.chunk.max_tokens = 200
        config.chunk.overlap_tokens = 0
        config.chunk.min_tokens = 30

        # Create alternating short and normal paragraphs
        content = (
            "Short.\n\n"
            + "This is a longer paragraph with enough words to be meaningful. " * 3
            + "\n\nTiny.\n\n"
            + "Another longer paragraph with plenty of content to work with. " * 3
        )

        result = _make_result(content)
        chunks = chunker.chunk(result, config)

        # None of the chunks should be below min_tokens
        # (except possibly the very last one if it can't be merged)
        for chunk in chunks[:-1]:
            assert chunk.token_count >= config.chunk.min_tokens


# ---------------------------------------------------------------------------
# Oversized atomic blocks
# ---------------------------------------------------------------------------


class TestOversizedAtomicBlocks:
    def test_large_table_becomes_single_chunk(self, chunker):
        """A table exceeding max_tokens should still be a single chunk."""
        config = default_config()
        config.chunk.max_tokens = 50
        config.chunk.overlap_tokens = 0

        # Build a large table
        rows = [f"| REG_{i:03d} | 0x{i * 4:04X} | 0x00000000 | Read/Write |" for i in range(30)]
        table = "| Register | Offset | Reset | Access |\n|----------|--------|-------|--------|\n"
        table += "\n".join(rows)

        result = _make_result(table)
        chunks = chunker.chunk(result, config)

        # The entire table should be in one chunk
        assert len(chunks) == 1
        assert "REG_000" in chunks[0].content
        assert "REG_029" in chunks[0].content


# ---------------------------------------------------------------------------
# Atomic block extraction
# ---------------------------------------------------------------------------


class TestAtomicBlockExtraction:
    def test_identifies_fenced_code(self):
        text = "Before.\n\n```python\ncode here\n```\n\nAfter."
        segments = _extract_atomic_blocks(text)

        atomic = [(s, a) for s, a in segments if a]
        assert len(atomic) == 1
        assert "code here" in atomic[0][0]

    def test_identifies_table(self):
        text = "Before.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nAfter."
        segments = _extract_atomic_blocks(text)

        atomic = [(s, a) for s, a in segments if a]
        assert len(atomic) == 1
        assert "| A | B |" in atomic[0][0]

    def test_non_table_pipe_lines(self):
        """Lines with pipes but no separator row should not be treated as tables."""
        text = "| This is not a table |\n| Just pipes |"
        segments = _extract_atomic_blocks(text)

        atomic = [(s, a) for s, a in segments if a]
        assert len(atomic) == 0

    def test_tilde_fence(self):
        text = "Before.\n\n~~~\ncode\n~~~\n\nAfter."
        segments = _extract_atomic_blocks(text)

        atomic = [(s, a) for s, a in segments if a]
        assert len(atomic) == 1
        assert "code" in atomic[0][0]


# ---------------------------------------------------------------------------
# Content type detection
# ---------------------------------------------------------------------------


class TestContentType:
    def test_prose_type(self, chunker, config):
        result = _make_result("Just some plain text without any special formatting.")
        chunks = chunker.chunk(result, config)
        assert chunks[0].metadata.content_type == "prose"

    def test_section_type(self, chunker, config):
        result = _make_result("# Heading\n\nSome text under a heading.")
        chunks = chunker.chunk(result, config)
        assert chunks[0].metadata.content_type == "section"


# ---------------------------------------------------------------------------
# Integration: realistic hardware content
# ---------------------------------------------------------------------------


class TestRealisticContent:
    def test_svd_like_register_map(self, chunker, config):
        """Chunker should handle SVD parser output well."""
        content = (
            "# TIMER0\n\n"
            "Timer/Counter 0 peripheral.\n\n"
            "## Registers\n\n"
            "| Register | Offset | Reset | Access |\n"
            "|----------|--------|-------|--------|\n"
            "| CR | 0x00 | 0x0000 | RW |\n"
            "| SR | 0x04 | 0x0001 | RO |\n"
            "| CNT | 0x08 | 0x0000 | RW |\n"
            "| ARR | 0x0C | 0xFFFF | RW |\n"
            "\n\n"
            "## CR — Control Register\n\n"
            "| Bits | Name | Access | Reset | Description |\n"
            "|------|------|--------|-------|-------------|\n"
            "| 0 | CEN | RW | 0 | Counter enable |\n"
            "| 1 | UDIS | RW | 0 | Update disable |\n"
            "| 2 | URS | RW | 0 | Update request source |\n"
        )

        result = _make_result(content, doc_type="svd")
        chunks = chunker.chunk(result, config)

        # Should produce at least 1 chunk
        assert len(chunks) >= 1
        # Doc type should propagate
        assert all(c.metadata.doc_type == "svd" for c in chunks)
        # Tables should be intact
        for chunk in chunks:
            if "|-------" in chunk.content:
                # Table is not split
                lines = chunk.content.split("\n")
                pipe_lines = [line for line in lines if line.startswith("|")]
                assert len(pipe_lines) >= 3  # header + sep + at least 1 row

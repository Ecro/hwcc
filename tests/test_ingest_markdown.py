"""Tests for hwcc.ingest.markdown — MarkdownParser."""

from __future__ import annotations

from pathlib import Path

import pytest

from hwcc.config import HwccConfig
from hwcc.exceptions import ParseError
from hwcc.ingest.markdown import MarkdownParser
from hwcc.types import ParseResult

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_MD = FIXTURE_DIR / "sample.md"
SAMPLE_FRONTMATTER = FIXTURE_DIR / "sample_frontmatter.md"


@pytest.fixture
def parser() -> MarkdownParser:
    return MarkdownParser()


@pytest.fixture
def config() -> HwccConfig:
    return HwccConfig()


@pytest.fixture
def result(parser: MarkdownParser, config: HwccConfig) -> ParseResult:
    """Parse the sample markdown once, shared across tests."""
    return parser.parse(SAMPLE_MD, config)


@pytest.fixture
def fm_result(parser: MarkdownParser, config: HwccConfig) -> ParseResult:
    """Parse the front-matter markdown once, shared across tests."""
    return parser.parse(SAMPLE_FRONTMATTER, config)


# ── ParseResult fields ─────────────────────────────────────────────


class TestParseResultFields:
    def test_returns_parse_result(self, result: ParseResult) -> None:
        assert isinstance(result, ParseResult)

    def test_doc_type_is_markdown(self, result: ParseResult) -> None:
        assert result.doc_type == "markdown"

    def test_doc_id_follows_stem_md_pattern(self, result: ParseResult) -> None:
        assert result.doc_id == "sample_md"

    def test_source_path_matches_input(self, result: ParseResult) -> None:
        assert result.source_path == str(SAMPLE_MD)

    def test_content_is_non_empty(self, result: ParseResult) -> None:
        assert len(result.content) > 0

    def test_title_from_first_heading(self, result: ParseResult) -> None:
        assert result.title == "STM32F407 SPI Configuration Notes"


# ── Content preservation ───────────────────────────────────────────


class TestContentPreservation:
    def test_preserves_code_blocks(self, result: ParseResult) -> None:
        assert "spi->CR1 = SPI_CR1_MSTR" in result.content

    def test_preserves_markdown_tables(self, result: ParseResult) -> None:
        assert "| SPI_CR1" in result.content

    def test_preserves_headings(self, result: ParseResult) -> None:
        assert "## Clock Configuration" in result.content

    def test_preserves_special_characters(self, result: ParseResult) -> None:
        assert "µs" in result.content
        assert "°C" in result.content
        assert "Ω" in result.content


# ── Whitespace normalization ───────────────────────────────────────


class TestWhitespaceNormalization:
    def test_collapses_excessive_blank_lines(
        self, parser: MarkdownParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        f = tmp_path / "gaps.md"
        f.write_text("line1\n\n\n\n\nline2\n", encoding="utf-8")
        result = parser.parse(f, config)
        assert "\n\n\n" not in result.content
        assert "line1\n\nline2" in result.content

    def test_strips_trailing_whitespace(
        self, parser: MarkdownParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        f = tmp_path / "trailing.md"
        f.write_text("hello   \nworld  \n", encoding="utf-8")
        result = parser.parse(f, config)
        for line in result.content.split("\n"):
            assert line == line.rstrip(), f"Trailing whitespace on: {line!r}"


# ── Front-matter extraction ───────────────────────────────────────


class TestFrontMatter:
    def test_extracts_title_from_frontmatter(self, fm_result: ParseResult) -> None:
        assert fm_result.title == "I2C Bus Configuration Guide"

    def test_extracts_metadata_from_frontmatter(self, fm_result: ParseResult) -> None:
        meta = dict(fm_result.metadata)
        assert meta["chip"] == "STM32F407"
        assert meta["doc_type"] == "app_note"
        assert meta["author"] == "Engineering Team"

    def test_frontmatter_stripped_from_content(self, fm_result: ParseResult) -> None:
        # The --- delimiters and YAML block should not appear in content
        assert not fm_result.content.startswith("---")

    def test_content_after_frontmatter_preserved(self, fm_result: ParseResult) -> None:
        assert "# I2C Bus Configuration" in fm_result.content
        assert "Standard mode (100 kHz)" in fm_result.content

    def test_invalid_frontmatter_treated_as_content(
        self, parser: MarkdownParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        f = tmp_path / "bad_fm.md"
        f.write_text("---\n[invalid yaml: {\n---\n\nContent here\n", encoding="utf-8")
        result = parser.parse(f, config)
        # Should not crash; content should include the bad front-matter
        assert "Content here" in result.content

    def test_no_frontmatter_no_metadata(self, result: ParseResult) -> None:
        # sample.md has no front-matter
        assert result.metadata == ()


# ── Title extraction priority ──────────────────────────────────────


class TestTitleExtraction:
    def test_frontmatter_title_takes_priority(self, fm_result: ParseResult) -> None:
        # Front-matter title should be used even though there's a # heading
        assert fm_result.title == "I2C Bus Configuration Guide"

    def test_heading_title_when_no_frontmatter(self, result: ParseResult) -> None:
        assert result.title == "STM32F407 SPI Configuration Notes"

    def test_filename_stem_when_no_heading(
        self, parser: MarkdownParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        f = tmp_path / "no_heading.md"
        f.write_text("Just some plain text without headings.\n", encoding="utf-8")
        result = parser.parse(f, config)
        assert result.title == "no_heading"

    def test_title_from_h2_when_no_h1(
        self, parser: MarkdownParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        f = tmp_path / "h2_only.md"
        f.write_text("## Subsection Title\nBody text.\n", encoding="utf-8")
        result = parser.parse(f, config)
        assert result.title == "Subsection Title"


# ── Extension support ──────────────────────────────────────────────


class TestExtensions:
    def test_supported_extensions(self, parser: MarkdownParser) -> None:
        exts = parser.supported_extensions()
        assert ".md" in exts
        assert ".markdown" in exts

    def test_can_parse_md_file(self, parser: MarkdownParser, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.touch()
        assert parser.can_parse(f) is True

    def test_cannot_parse_pdf_file(self, parser: MarkdownParser, tmp_path: Path) -> None:
        f = tmp_path / "test.pdf"
        f.touch()
        assert parser.can_parse(f) is False


# ── Error handling ─────────────────────────────────────────────────


class TestErrorHandling:
    def test_raises_parse_error_for_missing_file(
        self, parser: MarkdownParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nonexistent.md"
        with pytest.raises(ParseError, match="not found"):
            parser.parse(missing, config)

    def test_empty_file_returns_empty_content(
        self, parser: MarkdownParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        f = tmp_path / "empty.md"
        f.write_text("", encoding="utf-8")
        result = parser.parse(f, config)
        assert result.content == ""
        assert result.doc_type == "markdown"

    def test_raises_parse_error_for_directory(
        self, parser: MarkdownParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        with pytest.raises(ParseError, match="Not a file"):
            parser.parse(tmp_path, config)

    def test_raises_parse_error_for_oversized_file(
        self,
        parser: MarkdownParser,
        config: HwccConfig,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import hwcc.ingest.markdown as md_mod

        monkeypatch.setattr(md_mod, "MAX_FILE_SIZE", 10)
        f = tmp_path / "big.md"
        f.write_text("x" * 20, encoding="utf-8")
        with pytest.raises(ParseError, match="exceeds maximum size"):
            parser.parse(f, config)

    def test_utf8_with_bom(
        self, parser: MarkdownParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        f = tmp_path / "bom.md"
        f.write_bytes(b"\xef\xbb\xbf# Hello BOM\n")
        result = parser.parse(f, config)
        assert "Hello BOM" in result.content

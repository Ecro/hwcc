"""Tests for hwcc.ingest.text — TextParser."""

from __future__ import annotations

from pathlib import Path

import pytest

from hwcc.config import HwccConfig
from hwcc.exceptions import ParseError
from hwcc.ingest.text import TextParser
from hwcc.types import ParseResult

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_TXT = FIXTURE_DIR / "sample.txt"


@pytest.fixture
def parser() -> TextParser:
    return TextParser()


@pytest.fixture
def config() -> HwccConfig:
    return HwccConfig()


@pytest.fixture
def result(parser: TextParser, config: HwccConfig) -> ParseResult:
    """Parse the sample text once, shared across tests."""
    return parser.parse(SAMPLE_TXT, config)


# ── ParseResult fields ─────────────────────────────────────────────


class TestParseResultFields:
    def test_returns_parse_result(self, result: ParseResult) -> None:
        assert isinstance(result, ParseResult)

    def test_doc_type_is_text(self, result: ParseResult) -> None:
        assert result.doc_type == "text"

    def test_doc_id_follows_stem_txt_pattern(self, result: ParseResult) -> None:
        assert result.doc_id == "sample_txt"

    def test_source_path_matches_input(self, result: ParseResult) -> None:
        assert result.source_path == str(SAMPLE_TXT)

    def test_content_is_non_empty(self, result: ParseResult) -> None:
        assert len(result.content) > 0

    def test_title_from_first_line(self, result: ParseResult) -> None:
        assert result.title == "STM32F407 Errata Summary"

    def test_no_metadata(self, result: ParseResult) -> None:
        assert result.metadata == ()


# ── Content preservation ───────────────────────────────────────────


class TestContentPreservation:
    def test_preserves_content_text(self, result: ParseResult) -> None:
        assert "SPI CRC calculation" in result.content
        assert "analog noise filter" in result.content

    def test_preserves_special_characters(self, result: ParseResult) -> None:
        assert "µs" in result.content
        assert "°C" in result.content
        assert "Ω" in result.content


# ── Whitespace normalization ───────────────────────────────────────


class TestWhitespaceNormalization:
    def test_collapses_excessive_blank_lines(
        self, parser: TextParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        f = tmp_path / "gaps.txt"
        f.write_text("line1\n\n\n\n\nline2\n", encoding="utf-8")
        result = parser.parse(f, config)
        assert "\n\n\n" not in result.content
        assert "line1\n\nline2" in result.content

    def test_strips_trailing_whitespace(
        self, parser: TextParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        f = tmp_path / "trailing.txt"
        f.write_text("hello   \nworld  \n", encoding="utf-8")
        result = parser.parse(f, config)
        for line in result.content.split("\n"):
            assert line == line.rstrip(), f"Trailing whitespace on: {line!r}"


# ── Title extraction ──────────────────────────────────────────────


class TestTitleExtraction:
    def test_first_non_empty_line_as_title(self, result: ParseResult) -> None:
        assert result.title == "STM32F407 Errata Summary"

    def test_skips_leading_blank_lines(
        self, parser: TextParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        f = tmp_path / "blanks.txt"
        f.write_text("\n\n\nActual title\nBody text\n", encoding="utf-8")
        result = parser.parse(f, config)
        assert result.title == "Actual title"

    def test_filename_stem_when_whitespace_only(
        self, parser: TextParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        f = tmp_path / "whitespace_only.txt"
        f.write_text("   \n\n   \n", encoding="utf-8")
        result = parser.parse(f, config)
        assert result.title == "whitespace_only"


# ── Extension support ──────────────────────────────────────────────


class TestExtensions:
    def test_supported_extensions(self, parser: TextParser) -> None:
        exts = parser.supported_extensions()
        assert ".txt" in exts
        assert ".text" in exts

    def test_can_parse_txt_file(self, parser: TextParser, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.touch()
        assert parser.can_parse(f) is True

    def test_cannot_parse_md_file(self, parser: TextParser, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.touch()
        assert parser.can_parse(f) is False


# ── Error handling ─────────────────────────────────────────────────


class TestErrorHandling:
    def test_raises_parse_error_for_missing_file(
        self, parser: TextParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nonexistent.txt"
        with pytest.raises(ParseError, match="not found"):
            parser.parse(missing, config)

    def test_raises_parse_error_for_directory(
        self, parser: TextParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        with pytest.raises(ParseError, match="Not a file"):
            parser.parse(tmp_path, config)

    def test_raises_parse_error_for_oversized_file(
        self,
        parser: TextParser,
        config: HwccConfig,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import hwcc.ingest.text as txt_mod

        monkeypatch.setattr(txt_mod, "MAX_FILE_SIZE", 10)
        f = tmp_path / "big.txt"
        f.write_text("x" * 20, encoding="utf-8")
        with pytest.raises(ParseError, match="exceeds maximum size"):
            parser.parse(f, config)

    def test_empty_file_returns_empty_content(
        self, parser: TextParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        result = parser.parse(f, config)
        assert result.content == ""
        assert result.doc_type == "text"

    def test_utf8_with_bom(self, parser: TextParser, config: HwccConfig, tmp_path: Path) -> None:
        f = tmp_path / "bom.txt"
        f.write_bytes(b"\xef\xbb\xbfHello BOM\n")
        result = parser.parse(f, config)
        assert "Hello BOM" in result.content

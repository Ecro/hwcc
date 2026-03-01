"""Tests for hwcc.ingest.pdf — PdfParser."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hwcc.config import HwccConfig
from hwcc.exceptions import ParseError
from hwcc.ingest.pdf import PdfParser, _build_font_map, _render_table
from hwcc.types import ParseResult

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PDF = FIXTURE_DIR / "sample.pdf"


@pytest.fixture
def parser() -> PdfParser:
    return PdfParser()


@pytest.fixture
def config() -> HwccConfig:
    return HwccConfig()


@pytest.fixture
def result(parser: PdfParser, config: HwccConfig) -> ParseResult:
    """Parse the sample PDF once, shared across tests."""
    return parser.parse(SAMPLE_PDF, config)


# ── ParseResult fields ─────────────────────────────────────────────


class TestParseResultFields:
    def test_returns_parse_result(self, result: ParseResult):
        assert isinstance(result, ParseResult)

    def test_doc_type_is_pdf(self, result: ParseResult):
        assert result.doc_type == "pdf"

    def test_doc_id_from_filename(self, result: ParseResult):
        assert "sample" in result.doc_id
        assert result.doc_id.endswith("_pdf")

    def test_title_from_metadata(self, result: ParseResult):
        assert result.title == "TESTCHIP Datasheet"

    def test_source_path_set(self, result: ParseResult):
        assert result.source_path == str(SAMPLE_PDF)

    def test_content_is_nonempty_string(self, result: ParseResult):
        assert isinstance(result.content, str)
        assert len(result.content) > 100


# ── Metadata ────────────────────────────────────────────────────────


class TestMetadata:
    def test_page_count_in_metadata(self, result: ParseResult):
        meta = dict(result.metadata)
        assert meta["page_count"] == "2"

    def test_table_count_in_metadata(self, result: ParseResult):
        meta = dict(result.metadata)
        assert meta["table_count"] == "2"

    def test_pdf_title_in_metadata(self, result: ParseResult):
        meta = dict(result.metadata)
        assert meta["pdf_title"] == "TESTCHIP Datasheet"

    def test_pdf_author_in_metadata(self, result: ParseResult):
        meta = dict(result.metadata)
        assert meta["pdf_author"] == "TestVendor"


# ── Heading detection ───────────────────────────────────────────────


class TestHeadingDetection:
    def test_title_rendered_as_h1(self, result: ParseResult):
        assert "# TESTCHIP Datasheet" in result.content

    def test_section_rendered_as_h2(self, result: ParseResult):
        assert "## 1. SPI Peripheral" in result.content
        assert "## 2. GPIO Peripheral" in result.content

    def test_subsection_rendered_as_h3(self, result: ParseResult):
        assert "### 1.1 Register Map" in result.content
        assert "### 2.1 Electrical Characteristics" in result.content

    def test_heading_hierarchy_order(self, result: ParseResult):
        """Larger fonts get higher-level headings."""
        h1_pos = result.content.index("# TESTCHIP Datasheet")
        h2_pos = result.content.index("## 1. SPI Peripheral")
        h3_pos = result.content.index("### 1.1 Register Map")
        assert h1_pos < h2_pos < h3_pos

    def test_body_text_not_rendered_as_heading(self, result: ParseResult):
        # Body text at size 10 should NOT be a heading
        assert "# The SPI peripheral" not in result.content
        assert "# It provides master" not in result.content


# ── Table extraction ────────────────────────────────────────────────


class TestTableExtraction:
    def test_register_table_present(self, result: ParseResult):
        assert "| Register" in result.content
        assert "| CR1" in result.content

    def test_register_table_has_separator(self, result: ParseResult):
        """Markdown tables must have a |---|---| separator row."""
        assert re.search(r"\|[-: ]+\|[-: ]+\|", result.content)

    def test_register_table_all_rows(self, result: ParseResult):
        for reg in ["CR1", "CR2", "SR", "DR"]:
            assert f"| {reg}" in result.content

    def test_electrical_table_present(self, result: ParseResult):
        assert "| Parameter" in result.content
        assert "| VIH" in result.content
        assert "| IOH" in result.content

    def test_table_content_not_duplicated_in_body(self, result: ParseResult):
        """Table text should NOT appear as body paragraphs outside the table."""
        # Table cell content like "Control register 1" should only be in the table,
        # not duplicated as body text
        ctrl_reg_lines = [
            line
            for line in result.content.split("\n")
            if "Control register 1" in line and not line.strip().startswith("|")
        ]
        assert len(ctrl_reg_lines) == 0


# ── Header/footer removal ──────────────────────────────────────────


class TestHeaderFooterRemoval:
    def test_page_header_stripped(self, result: ParseResult):
        """The repeating 'TestVendor — TESTCHIP' header should not be in content."""
        # The header uses a special dot character, so check for the vendor name
        # appearing as standalone body text (not inside a heading)
        lines = result.content.split("\n")
        vendor_only_lines = [
            line
            for line in lines
            if "TestVendor" in line
            and not line.strip().startswith("#")
            and not line.strip().startswith("|")
        ]
        assert len(vendor_only_lines) == 0

    def test_page_footer_stripped(self, result: ParseResult):
        assert "Page 1 of 2" not in result.content
        assert "Page 2 of 2" not in result.content


# ── Body text ───────────────────────────────────────────────────────


class TestBodyText:
    def test_body_paragraph_preserved(self, result: ParseResult):
        assert "full-duplex synchronous serial communication" in result.content

    def test_body_after_table_preserved(self, result: ParseResult):
        assert "SPI clock phase and polarity" in result.content

    def test_page2_body_preserved(self, result: ParseResult):
        assert "16 individually configurable I/O pins" in result.content

    def test_page2_body_after_table(self, result: ParseResult):
        assert "5V tolerant" in result.content


# ── Extensions and can_parse ────────────────────────────────────────


class TestExtensions:
    def test_supported_extensions(self, parser: PdfParser):
        assert parser.supported_extensions() == frozenset({".pdf"})

    def test_can_parse_pdf(self, parser: PdfParser):
        assert parser.can_parse(Path("datasheet.pdf"))

    def test_can_parse_pdf_uppercase(self, parser: PdfParser):
        assert parser.can_parse(Path("DATASHEET.PDF"))

    def test_cannot_parse_svd(self, parser: PdfParser):
        assert not parser.can_parse(Path("chip.svd"))

    def test_cannot_parse_txt(self, parser: PdfParser):
        assert not parser.can_parse(Path("readme.txt"))


# ── Error handling ──────────────────────────────────────────────────


class TestErrorHandling:
    def test_nonexistent_file_raises_parse_error(self, parser: PdfParser):
        config = HwccConfig()
        with pytest.raises(ParseError, match="not found"):
            parser.parse(Path("/nonexistent/file.pdf"), config)

    def test_non_pdf_file_raises_parse_error(self, parser: PdfParser, tmp_path: Path):
        config = HwccConfig()
        fake = tmp_path / "not_a_pdf.pdf"
        fake.write_text("This is not a PDF")
        with pytest.raises(ParseError, match="not a valid PDF"):
            parser.parse(fake, config)

    def test_oversized_file_raises_parse_error(
        self, parser: PdfParser, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        config = HwccConfig()
        fake = tmp_path / "big.pdf"
        fake.write_bytes(b"%PDF-1.4 " + b"\0" * 100)
        monkeypatch.setattr(PdfParser, "MAX_FILE_SIZE", 50)
        with pytest.raises(ParseError, match="exceeds maximum"):
            parser.parse(fake, config)

    def test_corrupt_pdf_raises_parse_error(self, parser: PdfParser, tmp_path: Path):
        config = HwccConfig()
        corrupt = tmp_path / "corrupt.pdf"
        corrupt.write_bytes(b"%PDF-1.4 this is not a real pdf")
        with pytest.raises(ParseError):
            parser.parse(corrupt, config)


# ── _render_table helper ────────────────────────────────────────────


class TestRenderTable:
    def test_basic_table(self):
        data = [["Name", "Value"], ["A", "1"], ["B", "2"]]
        result = _render_table(data)
        assert "| Name | Value |" in result
        assert "| --- | --- |" in result
        assert "| A | 1 |" in result
        assert "| B | 2 |" in result

    def test_none_cells_become_empty(self):
        data = [["X", "Y"], [None, "1"], ["2", None]]
        result = _render_table(data)
        assert "|  | 1 |" in result
        assert "| 2 |  |" in result

    def test_empty_table_returns_empty(self):
        assert _render_table([]) == ""

    def test_single_row_is_header_only(self):
        data = [["Col1", "Col2"]]
        result = _render_table(data)
        assert "| Col1 | Col2 |" in result
        assert "| --- | --- |" in result

    def test_whitespace_stripped_in_cells(self):
        data = [["A", "B"], ["  hello  ", "\nworld\n"]]
        result = _render_table(data)
        assert "| hello | world |" in result

    def test_pipe_characters_escaped(self):
        data = [["Mode", "Value"], ["I2C | SPI", "0|1"]]
        result = _render_table(data)
        assert r"I2C \| SPI" in result
        assert r"0\|1" in result


# ── _build_font_map helper ──────────────────────────────────────────


class TestBuildFontMap:
    def test_single_body_font(self):
        # Only one font size — it's body text, no headings
        histogram = {(10.0, False): 100}
        font_map = _build_font_map(histogram)
        assert 10.0 not in font_map  # body text isn't mapped to a heading

    def test_two_tiers(self):
        # Body at 10pt (most common), heading at 18pt
        histogram = {(10.0, False): 100, (18.0, True): 5}
        font_map = _build_font_map(histogram)
        assert font_map[18.0] == 1  # largest bold = h1

    def test_three_tiers(self):
        # Body=10, h2=14, h1=18
        histogram = {
            (10.0, False): 100,
            (14.0, True): 10,
            (18.0, True): 5,
        }
        font_map = _build_font_map(histogram)
        assert font_map[18.0] == 1  # h1
        assert font_map[14.0] == 2  # h2

    def test_four_tiers(self):
        # Body=10, h3=14, h2=18, h1=24
        histogram = {
            (10.0, False): 200,
            (14.0, True): 10,
            (18.0, True): 5,
            (24.0, True): 2,
        }
        font_map = _build_font_map(histogram)
        assert font_map[24.0] == 1  # h1
        assert font_map[18.0] == 2  # h2
        assert font_map[14.0] == 3  # h3

    def test_non_bold_large_font_as_heading(self):
        # Large non-bold text should still be treated as heading
        histogram = {(10.0, False): 100, (24.0, False): 2}
        font_map = _build_font_map(histogram)
        assert font_map[24.0] == 1


# ── Edge cases ──────────────────────────────────────────────────────


class TestPageMarkers:
    def test_page_markers_present(self, result: ParseResult):
        """Each page should have a <!-- PAGE:N --> marker."""
        assert "<!-- PAGE:1 -->" in result.content
        assert "<!-- PAGE:2 -->" in result.content

    def test_page_markers_before_content(self, result: ParseResult):
        """Page markers should precede their page's content."""
        marker_pos = result.content.index("<!-- PAGE:1 -->")
        spi_pos = result.content.index("## 1. SPI Peripheral")
        assert marker_pos < spi_pos

        marker2_pos = result.content.index("<!-- PAGE:2 -->")
        gpio_pos = result.content.index("## 2. GPIO Peripheral")
        assert marker2_pos < gpio_pos


class TestEdgeCases:
    def test_section_continuity_across_pages(self, result: ParseResult):
        """Section 1 is on page 1, section 2 on page 2 — both present."""
        assert "## 1. SPI Peripheral" in result.content
        assert "## 2. GPIO Peripheral" in result.content
        # Section 2 comes after section 1
        pos1 = result.content.index("## 1. SPI Peripheral")
        pos2 = result.content.index("## 2. GPIO Peripheral")
        assert pos1 < pos2

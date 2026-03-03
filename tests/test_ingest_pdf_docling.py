"""Tests for DoclingPdfParser."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hwcc.config import HwccConfig, default_config
from hwcc.exceptions import ParseError
from hwcc.vision.none import NullVisionProvider


def _make_config() -> HwccConfig:
    cfg = default_config()
    cfg.ingest.pdf_backend = "docling"
    return cfg


class TestDoclingPdfParserImport:
    def test_import_succeeds(self) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        assert DoclingPdfParser is not None

    def test_supported_extensions_returns_pdf(self) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        parser = DoclingPdfParser()
        assert ".pdf" in parser.supported_extensions()

    def test_can_parse_pdf_path(self, tmp_path: Path) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        parser = DoclingPdfParser()
        assert parser.can_parse(pdf) is True

    def test_cannot_parse_non_pdf(self, tmp_path: Path) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        f = tmp_path / "test.svd"
        f.write_text("content")
        parser = DoclingPdfParser()
        assert parser.can_parse(f) is False


class TestDoclingPdfParserErrors:
    def test_raises_parse_error_if_file_not_found(self) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        parser = DoclingPdfParser()
        with pytest.raises(ParseError, match="not found"):
            parser.parse(Path("/nonexistent/file.pdf"), _make_config())

    def test_raises_parse_error_if_docling_not_installed(self, tmp_path: Path) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        parser = DoclingPdfParser()
        import_err = ImportError("No module named 'docling'")
        with (
            patch("builtins.__import__", side_effect=import_err),
            pytest.raises(ParseError, match="docling"),
        ):
            parser.parse(pdf, _make_config())

    def test_falls_back_to_pdf_parser_when_fallback_enabled(
        self, tmp_path: Path
    ) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        parser = DoclingPdfParser(fallback_on_missing_dep=True)

        mock_result = MagicMock()
        mock_result.content = "fallback text content"

        with patch("hwcc.ingest.pdf_docling._docling_available", return_value=False), patch(
            "hwcc.ingest.pdf.PdfParser.parse", return_value=mock_result
        ) as mock_parse:
            result = parser.parse(pdf, _make_config())

        mock_parse.assert_called_once()
        assert result.content == "fallback text content"


class TestClassifyFigureType:
    def test_timing_keywords(self) -> None:
        from hwcc.ingest.pdf_docling import _classify_figure_type

        assert _classify_figure_type("SPI timing diagram CPOL CPHA") == "timing_diagram"
        assert _classify_figure_type("CLK waveform setup time") == "timing_diagram"
        assert _classify_figure_type("tSU tHD clock signal") == "timing_diagram"

    def test_block_diagram_keywords(self) -> None:
        from hwcc.ingest.pdf_docling import _classify_figure_type

        assert _classify_figure_type("block diagram AHB bus") == "block_diagram"
        assert _classify_figure_type("peripheral architecture overview") == "block_diagram"
        assert _classify_figure_type("APB bridge topology") == "block_diagram"

    def test_pinout_keywords(self) -> None:
        from hwcc.ingest.pdf_docling import _classify_figure_type

        assert _classify_figure_type("pin assignment LQFP package") == "pinout"
        assert _classify_figure_type("pinout diagram BGA") == "pinout"
        assert _classify_figure_type("QFP 64-pin package") == "pinout"

    def test_schematic_keywords(self) -> None:
        from hwcc.ingest.pdf_docling import _classify_figure_type

        assert _classify_figure_type("circuit schematic transistor") == "schematic_figure"
        assert _classify_figure_type("MOSFET gate driver circuit") == "schematic_figure"

    def test_unknown_returns_figure(self) -> None:
        from hwcc.ingest.pdf_docling import _classify_figure_type

        assert _classify_figure_type("") == "figure"
        assert _classify_figure_type("some unrelated text") == "figure"
        assert _classify_figure_type("graph of temperature vs voltage") == "figure"

    def test_case_insensitive(self) -> None:
        from hwcc.ingest.pdf_docling import _classify_figure_type

        assert _classify_figure_type("TIMING DIAGRAM") == "timing_diagram"
        assert _classify_figure_type("Block Diagram") == "block_diagram"


class TestRenderFigureBlock:
    def test_no_caption_no_ai_desc(self) -> None:
        from hwcc.ingest.pdf_docling import _render_figure_block

        md = _render_figure_block(
            page=5,
            figure_type="timing_diagram",
            caption="",
            ai_description="",
            bbox=(10, 20, 200, 150),
        )
        assert "<!-- FIGURE:" in md
        assert "page 5" in md
        assert "timing_diagram" in md
        assert "> **[Visual:" in md

    def test_with_caption(self) -> None:
        from hwcc.ingest.pdf_docling import _render_figure_block

        md = _render_figure_block(
            page=12,
            figure_type="timing_diagram",
            caption="Figure 8. SPI bus timing.",
            ai_description="",
            bbox=(0, 0, 100, 100),
        )
        assert "Figure 8. SPI bus timing." in md
        assert "*Caption:" in md

    def test_with_ai_description(self) -> None:
        from hwcc.ingest.pdf_docling import _render_figure_block

        md = _render_figure_block(
            page=3,
            figure_type="block_diagram",
            caption="Figure 3. DMA controller.",
            ai_description="Block diagram showing DMA controller with 8 channels.",
            bbox=(0, 0, 100, 100),
        )
        assert "*AI Description:" in md
        assert "DMA controller" in md

    def test_output_is_valid_markdown_blockquote(self) -> None:
        from hwcc.ingest.pdf_docling import _render_figure_block

        md = _render_figure_block(
            page=1,
            figure_type="figure",
            caption="Test caption.",
            ai_description="",
            bbox=(0, 0, 50, 50),
        )
        lines = md.strip().split("\n")
        # HTML comment line + blockquote lines
        assert lines[0].startswith("<!--")
        blockquote_lines = [line for line in lines if line.strip()]
        assert any(line.startswith(">") for line in blockquote_lines)


class TestDoclingPdfParserParse:
    """Tests using mocked Docling output."""

    def _make_mock_docling(
        self,
        text_items: list[dict],
        figure_items: list[dict] | None = None,
    ) -> MagicMock:
        """Build a mock Docling ConversionResult."""
        mock_result = MagicMock()
        mock_result.status = MagicMock()
        mock_result.status.name = "SUCCESS"

        all_items = []

        for item in text_items:
            mock_item = MagicMock()
            mock_item.label = MagicMock()
            mock_item.label.name = item.get("label", "TEXT")
            mock_item.text = item.get("text", "")
            mock_item.prov = [MagicMock()]
            mock_item.prov[0].page_no = item.get("page", 1)
            mock_item.prov[0].bbox = MagicMock()
            mock_item.prov[0].bbox.t = item.get("y", 100.0)
            mock_item.prov[0].bbox.l = 10.0
            mock_item.prov[0].bbox.r = 500.0
            mock_item.prov[0].bbox.b = item.get("y", 100.0) + 20.0
            all_items.append(mock_item)

        for item in (figure_items or []):
            mock_fig = MagicMock()
            mock_fig.label = MagicMock()
            mock_fig.label.name = "PICTURE"
            mock_fig.text = ""
            mock_fig.prov = [MagicMock()]
            mock_fig.prov[0].page_no = item.get("page", 1)
            mock_fig.prov[0].bbox = MagicMock()
            mock_fig.prov[0].bbox.t = item.get("y", 200.0)
            mock_fig.prov[0].bbox.l = 10.0
            mock_fig.prov[0].bbox.r = 400.0
            mock_fig.prov[0].bbox.b = item.get("y", 200.0) + 100.0
            mock_fig.caption_text = MagicMock(return_value=item.get("caption", ""))
            mock_fig.get_image = MagicMock(return_value=MagicMock())
            all_items.append(mock_fig)

        mock_result.document = MagicMock()
        mock_result.document.iterate_items = MagicMock(return_value=iter(
            [(item, None) for item in all_items]
        ))
        mock_result.document.export_to_markdown = MagicMock(return_value="")

        return mock_result

    def _mock_docling_converter(self, mock_result: MagicMock) -> MagicMock:
        mock_converter_cls = MagicMock()
        mock_converter = MagicMock()
        mock_converter.convert.return_value = mock_result
        mock_converter_cls.return_value = mock_converter
        return mock_converter_cls

    def test_parse_returns_parse_result(self, tmp_path: Path) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser
        from hwcc.types import ParseResult

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake content")

        mock_result = self._make_mock_docling(
            [{"label": "TEXT", "text": "Register description", "page": 1, "y": 50.0}]
        )

        with patch("hwcc.ingest.pdf_docling._docling_available", return_value=True), patch(
            "hwcc.ingest.pdf_docling.DocumentConverter",
            self._mock_docling_converter(mock_result),
        ):
            parser = DoclingPdfParser()
            result = parser.parse(pdf, _make_config())

        assert isinstance(result, ParseResult)
        assert result.doc_type == "pdf"
        assert result.source_path == str(pdf)

    def test_parse_includes_text_content(self, tmp_path: Path) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        mock_result = self._make_mock_docling(
            [{"label": "TEXT", "text": "SPI register description", "page": 1, "y": 50.0}]
        )

        with patch("hwcc.ingest.pdf_docling._docling_available", return_value=True), patch(
            "hwcc.ingest.pdf_docling.DocumentConverter",
            self._mock_docling_converter(mock_result),
        ):
            parser = DoclingPdfParser()
            result = parser.parse(pdf, _make_config())

        assert "SPI register description" in result.content

    def test_parse_inserts_figure_placeholder(self, tmp_path: Path) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        mock_result = self._make_mock_docling(
            text_items=[{"label": "TEXT", "text": "Before figure", "page": 1, "y": 50.0}],
            figure_items=[{"page": 1, "y": 150.0, "caption": "Figure 3. SPI timing."}],
        )

        with patch("hwcc.ingest.pdf_docling._docling_available", return_value=True), patch(
            "hwcc.ingest.pdf_docling.DocumentConverter",
            self._mock_docling_converter(mock_result),
        ):
            parser = DoclingPdfParser(vision_provider=NullVisionProvider())
            result = parser.parse(pdf, _make_config())

        assert "<!-- FIGURE:" in result.content
        assert "Figure 3. SPI timing." in result.content

    def test_parse_classifies_timing_figure(self, tmp_path: Path) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        mock_result = self._make_mock_docling(
            text_items=[],
            figure_items=[{"page": 1, "y": 100.0, "caption": "Figure 1. CLK timing waveform."}],
        )

        with patch("hwcc.ingest.pdf_docling._docling_available", return_value=True), patch(
            "hwcc.ingest.pdf_docling.DocumentConverter",
            self._mock_docling_converter(mock_result),
        ):
            parser = DoclingPdfParser(vision_provider=NullVisionProvider())
            result = parser.parse(pdf, _make_config())

        assert "timing_diagram" in result.content

    def test_parse_calls_vision_provider_for_figures(self, tmp_path: Path) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        mock_result = self._make_mock_docling(
            text_items=[],
            figure_items=[{"page": 1, "y": 100.0, "caption": "Figure 1. SPI timing."}],
        )

        mock_vision = MagicMock(spec=NullVisionProvider)
        mock_vision.caption_image.return_value = "Four signal traces: CLK, CS, MOSI, MISO."
        mock_vision.is_available.return_value = True

        with patch("hwcc.ingest.pdf_docling._docling_available", return_value=True), patch(
            "hwcc.ingest.pdf_docling.DocumentConverter",
            self._mock_docling_converter(mock_result),
        ):
            parser = DoclingPdfParser(vision_provider=mock_vision)
            result = parser.parse(pdf, _make_config())

        mock_vision.caption_image.assert_called_once()
        assert "Four signal traces" in result.content

    def test_parse_passes_caption_as_context_to_vision(self, tmp_path: Path) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        mock_result = self._make_mock_docling(
            text_items=[],
            figure_items=[{"page": 2, "y": 80.0, "caption": "Figure 5. I2C bus timing."}],
        )

        mock_vision = MagicMock(spec=NullVisionProvider)
        mock_vision.caption_image.return_value = ""
        mock_vision.is_available.return_value = True

        with patch("hwcc.ingest.pdf_docling._docling_available", return_value=True), patch(
            "hwcc.ingest.pdf_docling.DocumentConverter",
            self._mock_docling_converter(mock_result),
        ):
            parser = DoclingPdfParser(vision_provider=mock_vision)
            parser.parse(pdf, _make_config())

        call_kwargs = mock_vision.caption_image.call_args
        context_arg = call_kwargs[1].get("context") or call_kwargs[0][1]
        assert "I2C bus timing" in context_arg

    def test_metadata_includes_figure_count(self, tmp_path: Path) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        mock_result = self._make_mock_docling(
            text_items=[{"label": "TEXT", "text": "text", "page": 1, "y": 10.0}],
            figure_items=[
                {"page": 1, "y": 100.0, "caption": "Figure 1"},
                {"page": 2, "y": 50.0, "caption": "Figure 2"},
            ],
        )

        with patch("hwcc.ingest.pdf_docling._docling_available", return_value=True), patch(
            "hwcc.ingest.pdf_docling.DocumentConverter",
            self._mock_docling_converter(mock_result),
        ):
            parser = DoclingPdfParser(vision_provider=NullVisionProvider())
            result = parser.parse(pdf, _make_config())

        meta = dict(result.metadata)
        assert meta.get("figure_count") == "2"

    def test_parse_renders_table_items(self, tmp_path: Path) -> None:
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        mock_table = MagicMock()
        mock_table.label = MagicMock()
        mock_table.label.name = "TABLE"
        mock_table.text = ""
        mock_table.prov = [MagicMock()]
        mock_table.prov[0].page_no = 1
        mock_table.prov[0].bbox = MagicMock()
        mock_table.prov[0].bbox.t = 80.0
        mock_table.prov[0].bbox.l = 10.0
        mock_table.prov[0].bbox.r = 400.0
        mock_table.prov[0].bbox.b = 200.0
        mock_table.export_to_markdown = MagicMock(return_value="| A | B |\n|---|---|\n| 1 | 2 |")

        mock_result = MagicMock()
        mock_result.document = MagicMock()
        mock_result.document.iterate_items = MagicMock(
            return_value=iter([(mock_table, None)])
        )

        mock_converter_cls = MagicMock()
        mock_converter = MagicMock()
        mock_converter.convert.return_value = mock_result
        mock_converter_cls.return_value = mock_converter

        with patch("hwcc.ingest.pdf_docling._docling_available", return_value=True), patch(
            "hwcc.ingest.pdf_docling.DocumentConverter", mock_converter_cls
        ):
            parser = DoclingPdfParser(vision_provider=NullVisionProvider())
            result = parser.parse(pdf, _make_config())

        assert "| A | B |" in result.content

    def test_parse_falls_back_to_null_when_vision_unavailable(self, tmp_path: Path) -> None:
        """When vision provider is_available() returns False, parser must fall back
        to NullVisionProvider and NOT call caption_image() on the unavailable provider.
        This is the C2 fix: is_available() check before processing figures.
        """
        from hwcc.ingest.pdf_docling import DoclingPdfParser

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        mock_result = self._make_mock_docling(
            text_items=[],
            figure_items=[{"page": 1, "y": 100.0, "caption": "Figure 1. SPI timing."}],
        )

        mock_vision = MagicMock(spec=NullVisionProvider)
        mock_vision.is_available.return_value = False  # provider not usable
        mock_vision.caption_image.return_value = "should not be called"

        with patch("hwcc.ingest.pdf_docling._docling_available", return_value=True), patch(
            "hwcc.ingest.pdf_docling.DocumentConverter",
            self._mock_docling_converter(mock_result),
        ):
            parser = DoclingPdfParser(vision_provider=mock_vision)
            result = parser.parse(pdf, _make_config())

        # caption_image must NOT be called on the unavailable provider
        mock_vision.caption_image.assert_not_called()
        # Figure placeholder still appears (via NullVisionProvider fallback)
        assert "<!-- FIGURE:" in result.content
        assert "should not be called" not in result.content

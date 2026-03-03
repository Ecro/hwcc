"""Tests for config-driven PDF parser selection in the CLI pipeline."""

from __future__ import annotations

from hwcc.config import default_config
from hwcc.ingest.pdf import PdfParser
from hwcc.ingest.pdf_docling import DoclingPdfParser


class TestGetPdfParser:
    def test_default_config_returns_pdf_parser(self) -> None:
        from hwcc.cli import _get_pdf_parser

        cfg = default_config()
        parser = _get_pdf_parser(cfg)
        assert isinstance(parser, PdfParser)

    def test_pymupdf_backend_returns_pdf_parser(self) -> None:
        from hwcc.cli import _get_pdf_parser

        cfg = default_config()
        cfg.ingest.pdf_backend = "pymupdf"
        parser = _get_pdf_parser(cfg)
        assert isinstance(parser, PdfParser)

    def test_docling_backend_returns_docling_parser(self) -> None:
        from hwcc.cli import _get_pdf_parser

        cfg = default_config()
        cfg.ingest.pdf_backend = "docling"
        parser = _get_pdf_parser(cfg)
        assert isinstance(parser, DoclingPdfParser)

    def test_docling_backend_passes_vision_provider(self) -> None:
        from hwcc.cli import _get_pdf_parser
        from hwcc.vision.none import NullVisionProvider

        cfg = default_config()
        cfg.ingest.pdf_backend = "docling"
        cfg.vision.provider = "none"
        parser = _get_pdf_parser(cfg)
        assert isinstance(parser, DoclingPdfParser)
        assert isinstance(parser.vision_provider, NullVisionProvider)

    def test_unknown_backend_falls_back_to_pdf_parser(self) -> None:
        from hwcc.cli import _get_pdf_parser

        cfg = default_config()
        cfg.ingest.pdf_backend = "unknown_backend"
        parser = _get_pdf_parser(cfg)
        assert isinstance(parser, PdfParser)

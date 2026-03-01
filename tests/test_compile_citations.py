"""Tests for hwcc.compile.citations — source provenance formatting."""

from __future__ import annotations

import pytest

from hwcc.compile.citations import build_title_map, format_citation
from hwcc.manifest import DocumentEntry, Manifest
from hwcc.types import ChunkMetadata

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def title_map() -> dict[str, str]:
    """Standard title map for testing."""
    return {
        "rm0090_pdf": "RM0090",
        "stm32f407_svd": "STM32F407",
        "getting_started_md": "getting started",
    }


def _meta(
    doc_id: str = "rm0090_pdf",
    doc_type: str = "pdf",
    section_path: str = "",
    page: int = 0,
    chip: str = "",
) -> ChunkMetadata:
    """Helper to create ChunkMetadata with common defaults."""
    return ChunkMetadata(
        doc_id=doc_id,
        doc_type=doc_type,
        section_path=section_path,
        page=page,
        chip=chip,
    )


# ---------------------------------------------------------------------------
# format_citation
# ---------------------------------------------------------------------------


class TestFormatCitation:
    def test_pdf_with_section_and_page(self, title_map):
        meta = _meta(section_path="RM0090 > SPI1 > Configuration", page=868)
        result = format_citation(meta, title_map)
        assert result == "*Source: RM0090, §SPI1 > Configuration, p.868*"

    def test_pdf_with_section_no_page(self, title_map):
        meta = _meta(section_path="RM0090 > GPIO", page=0)
        result = format_citation(meta, title_map)
        assert result == "*Source: RM0090, §RM0090 > GPIO*"

    def test_pdf_with_page_no_section(self, title_map):
        meta = _meta(section_path="", page=42)
        result = format_citation(meta, title_map)
        assert result == "*Source: RM0090, p.42*"

    def test_svd_minimal(self, title_map):
        meta = _meta(doc_id="stm32f407_svd", doc_type="svd")
        result = format_citation(meta, title_map)
        assert result == "*Source: STM32F407*"

    def test_svd_with_section_path(self, title_map):
        meta = _meta(
            doc_id="stm32f407_svd",
            doc_type="svd",
            section_path="STM32F407 Register Map > SPI1",
        )
        result = format_citation(meta, title_map)
        assert result == "*Source: STM32F407, §STM32F407 Register Map > SPI1*"

    def test_markdown_doc(self, title_map):
        meta = _meta(
            doc_id="getting_started_md",
            doc_type="markdown",
            section_path="Getting Started > Installation",
        )
        result = format_citation(meta, title_map)
        assert result == "*Source: getting started, §Getting Started > Installation*"

    def test_unknown_doc_id_falls_back(self, title_map):
        meta = _meta(doc_id="unknown_doc", doc_type="pdf", page=1)
        result = format_citation(meta, title_map)
        assert result == "*Source: unknown_doc, p.1*"

    def test_section_path_truncation(self, title_map):
        """Deep section paths truncated to last 2 elements."""
        meta = _meta(section_path="Root > Level1 > Level2 > Level3", page=10)
        result = format_citation(meta, title_map)
        assert "§Level2 > Level3" in result
        assert "Root" not in result

    def test_section_path_two_elements_not_truncated(self, title_map):
        """Two-element paths should not be truncated."""
        meta = _meta(section_path="SPI > Configuration", page=5)
        result = format_citation(meta, title_map)
        assert "§SPI > Configuration" in result

    def test_empty_title_map(self):
        meta = _meta(doc_id="some_doc", doc_type="pdf", page=1)
        result = format_citation(meta, {})
        assert result == "*Source: some_doc, p.1*"


# ---------------------------------------------------------------------------
# build_title_map
# ---------------------------------------------------------------------------


class TestBuildTitleMap:
    def test_builds_from_manifest(self):
        manifest = Manifest()
        manifest.add_document(DocumentEntry(
            id="rm0090_pdf",
            path="/docs/RM0090.pdf",
            doc_type="pdf",
            hash="abc123",
            added="2026-01-01",
            chunks=50,
        ))
        manifest.add_document(DocumentEntry(
            id="stm32_svd",
            path="/docs/stm32f407.svd",
            doc_type="svd",
            hash="def456",
            added="2026-01-01",
            chunks=100,
        ))

        result = build_title_map(manifest)
        assert result["rm0090_pdf"] == "RM0090"
        assert result["stm32_svd"] == "stm32f407"

    def test_empty_manifest(self):
        manifest = Manifest()
        result = build_title_map(manifest)
        assert result == {}

    def test_hyphens_and_underscores_replaced(self):
        manifest = Manifest()
        manifest.add_document(DocumentEntry(
            id="my_doc",
            path="/docs/my-cool_datasheet.pdf",
            doc_type="pdf",
            hash="aaa",
            added="2026-01-01",
        ))

        result = build_title_map(manifest)
        assert result["my_doc"] == "my cool datasheet"

"""PDF parser — extracts text and tables from hardware datasheets.

Two-pass architecture for quality-first extraction:
1. Font analysis pass — scan all pages to detect heading font size tiers
2. Extraction pass — text (PyMuPDF) + tables (pdfplumber) → structured markdown

This parser is 100% deterministic — no LLM dependency.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hwcc.exceptions import ParseError
from hwcc.ingest.base import BaseParser
from hwcc.types import ParseResult

if TYPE_CHECKING:
    from pathlib import Path

    from hwcc.config import HwccConfig

__all__ = ["PdfParser"]

logger = logging.getLogger(__name__)

# PyMuPDF text extraction flags: preserve ligatures + whitespace, suppress images
_TEXT_FLAGS = 11


class PdfParser(BaseParser):
    """Parser for PDF documents (datasheets, reference manuals, app notes).

    Two-pass architecture for quality-first extraction:
    1. Font analysis pass — detect heading font size tiers
    2. Extraction pass — text + tables → structured markdown
    """

    HEADER_MARGIN: int = 60
    FOOTER_MARGIN: int = 50
    MAX_FILE_SIZE: int = 200 * 1024 * 1024  # 200 MB

    def parse(self, path: Path, config: HwccConfig) -> ParseResult:
        """Parse a PDF file into a ParseResult with structured markdown.

        Args:
            path: Path to the .pdf file.
            config: Project configuration.

        Returns:
            ParseResult with clean markdown content and metadata.

        Raises:
            ParseError: If the PDF cannot be parsed.
        """
        try:
            import pdfplumber
            import pymupdf
        except ImportError as e:
            msg = (
                "pymupdf and pdfplumber are required for PDF parsing:"
                " pip install pymupdf pdfplumber"
            )
            raise ParseError(msg) from e

        if not path.exists():
            msg = f"PDF file not found: {path.name}"
            raise ParseError(msg)

        _check_pdf_safety(path, self.MAX_FILE_SIZE)

        logger.info("Parsing PDF file: %s", path)

        try:
            mu_doc = pymupdf.open(str(path))
        except (RuntimeError, ValueError, OSError) as e:
            logger.debug("PDF open failure (%s): %s", type(e).__name__, e, exc_info=True)
            msg = f"Failed to open PDF file {path.name}: {e}"
            raise ParseError(msg) from e

        try:
            page_count = len(mu_doc)
            if page_count == 0:
                return ParseResult(
                    doc_id=_make_doc_id(path),
                    content="",
                    doc_type="pdf",
                    title=path.stem,
                    source_path=str(path),
                    metadata=(("page_count", "0"), ("table_count", "0")),
                )

            # Pass 1: Font analysis
            font_histogram = _scan_fonts(mu_doc, self.HEADER_MARGIN, self.FOOTER_MARGIN)
            font_map = _build_font_map(font_histogram)

            # Pass 2: Extract text + tables
            sections: list[str] = []
            total_tables = 0

            with pdfplumber.open(str(path)) as plumb_doc:
                for page_idx in range(page_count):
                    mu_page = mu_doc.load_page(page_idx)
                    plumb_page = plumb_doc.pages[page_idx]

                    page_md, table_count = _extract_page(
                        mu_page,
                        plumb_page,
                        font_map,
                        self.HEADER_MARGIN,
                        self.FOOTER_MARGIN,
                    )
                    if page_md.strip():
                        sections.append(page_md)
                    total_tables += table_count

            content = "\n\n".join(sections)

            # Metadata
            pdf_meta = mu_doc.metadata or {}
            pdf_title = pdf_meta.get("title", "") or ""
            pdf_author = pdf_meta.get("author", "") or ""
            title = pdf_title if pdf_title else path.stem

            metadata = (
                ("page_count", str(page_count)),
                ("table_count", str(total_tables)),
                ("pdf_title", pdf_title),
                ("pdf_author", pdf_author),
            )

            logger.info("Parsed %s: %d pages, %d tables", path.name, page_count, total_tables)

        finally:
            mu_doc.close()

        return ParseResult(
            doc_id=_make_doc_id(path),
            content=content,
            doc_type="pdf",
            title=title,
            source_path=str(path),
            metadata=metadata,
        )

    def supported_extensions(self) -> frozenset[str]:
        """Return supported file extensions."""
        return frozenset({".pdf"})


# ── Module-level helpers ────────────────────────────────────────────


def _make_doc_id(path: Path) -> str:
    """Generate a document ID from the file path."""
    return path.stem.lower().replace("-", "_").replace(" ", "_") + "_pdf"


def _check_pdf_safety(path: Path, max_size: int) -> None:
    """Validate PDF magic header and file size.

    Raises:
        ParseError: If the file is not a valid PDF or exceeds size limit.
    """
    file_size = path.stat().st_size
    if file_size > max_size:
        msg = f"PDF file {path.name} ({file_size} bytes) exceeds maximum size ({max_size} bytes)"
        raise ParseError(msg)

    # Check PDF magic header
    try:
        with path.open("rb") as f:
            header = f.read(5)
    except OSError as e:
        msg = f"Cannot read PDF file {path.name}: {e}"
        raise ParseError(msg) from e

    if header != b"%PDF-":
        msg = f"File {path.name} is not a valid PDF (missing %PDF- header)"
        raise ParseError(msg)


def _scan_fonts(
    doc: object,  # pymupdf.Document (stubs incomplete)
    header_margin: int,
    footer_margin: int,
) -> dict[tuple[float, bool], int]:
    """Pass 1: Scan all pages to build a font size histogram.

    Returns:
        dict mapping (font_size, is_bold) → character count.
    """
    import pymupdf

    histogram: dict[tuple[float, bool], int] = {}

    for page in doc:  # type: ignore[attr-defined]
        page_rect = page.rect
        clip = pymupdf.Rect(
            page_rect.x0,
            page_rect.y0 + header_margin,
            page_rect.x1,
            page_rect.y1 - footer_margin,
        )

        blocks = page.get_text("dict", flags=_TEXT_FLAGS, clip=clip)["blocks"]
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    font_size = round(span["size"], 1)
                    is_bold = bool(span["flags"] & 16) or "bold" in span["font"].lower()
                    text_len = len(span["text"].strip())
                    if text_len > 0:
                        key = (font_size, is_bold)
                        histogram[key] = histogram.get(key, 0) + text_len

    return histogram


def _build_font_map(
    histogram: dict[tuple[float, bool], int],
) -> dict[float, int]:
    """Convert font size histogram into font_size → heading_level mapping.

    The most common font size is body text. Font sizes significantly larger
    than body text are classified as headings, ordered by size (largest = h1).

    Args:
        histogram: mapping of (font_size, is_bold) → character count.

    Returns:
        dict mapping font_size → heading level (1=h1, 2=h2, etc.).
        Body text size is NOT included.
    """
    if not histogram:
        return {}

    # Aggregate character counts by font size (ignore bold for frequency analysis)
    size_counts: dict[float, int] = {}
    for (size, _bold), count in histogram.items():
        size_counts[size] = size_counts.get(size, 0) + count

    # Body text = most common font size
    body_size = max(size_counts, key=lambda s: size_counts[s])

    # Heading candidates: sizes larger than body, OR bold sizes equal to body
    # that have significantly fewer characters (likely sub-headings)
    heading_sizes: set[float] = set()
    for (size, is_bold), count in histogram.items():
        if size > body_size:
            heading_sizes.add(size)
        elif size == body_size and is_bold and count < size_counts[body_size] * 0.1:
            # Bold text at body size with < 10% of body chars = possible subheading
            # Skip for now — too unreliable
            pass

    if not heading_sizes:
        return {}

    # Sort heading sizes descending: largest = h1, next = h2, etc.
    sorted_sizes = sorted(heading_sizes, reverse=True)
    font_map: dict[float, int] = {}
    for level, size in enumerate(sorted_sizes, start=1):
        font_map[size] = level

    return font_map


def _extract_page(
    mu_page: object,  # pymupdf.Page (stubs incomplete)
    plumb_page: object,  # pdfplumber.page.Page
    font_map: dict[float, int],
    header_margin: int,
    footer_margin: int,
) -> tuple[str, int]:
    """Extract one page as markdown.

    Returns:
        (markdown_string, table_count)
    """
    import pymupdf

    page_rect = mu_page.rect  # type: ignore[attr-defined]
    clip = pymupdf.Rect(
        page_rect.x0,
        page_rect.y0 + header_margin,
        page_rect.x1,
        page_rect.y1 - footer_margin,
    )

    # Step A: Find tables with pdfplumber (get bboxes + data)
    tables = plumb_page.find_tables()  # type: ignore[attr-defined]
    table_rects: list[pymupdf.Rect] = []
    table_entries: list[tuple[float, str]] = []  # (y_position, markdown)

    for table in tables:
        x0, top, x1, bottom = table.bbox
        table_rects.append(pymupdf.Rect(x0, top, x1, bottom))
        data = table.extract()
        md = _render_table(data)
        if md:
            table_entries.append((top, md))

    # Step B: Extract text blocks with PyMuPDF, skipping table regions
    blocks = mu_page.get_text("dict", flags=_TEXT_FLAGS, clip=clip)["blocks"]  # type: ignore[attr-defined]
    text_entries: list[tuple[float, str]] = []  # (y_position, markdown)

    for block in blocks:
        if block["type"] != 0:
            continue

        block_rect = pymupdf.Rect(block["bbox"])

        # Skip blocks that overlap with any table bounding box
        if any(block_rect.intersects(tr) for tr in table_rects):
            continue

        # Classify and render text block
        block_md = _render_block(block, font_map)
        if block_md.strip():
            y_pos = block["bbox"][1]  # top Y coordinate
            text_entries.append((y_pos, block_md))

    # Step C: Merge text and table entries, sorted by Y position
    all_entries = text_entries + table_entries
    all_entries.sort(key=lambda entry: entry[0])

    page_md = "\n\n".join(entry[1] for entry in all_entries)
    return page_md, len(tables)


def _render_block(block: dict[str, object], font_map: dict[float, int]) -> str:
    """Render a text block as markdown (heading or paragraph)."""
    lines_data: list[dict[str, object]] = block.get("lines", [])  # type: ignore[assignment]
    if not lines_data:
        return ""

    # Collect all spans across all lines in this block
    all_text_parts: list[str] = []
    dominant_size = 0.0
    max_span_len = 0

    for line in lines_data:
        spans: list[dict[str, object]] = line.get("spans", [])  # type: ignore[assignment]
        for span in spans:
            text = str(span.get("text", "")).strip()
            if not text:
                continue
            all_text_parts.append(text)
            char_count = len(text)
            font_size = float(str(span.get("size", 0)))
            if char_count > max_span_len:
                dominant_size = round(font_size, 1)
                max_span_len = char_count

    if not all_text_parts:
        return ""

    full_text = " ".join(all_text_parts)

    # Check if this is a heading
    heading_level = font_map.get(dominant_size)
    if heading_level is not None:
        prefix = "#" * heading_level
        return f"{prefix} {full_text}"

    # Regular paragraph
    return full_text


def _render_table(table_data: list[list[str | None]]) -> str:
    """Convert table data to markdown table with header separator.

    Args:
        table_data: List of rows, each a list of cell strings (or None).

    Returns:
        Markdown table string, or empty string if no data.
    """
    if not table_data:
        return ""

    def clean_cell(cell: str | None) -> str:
        if cell is None:
            return ""
        return cell.strip().replace("\n", " ").replace("|", "\\|")

    lines: list[str] = []

    # Header row
    header = table_data[0]
    header_cells = [clean_cell(c) for c in header]
    lines.append("| " + " | ".join(header_cells) + " |")

    # Separator
    lines.append("| " + " | ".join("---" for _ in header_cells) + " |")

    # Data rows
    for row in table_data[1:]:
        cells = [clean_cell(c) for c in row]
        # Pad or truncate to match header column count
        while len(cells) < len(header_cells):
            cells.append("")
        if len(cells) > len(header_cells):
            logger.debug(
                "Table row has %d columns but header has %d — truncating",
                len(cells),
                len(header_cells),
            )
            cells = cells[: len(header_cells)]
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)

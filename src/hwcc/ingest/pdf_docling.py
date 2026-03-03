"""Docling-based PDF parser — layout-aware extraction of text, tables, and figures.

Uses IBM's Docling library for document layout detection. Identifies figures
(timing diagrams, block diagrams, pinouts) and represents them as searchable
markdown blockquotes, optionally with AI-generated captions.

Requires: pip install hwcc[docling]
Optional captioning: configure [vision] in .rag/config.toml
"""

from __future__ import annotations

import io
import logging
import re
from typing import TYPE_CHECKING, Any

from hwcc.exceptions import ParseError
from hwcc.ingest.base import BaseParser
from hwcc.types import ParseResult

if TYPE_CHECKING:
    from pathlib import Path

    from hwcc.config import HwccConfig
    from hwcc.vision.base import BaseVisionProvider

__all__ = ["DoclingPdfParser"]

logger = logging.getLogger(__name__)

# Module-level conditional import so the name is patchable in tests.
try:
    from docling.document_converter import (
        DocumentConverter,  # type: ignore[import-untyped,unused-ignore]
    )
except ImportError:
    DocumentConverter = None  # type: ignore[assignment,misc,unused-ignore]


def _docling_available() -> bool:
    """Return True if the docling package is importable."""
    try:
        import docling  # noqa: F401

        return True
    except ImportError:
        return False


# ── Figure type classification ───────────────────────────────────────────────

_FIGURE_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "timing_diagram",
        re.compile(
            r"\b(timing|waveform|t_?su|t_?hd|t_?hold|t_?setup|clock|clk)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "block_diagram",
        re.compile(
            r"\b(block\s+diagram|architecture|peripheral|bus|ahb|apb)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "pinout",
        re.compile(r"\b(pin|pinout|package|qfp|lqfp|bga)\b", re.IGNORECASE),
    ),
    (
        "schematic_figure",
        re.compile(r"\b(schematic|circuit|transistor|mosfet)\b", re.IGNORECASE),
    ),
]


def _classify_figure_type(caption: str) -> str:
    """Classify a figure as timing_diagram, block_diagram, pinout, etc.

    Uses keyword matching on the figure's caption text.
    Returns ``"figure"`` if no pattern matches.
    """
    for figure_type, pattern in _FIGURE_TYPE_PATTERNS:
        if pattern.search(caption):
            return figure_type
    return "figure"


# ── Markdown rendering ───────────────────────────────────────────────────────


def _render_figure_block(
    page: int,
    figure_type: str,
    caption: str,
    ai_description: str,
    bbox: tuple[float, float, float, float],
) -> str:
    """Render a figure as a markdown blockquote with a metadata comment.

    Format (no VLM)::

        <!-- FIGURE: page 12, type: timing_diagram, bbox: (10,200,400,350) -->
        > **[Visual: Timing Diagram]**
        > *Caption: Figure 8. SPI bus timing.*

    With VLM caption, an ``AI Description`` line is appended.
    """
    x0, y0, x1, y1 = bbox
    label = figure_type.replace("_", " ").title()
    lines = [
        f"<!-- FIGURE: page {page}, type: {figure_type},"
        f" bbox: ({x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}) -->",
        f"> **[Visual: {label}]**",
    ]
    if caption:
        lines.append(f"> *Caption: {caption}*")
    if ai_description:
        lines.append(f"> *AI Description: {ai_description}*")
    return "\n".join(lines)


def _image_to_bytes(img: Any) -> bytes:
    """Convert a PIL Image object to PNG bytes.

    Returns empty bytes on failure (e.g. mock objects in tests).
    """
    try:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except (OSError, ValueError, AttributeError) as e:
        logger.debug("Failed to convert figure image to bytes: %s", e)
        return b""


# ── Parser class ─────────────────────────────────────────────────────────────


class DoclingPdfParser(BaseParser):
    """Layout-aware PDF parser using Docling for text, tables, and figures.

    Identifies figures (timing diagrams, block diagrams, pinouts) in hardware
    datasheets and represents them as searchable markdown blockquotes at their
    correct reading position.

    Args:
        vision_provider: Vision provider for figure captioning. Defaults to
            NullVisionProvider (placeholders only, no AI descriptions).
        fallback_on_missing_dep: If True, silently fall back to the text-only
            PdfParser when Docling is not installed. If False (default),
            raise ParseError.
    """

    def __init__(
        self,
        vision_provider: BaseVisionProvider | None = None,
        fallback_on_missing_dep: bool = False,
    ) -> None:
        if vision_provider is None:
            from hwcc.vision.none import NullVisionProvider

            vision_provider = NullVisionProvider()
        self.vision_provider = vision_provider
        self.fallback_on_missing_dep = fallback_on_missing_dep

    def supported_extensions(self) -> frozenset[str]:
        """Return supported file extensions."""
        return frozenset({".pdf"})

    def parse(self, path: Path, config: HwccConfig) -> ParseResult:
        """Parse a PDF with Docling layout detection.

        Raises:
            ParseError: If file not found or Docling not installed
                (when fallback_on_missing_dep=False).
        """
        if not path.exists():
            raise ParseError(f"PDF file not found: {path.name}")

        if not _docling_available():
            if self.fallback_on_missing_dep:
                logger.warning(
                    "docling not installed; falling back to text-only PdfParser for %s. "
                    "Enable layout+figure extraction with: pip install hwcc[docling]",
                    path.name,
                )
                from hwcc.ingest.pdf import PdfParser

                return PdfParser().parse(path, config)
            raise ParseError(
                "docling is not installed (required for pdf_backend='docling'). "
                "Install with: pip install hwcc[docling]"
            )

        logger.info("Parsing PDF with Docling: %s", path)

        # Validate vision provider availability once before processing figures.
        # Falls back to NullVisionProvider if provider is not usable (e.g.
        # ClaudeCliVisionProvider when CLAUDECODE env var is set).
        effective_vision = self.vision_provider
        if not effective_vision.is_available():
            from hwcc.vision.none import NullVisionProvider

            logger.info(
                "%s not available; using figure placeholders without captions.",
                effective_vision.__class__.__name__,
            )
            effective_vision = NullVisionProvider()

        try:
            converter = DocumentConverter()
            doc_result = converter.convert(str(path))
        except Exception as e:
            raise ParseError(f"Docling failed to convert {path.name}: {e}") from e

        content, figure_count = _assemble_document(doc_result, effective_vision)

        logger.info(
            "Docling parsed %s: %d figures extracted",
            path.name,
            figure_count,
        )

        return ParseResult(
            doc_id=_make_doc_id(path),
            content=content,
            doc_type="pdf",
            title=path.stem,
            source_path=str(path),
            metadata=(
                ("figure_count", str(figure_count)),
                ("parser", "docling"),
            ),
        )


# ── Document assembly helpers ────────────────────────────────────────────────


def _make_doc_id(path: Path) -> str:
    return path.stem.lower().replace("-", "_").replace(" ", "_") + "_pdf"


def _assemble_document(
    doc_result: Any,
    vision_provider: BaseVisionProvider,
) -> tuple[str, int]:
    """Walk Docling items and assemble a markdown string in reading order.

    Returns:
        (markdown_content, figure_count)
    """
    entries: list[tuple[int, float, str]] = []  # (page, y_pos, markdown)
    figure_count = 0

    for item, _level in doc_result.document.iterate_items():
        label_name = item.label.name if hasattr(item.label, "name") else str(item.label)

        page, y_pos, bbox = _get_provenance(item)

        if label_name == "SECTION_HEADER":
            text = str(item.text or "").strip()
            if text:
                entries.append((page, y_pos, f"## {text}"))

        elif label_name == "TEXT":
            text = str(item.text or "").strip()
            if text:
                entries.append((page, y_pos, text))

        elif label_name == "TABLE":
            if hasattr(item, "export_to_markdown"):
                try:
                    md_table = str(item.export_to_markdown() or "").strip()
                    if md_table:
                        entries.append((page, y_pos, md_table))
                except (OSError, ValueError, TypeError, AttributeError) as e:
                    logger.debug("Failed to export Docling table to markdown: %s", e)

        elif label_name in ("PICTURE", "FIGURE"):
            figure_count += 1
            block = _process_figure(item, doc_result, page, y_pos, bbox, vision_provider)
            entries.append((page, y_pos, block))

    # Sort into reading order: page first, then Y position (top of page = low Y)
    entries.sort(key=lambda e: (e[0], e[1]))

    # Group by page with separators
    pages: dict[int, list[str]] = {}
    for page, _y, text in entries:
        pages.setdefault(page, []).append(text)

    sections = [
        f"<!-- PAGE:{page} -->\n" + "\n\n".join(items)
        for page, items in sorted(pages.items())
    ]

    return "\n\n".join(sections), figure_count


def _get_provenance(item: Any) -> tuple[int, float, tuple[float, float, float, float]]:
    """Extract page number, Y position, and bounding box from a Docling item."""
    if not item.prov:
        return 1, 0.0, (0.0, 0.0, 0.0, 0.0)
    prov = item.prov[0]
    page = int(prov.page_no)
    bbox = (
        float(prov.bbox.l),
        float(prov.bbox.t),
        float(prov.bbox.r),
        float(prov.bbox.b),
    )
    return page, float(prov.bbox.t), bbox


def _process_figure(
    item: Any,
    doc_result: Any,
    page: int,
    y_pos: float,
    bbox: tuple[float, float, float, float],
    vision_provider: BaseVisionProvider,
) -> str:
    """Extract caption, optionally caption image via vision, render figure block."""
    caption = ""
    if hasattr(item, "caption_text") and callable(item.caption_text):
        caption = str(item.caption_text() or "")

    figure_type = _classify_figure_type(caption)
    ai_description = ""

    if hasattr(item, "get_image"):
        img_obj = item.get_image(doc_result.document)
        if img_obj is not None:
            image_bytes = _image_to_bytes(img_obj)
            ai_description = vision_provider.caption_image(image_bytes, context=caption)

    return _render_figure_block(page, figure_type, caption, ai_description, bbox)

"""Plain text file parser — passthrough with normalization.

Reads plain text files, normalizes whitespace and encoding, and produces
a ParseResult ready for the chunking pipeline.

This parser is 100% deterministic — no LLM dependency.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from hwcc.exceptions import ParseError
from hwcc.ingest.base import BaseParser
from hwcc.types import ParseResult

if TYPE_CHECKING:
    from pathlib import Path

    from hwcc.config import HwccConfig

__all__ = ["TextParser"]

logger = logging.getLogger(__name__)

MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50 MB

# Matches 3+ consecutive blank lines (to collapse to 2)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


class TextParser(BaseParser):
    """Parser for plain text documentation files.

    Normalizes whitespace and encoding, extracts a title from the first
    non-empty line, and returns the content as-is.
    """

    def parse(self, path: Path, config: HwccConfig) -> ParseResult:
        """Parse a plain text file into a ParseResult.

        Args:
            path: Path to the .txt or .text file.
            config: Project configuration.

        Returns:
            ParseResult with normalized text content.

        Raises:
            ParseError: If the file cannot be read.
        """
        if not path.exists():
            msg = f"Text file not found: {path}"
            raise ParseError(msg)

        if not path.is_file():
            msg = f"Not a file: {path}"
            raise ParseError(msg)

        _check_file_size(path, MAX_FILE_SIZE)

        logger.info("Parsing text file: %s", path)

        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("UTF-8 decode failed for %s, retrying with replacement", path.name)
            raw = path.read_bytes().decode("utf-8", errors="replace")
        except OSError as e:
            msg = f"Cannot read text file {path.name}: {e}"
            raise ParseError(msg) from e

        # Strip BOM if present
        if raw.startswith("\ufeff"):
            raw = raw[1:]

        # Extract title from first non-empty line (before normalization)
        title = _extract_title(raw, path)

        # Normalize whitespace
        content = _normalize_whitespace(raw)

        logger.info("Parsed %s: %d chars", path.name, len(content))

        return ParseResult(
            doc_id=_make_doc_id(path),
            content=content,
            doc_type="text",
            title=title,
            source_path=str(path),
        )

    def supported_extensions(self) -> frozenset[str]:
        """Return supported file extensions."""
        return frozenset({".txt", ".text"})


# ── Module-level helpers ────────────────────────────────────────────


def _make_doc_id(path: Path) -> str:
    """Generate a document ID from the file path."""
    return path.stem.lower().replace("-", "_").replace(" ", "_") + "_txt"


def _check_file_size(path: Path, max_size: int) -> None:
    """Validate file size.

    Raises:
        ParseError: If the file exceeds the size limit.
    """
    file_size = path.stat().st_size
    if file_size > max_size:
        msg = f"Text file {path.name} ({file_size} bytes) exceeds maximum size ({max_size} bytes)"
        raise ParseError(msg)


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text.

    - Strip trailing whitespace from each line
    - Collapse 3+ consecutive blank lines to 2
    - Strip leading/trailing whitespace from the whole document
    """
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip()


def _extract_title(raw: str, path: Path) -> str:
    """Extract title from the first non-empty line, or filename stem."""
    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped:
            return stripped
    return path.stem

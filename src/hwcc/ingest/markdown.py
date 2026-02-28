"""Markdown file parser — passthrough with normalization and front-matter extraction.

Reads markdown files, normalizes whitespace, extracts YAML front-matter
metadata, and preserves code blocks and tables unchanged.

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

__all__ = ["MarkdownParser"]

logger = logging.getLogger(__name__)

MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50 MB

# Matches 3+ consecutive blank lines (to collapse to 2)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")

# Matches any markdown heading (h1-h6) at the start of a line for title extraction
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)", re.MULTILINE)


class MarkdownParser(BaseParser):
    """Parser for markdown documentation files.

    Extracts YAML front-matter metadata, normalizes whitespace, and
    preserves code blocks, tables, and structure unchanged.
    """

    def parse(self, path: Path, config: HwccConfig) -> ParseResult:
        """Parse a markdown file into a ParseResult.

        Args:
            path: Path to the .md or .markdown file.
            config: Project configuration.

        Returns:
            ParseResult with normalized markdown content and metadata.

        Raises:
            ParseError: If the file cannot be read.
        """
        if not path.exists():
            msg = f"Markdown file not found: {path}"
            raise ParseError(msg)

        if not path.is_file():
            msg = f"Not a file: {path}"
            raise ParseError(msg)

        _check_file_size(path, MAX_FILE_SIZE)

        logger.info("Parsing markdown file: %s", path)

        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("UTF-8 decode failed for %s, retrying with replacement", path.name)
            raw = path.read_bytes().decode("utf-8", errors="replace")
        except OSError as e:
            msg = f"Cannot read markdown file {path.name}: {e}"
            raise ParseError(msg) from e

        # Strip BOM if present
        if raw.startswith("\ufeff"):
            raw = raw[1:]

        # Extract front-matter
        frontmatter, body = _split_frontmatter(raw)
        meta_dict = _parse_frontmatter(frontmatter) if frontmatter is not None else {}

        # Normalize whitespace
        content = _normalize_whitespace(body)

        # Extract title: front-matter > first heading > filename stem
        title = _extract_title(meta_dict, content, path)

        # Build metadata tuples from front-matter (excluding title)
        metadata = tuple((str(k), str(v)) for k, v in meta_dict.items() if k != "title")

        logger.info("Parsed %s: %d chars", path.name, len(content))

        return ParseResult(
            doc_id=_make_doc_id(path),
            content=content,
            doc_type="markdown",
            title=title,
            source_path=str(path),
            metadata=metadata,
        )

    def supported_extensions(self) -> frozenset[str]:
        """Return supported file extensions."""
        return frozenset({".md", ".markdown"})


# ── Module-level helpers ────────────────────────────────────────────


def _make_doc_id(path: Path) -> str:
    """Generate a document ID from the file path."""
    return path.stem.lower().replace("-", "_").replace(" ", "_") + "_md"


def _check_file_size(path: Path, max_size: int) -> None:
    """Validate file size.

    Raises:
        ParseError: If the file exceeds the size limit.
    """
    file_size = path.stat().st_size
    if file_size > max_size:
        msg = (
            f"Markdown file {path.name} ({file_size} bytes) "
            f"exceeds maximum size ({max_size} bytes)"
        )
        raise ParseError(msg)


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """Split YAML front-matter from markdown body.

    Front-matter must start with ``---`` on the first line and end with
    a second ``---`` on its own line.

    Returns:
        (frontmatter_text or None, body_text)
    """
    if not text.startswith("---"):
        return None, text

    # Find the closing ---
    end_idx = text.find("\n---", 3)
    if end_idx == -1:
        return None, text

    # Move past the closing --- and its newline
    fm_text = text[3:end_idx].strip()
    body_start = end_idx + 4  # len("\n---")
    if body_start < len(text) and text[body_start] == "\n":
        body_start += 1

    body = text[body_start:]
    return fm_text, body


def _parse_frontmatter(fm_text: str) -> dict[str, str]:
    """Parse YAML front-matter text into a dict of string key-value pairs.

    Falls back gracefully if PyYAML is not available or YAML is invalid.
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("PyYAML not available, skipping front-matter parsing")
        return {}

    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        logger.debug("Invalid YAML front-matter, treating as content")
        return {}

    if not isinstance(data, dict):
        return {}

    return {str(k): str(v) for k, v in data.items()}


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text.

    - Strip trailing whitespace from each line
    - Collapse 3+ consecutive blank lines to 2
    - Strip leading/trailing whitespace from the whole document
    """
    # Strip trailing whitespace per line
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)

    # Collapse excessive blank lines
    text = _MULTI_BLANK_RE.sub("\n\n", text)

    return text.strip()


def _extract_title(meta: dict[str, str], content: str, path: Path) -> str:
    """Extract title from front-matter, first heading, or filename.

    Priority: front-matter ``title`` > first ``# heading`` > filename stem.
    """
    # 1. Front-matter title
    if "title" in meta:
        return meta["title"]

    # 2. First # heading in content
    match = _HEADING_RE.search(content)
    if match:
        return match.group(1).strip()

    # 3. Filename stem
    return path.stem

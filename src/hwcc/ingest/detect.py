"""File type detection by extension and magic bytes.

Detects the structural file format, maps it to a parser name, and
auto-classifies the semantic document type (datasheet, reference manual, etc.).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from hwcc.exceptions import ParseError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "DocType",
    "FileFormat",
    "FileInfo",
    "classify_doc_type",
    "detect_file_type",
    "get_supported_extensions",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums (str-based for backward compatibility with existing str fields)
# ---------------------------------------------------------------------------


class FileFormat(str, Enum):
    """Structural file format."""

    PDF = "pdf"
    SVD = "svd"
    MARKDOWN = "markdown"
    TEXT = "text"
    DEVICE_TREE = "device_tree"
    C_HEADER = "c_header"
    C_SOURCE = "c_source"
    RUST = "rust"
    HTML = "html"
    JSON_FORMAT = "json"
    YAML = "yaml"
    CUBEMX = "cubemx"
    IMAGE = "image"
    UNKNOWN = "unknown"


class DocType(str, Enum):
    """Semantic document classification."""

    DATASHEET = "datasheet"
    REFERENCE_MANUAL = "reference_manual"
    ERRATA = "errata"
    APP_NOTE = "app_note"
    SCHEMATIC = "schematic"
    SVD = "svd"
    DEVICE_TREE = "device_tree"
    CODE = "code"
    DOCUMENTATION = "documentation"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Detection result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileInfo:
    """Result of file type detection."""

    path: Path
    format: FileFormat
    doc_type: DocType
    parser_name: str
    confidence: float


# ---------------------------------------------------------------------------
# Extension → FileFormat mapping
# ---------------------------------------------------------------------------

_EXTENSION_MAP: dict[str, FileFormat] = {
    ".pdf": FileFormat.PDF,
    ".svd": FileFormat.SVD,
    ".md": FileFormat.MARKDOWN,
    ".markdown": FileFormat.MARKDOWN,
    ".txt": FileFormat.TEXT,
    ".text": FileFormat.TEXT,
    ".dts": FileFormat.DEVICE_TREE,
    ".dtsi": FileFormat.DEVICE_TREE,
    ".h": FileFormat.C_HEADER,
    ".c": FileFormat.C_SOURCE,
    ".rs": FileFormat.RUST,
    ".html": FileFormat.HTML,
    ".htm": FileFormat.HTML,
    ".json": FileFormat.JSON_FORMAT,
    ".yaml": FileFormat.YAML,
    ".yml": FileFormat.YAML,
    ".ioc": FileFormat.CUBEMX,
    ".png": FileFormat.IMAGE,
    ".jpg": FileFormat.IMAGE,
    ".jpeg": FileFormat.IMAGE,
}

# ---------------------------------------------------------------------------
# FileFormat → parser registry key mapping
# ---------------------------------------------------------------------------

_FORMAT_PARSER_MAP: dict[FileFormat, str] = {
    FileFormat.PDF: "pdf",
    FileFormat.SVD: "svd",
    FileFormat.MARKDOWN: "markdown",
    FileFormat.TEXT: "text",
    FileFormat.DEVICE_TREE: "device_tree",
    FileFormat.C_HEADER: "c_header",
    FileFormat.C_SOURCE: "c_source",
    FileFormat.RUST: "rust",
    FileFormat.HTML: "html",
    FileFormat.JSON_FORMAT: "json",
    FileFormat.YAML: "yaml",
    FileFormat.CUBEMX: "cubemx",
    FileFormat.IMAGE: "image",
}

# ---------------------------------------------------------------------------
# Magic byte signatures
# ---------------------------------------------------------------------------

_MAGIC_SIGNATURES: list[tuple[bytes, FileFormat]] = [
    (b"%PDF-", FileFormat.PDF),
    (b"\x89PNG\r\n\x1a\n", FileFormat.IMAGE),
    (b"\xff\xd8\xff", FileFormat.IMAGE),
]

# Max bytes to read for magic byte detection.
_MAGIC_READ_SIZE = 16


def _check_magic_bytes(path: Path) -> FileFormat | None:
    """Read file header and return detected format, or ``None``."""
    try:
        with path.open("rb") as f:
            header = f.read(_MAGIC_READ_SIZE)
    except OSError as exc:
        logger.debug("Cannot read magic bytes from %s: %s", path.name, exc)
        return None

    if not header:
        return None

    for signature, fmt in _MAGIC_SIGNATURES:
        if header[: len(signature)] == signature:
            return fmt

    return None


# ---------------------------------------------------------------------------
# SVD/XML disambiguation
# ---------------------------------------------------------------------------

_SVD_PROBE_SIZE = 4096


def _check_svd_xml(path: Path) -> bool:
    """Return ``True`` if *path* looks like a CMSIS-SVD XML file."""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            head = f.read(_SVD_PROBE_SIZE)
    except OSError as exc:
        logger.debug("Cannot read SVD probe from %s: %s", path.name, exc)
        return False
    return "<device" in head.lower()


# ---------------------------------------------------------------------------
# Document type classification heuristics
# ---------------------------------------------------------------------------

_DOC_TYPE_PATTERNS: list[tuple[re.Pattern[str], DocType]] = [
    (re.compile(r"(datasheet|\bds_|_ds\b)", re.IGNORECASE), DocType.DATASHEET),
    (
        re.compile(r"(reference|ref_manual|\brm_|_rm\b)", re.IGNORECASE),
        DocType.REFERENCE_MANUAL,
    ),
    (re.compile(r"(errata|erratum|\bes_|_es\b)", re.IGNORECASE), DocType.ERRATA),
    (re.compile(r"(app_note|appnote|\ban_|_an\b)", re.IGNORECASE), DocType.APP_NOTE),
    (re.compile(r"schematic", re.IGNORECASE), DocType.SCHEMATIC),
]

# Formats that have a deterministic doc type regardless of filename.
_FORMAT_DOC_TYPE_MAP: dict[FileFormat, DocType] = {
    FileFormat.SVD: DocType.SVD,
    FileFormat.DEVICE_TREE: DocType.DEVICE_TREE,
    FileFormat.C_HEADER: DocType.CODE,
    FileFormat.C_SOURCE: DocType.CODE,
    FileFormat.RUST: DocType.CODE,
    FileFormat.MARKDOWN: DocType.DOCUMENTATION,
}


def classify_doc_type(path: Path, file_format: FileFormat) -> DocType:
    """Classify the semantic document type from filename and format.

    Deterministic formats (SVD, device tree, code, markdown) return their
    fixed doc type.  For others (e.g. PDF), filename heuristics are applied.
    """
    # 1. Check deterministic format → doc type mapping first
    if file_format in _FORMAT_DOC_TYPE_MAP:
        return _FORMAT_DOC_TYPE_MAP[file_format]

    # 2. Apply filename heuristics
    name = path.stem  # filename without extension
    for pattern, doc_type in _DOC_TYPE_PATTERNS:
        if pattern.search(name):
            return doc_type

    return DocType.UNKNOWN


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_file_type(path: Path) -> FileInfo:
    """Detect file type by extension and magic bytes.

    Args:
        path: Path to the file to detect.

    Returns:
        A :class:`FileInfo` with format, doc type, parser name, and confidence.

    Raises:
        ParseError: If *path* does not exist.
    """
    if not path.exists():
        raise ParseError(f"File does not exist: {path}")

    if not path.is_file():
        raise ParseError(f"Not a file: {path}")

    ext = path.suffix.lower()
    ext_format = _EXTENSION_MAP.get(ext)

    magic_format = _check_magic_bytes(path)

    # SVD/XML disambiguation: .xml file containing <device> tag
    if ext == ".xml" and _check_svd_xml(path):
        ext_format = FileFormat.SVD

    # Determine final format and confidence
    if ext_format is not None and magic_format is not None:
        if ext_format == magic_format:
            final_format = ext_format
            confidence = 1.0
        else:
            # Conflict: trust extension but lower confidence
            final_format = ext_format
            confidence = 0.7
    elif ext_format is not None:
        # Extension matched; magic bytes couldn't confirm (text format or empty file)
        final_format = ext_format
        confidence = 0.9 if path.stat().st_size > 0 else 1.0
    elif magic_format is not None:
        # No recognized extension, but magic bytes matched
        final_format = magic_format
        confidence = 0.8
    else:
        final_format = FileFormat.UNKNOWN
        confidence = 0.0

    parser_name = _FORMAT_PARSER_MAP.get(final_format, "")
    doc_type = classify_doc_type(path, final_format)

    logger.debug(
        "Detected %s: format=%s, doc_type=%s, parser=%s, confidence=%.1f",
        path.name,
        final_format,
        doc_type,
        parser_name,
        confidence,
    )

    return FileInfo(
        path=path,
        format=final_format,
        doc_type=doc_type,
        parser_name=parser_name,
        confidence=confidence,
    )


_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(_EXTENSION_MAP.keys())


def get_supported_extensions() -> frozenset[str]:
    """Return all file extensions recognized by the detection module."""
    return _SUPPORTED_EXTENSIONS

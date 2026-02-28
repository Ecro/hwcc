"""Ingestion pipeline — parsers for hardware documentation."""

from hwcc.exceptions import ParseError
from hwcc.ingest.base import BaseParser
from hwcc.ingest.detect import (
    DocType,
    FileFormat,
    FileInfo,
    classify_doc_type,
    detect_file_type,
    get_supported_extensions,
)
from hwcc.ingest.markdown import MarkdownParser
from hwcc.ingest.pdf import PdfParser
from hwcc.ingest.svd import SvdParser
from hwcc.ingest.text import TextParser

__all__ = [
    "BaseParser",
    "DocType",
    "FileFormat",
    "FileInfo",
    "MarkdownParser",
    "PdfParser",
    "SvdParser",
    "TextParser",
    "classify_doc_type",
    "detect_file_type",
    "get_parser",
    "get_supported_extensions",
]

_PARSER_MAP: dict[str, type[BaseParser]] = {
    "pdf": PdfParser,
    "svd": SvdParser,
    "markdown": MarkdownParser,
    "text": TextParser,
}


def get_parser(parser_name: str) -> BaseParser:
    """Return a parser instance for the given parser name.

    Args:
        parser_name: Parser identifier (e.g. ``"pdf"``, ``"svd"``).

    Returns:
        A new parser instance.

    Raises:
        ParseError: If no parser is registered for the given name.
    """
    cls = _PARSER_MAP.get(parser_name)
    if cls is None:
        raise ParseError(f"No parser for format: {parser_name!r}")
    return cls()

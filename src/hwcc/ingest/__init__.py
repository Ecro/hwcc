"""Ingestion pipeline — parsers for hardware documentation."""

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
    "get_supported_extensions",
]

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
from hwcc.ingest.pdf import PdfParser
from hwcc.ingest.svd import SvdParser

__all__ = [
    "BaseParser",
    "DocType",
    "FileFormat",
    "FileInfo",
    "PdfParser",
    "SvdParser",
    "classify_doc_type",
    "detect_file_type",
    "get_supported_extensions",
]

"""Ingestion pipeline — parsers for hardware documentation."""

from hwcc.ingest.base import BaseParser
from hwcc.ingest.svd import SvdParser

__all__ = ["BaseParser", "SvdParser"]

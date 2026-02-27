"""Abstract base class for document parsers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from hwcc.config import HwccConfig
    from hwcc.types import ParseResult

__all__ = ["BaseParser"]

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Base class for all document parsers.

    Subclasses must implement ``parse`` and ``supported_extensions``.
    The ``can_parse`` helper checks file extension membership.
    """

    @abstractmethod
    def parse(self, path: Path, config: HwccConfig) -> ParseResult:
        """Parse a document file into a ``ParseResult``.

        Args:
            path: Path to the document file.
            config: Project configuration.

        Returns:
            ParseResult with clean markdown content and metadata.

        Raises:
            ParseError: If the document cannot be parsed.
        """

    @abstractmethod
    def supported_extensions(self) -> frozenset[str]:
        """Return the set of file extensions this parser handles.

        Extensions should include the leading dot, e.g. ``{".pdf", ".PDF"}``.
        """

    def can_parse(self, path: Path) -> bool:
        """Check whether this parser can handle the given file."""
        return path.suffix.lower() in self.supported_extensions()

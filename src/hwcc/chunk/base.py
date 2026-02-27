"""Abstract base class for chunking strategies."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hwcc.config import HwccConfig
    from hwcc.types import Chunk, ParseResult

__all__ = ["BaseChunker"]

logger = logging.getLogger(__name__)


class BaseChunker(ABC):
    """Base class for all chunking strategies.

    Subclasses split a ``ParseResult`` into a list of ``Chunk`` objects.
    """

    @abstractmethod
    def chunk(self, result: ParseResult, config: HwccConfig) -> list[Chunk]:
        """Split a parse result into chunks.

        Args:
            result: The parsed document to chunk.
            config: Project configuration (chunk size, overlap, etc.).

        Returns:
            List of chunks with metadata.

        Raises:
            ChunkError: If chunking fails.
        """

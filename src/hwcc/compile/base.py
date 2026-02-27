"""Abstract base class for context compilers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from hwcc.config import HwccConfig
    from hwcc.store.base import BaseStore

__all__ = ["BaseCompiler"]

logger = logging.getLogger(__name__)


class BaseCompiler(ABC):
    """Base class for all context compilers.

    Subclasses generate output files (hot context, peripheral context,
    CLAUDE.md sections, etc.) from the vector store.
    """

    @abstractmethod
    def compile(self, store: BaseStore, config: HwccConfig) -> list[Path]:
        """Compile context files from the store.

        Args:
            store: Vector store to query for content.
            config: Project configuration.

        Returns:
            List of file paths that were created or updated.

        Raises:
            CompileError: If compilation fails.
        """

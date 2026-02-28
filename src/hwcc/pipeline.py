"""Pipeline orchestrator for hwcc.

Composes parser → chunker → embedder → store via constructor injection.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from hwcc.exceptions import PipelineError

if TYPE_CHECKING:
    from pathlib import Path

    from hwcc.chunk.base import BaseChunker
    from hwcc.config import HwccConfig
    from hwcc.embed.base import BaseEmbedder
    from hwcc.ingest.base import BaseParser
    from hwcc.store.base import BaseStore

__all__ = ["Pipeline"]

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the document processing pipeline.

    All dependencies are injected via the constructor, making the pipeline
    fully testable with mock implementations.

    Usage::

        pipeline = Pipeline(
            parser=svd_parser,
            chunker=recursive_chunker,
            embedder=ollama_embedder,
            store=chroma_store,
            config=config,
        )
        chunk_count = pipeline.process(Path("board.svd"), doc_id="board_svd")
    """

    def __init__(
        self,
        parser: BaseParser,
        chunker: BaseChunker,
        embedder: BaseEmbedder,
        store: BaseStore,
        config: HwccConfig,
    ) -> None:
        self.parser = parser
        self.chunker = chunker
        self.embedder = embedder
        self.store = store
        self.config = config

    def process(
        self,
        path: Path,
        doc_id: str,
        doc_type: str = "",
        chip: str = "",
    ) -> int:
        """Run the full pipeline: parse → chunk → embed → store.

        Args:
            path: Path to the document file.
            doc_id: Unique document identifier.
            doc_type: Document type hint (e.g. "datasheet", "svd").
            chip: Chip/device identifier for multi-vendor support.

        Returns:
            Number of chunks stored.

        Raises:
            PipelineError: If any pipeline stage fails.
        """
        try:
            logger.info("Processing %s (doc_id=%s)", path, doc_id)

            result = self.parser.parse(path, self.config)

            # Apply caller-supplied overrides (CLI --type / --chip flags)
            if doc_type or chip:
                result = replace(
                    result,
                    doc_type=doc_type or result.doc_type,
                    chip=chip or result.chip,
                )

            logger.info("Parsed %s: %d chars", path.name, len(result.content))

            chunks = self.chunker.chunk(result, self.config)
            logger.info("Chunked into %d chunks", len(chunks))

            if not chunks:
                logger.warning("No chunks produced for %s", path)
                return 0

            embedded = self.embedder.embed_chunks(chunks)
            logger.info("Embedded %d chunks", len(embedded))

            count = self.store.add(embedded, doc_id)
            logger.info("Stored %d chunks for %s", count, doc_id)

            return count

        except PipelineError:
            raise
        except Exception as e:
            raise PipelineError(f"Pipeline failed processing {path}: {e}") from e

    def remove(self, doc_id: str) -> int:
        """Remove a document from the store.

        Args:
            doc_id: Document identifier to remove.

        Returns:
            Number of chunks removed.

        Raises:
            PipelineError: If removal fails.
        """
        try:
            count = self.store.delete(doc_id)
            logger.info("Removed %d chunks for %s", count, doc_id)
            return count
        except PipelineError:
            raise
        except Exception as e:
            raise PipelineError(f"Pipeline failed removing {doc_id}: {e}") from e

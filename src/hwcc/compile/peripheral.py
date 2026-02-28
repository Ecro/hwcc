"""Peripheral context compiler — generates .rag/context/peripherals/<name>.md.

Sources register maps from SVD chunks in the vector store and enriches
with cross-document content (datasheets, reference manuals) when available.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from hwcc.compile.base import BaseCompiler
from hwcc.compile.context import CompileContext
from hwcc.compile.templates import TemplateEngine
from hwcc.exceptions import CompileError

if TYPE_CHECKING:
    from pathlib import Path

    from hwcc.config import HwccConfig
    from hwcc.store.base import BaseStore
    from hwcc.types import Chunk

__all__ = ["PeripheralContextCompiler"]

logger = logging.getLogger(__name__)

_TEMPLATE_NAME = "peripheral.md.j2"

# Maximum number of non-SVD chunks to include as peripheral details.
_MAX_DETAIL_CHUNKS = 5


class PeripheralContextCompiler(BaseCompiler):
    """Compiles .rag/context/peripherals/<name>.md per peripheral.

    Sources register maps from SVD chunks and optionally enriches
    with content from datasheet/reference manual chunks.

    SVD section_paths follow the pattern::

        "DeviceName Register Map > PeripheralName [> SubSection]"

    The peripheral name is extracted as the 2nd element of the path.
    """

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._rag_dir = project_root / ".rag"
        self._peripherals_dir = self._rag_dir / "context" / "peripherals"
        self._engine = TemplateEngine(project_root)

    def compile(self, store: BaseStore, config: HwccConfig) -> list[Path]:
        """Compile per-peripheral context files.

        1. Discover peripherals from SVD chunk section_paths.
        2. For each peripheral, extract register map + details.
        3. Render ``peripheral.md.j2`` and write to output dir.

        Args:
            store: Vector store to query for chunk content.
            config: Project configuration.

        Returns:
            List of paths to generated peripheral context files.

        Raises:
            CompileError: If compilation fails.
        """
        try:
            self._peripherals_dir.mkdir(parents=True, exist_ok=True)

            # Fetch all chunks once, partition by doc_type
            all_chunks = store.get_chunks()
            svd_chunks = [c for c in all_chunks if c.metadata.doc_type == "svd"]
            non_svd_chunks = [c for c in all_chunks if c.metadata.doc_type != "svd"]

            if not svd_chunks:
                logger.info("No SVD documents indexed, skipping peripheral compilation")
                return []

            # Discover peripherals from SVD section paths
            peripherals = self._discover_peripherals(svd_chunks)
            if not peripherals:
                logger.info("No peripherals found in SVD data")
                return []

            logger.debug(
                "Discovered %d peripherals from %d SVD chunks",
                len(peripherals),
                len(svd_chunks),
            )

            # Detect name collisions across chips for filename disambiguation
            name_counts: dict[str, int] = {}
            for name, _chip in peripherals:
                name_counts[name] = name_counts.get(name, 0) + 1

            # Generate context file per peripheral
            base_context = CompileContext.from_config(config)
            output_paths: list[Path] = []

            for name, chip in peripherals:
                register_map = self._extract_register_map(name, svd_chunks, chip)
                details = self._gather_peripheral_details(name, non_svd_chunks, chip)

                ctx = replace(
                    base_context,
                    peripheral_name=name,
                    register_map=register_map,
                    peripheral_details=details,
                )

                content = self._engine.render(_TEMPLATE_NAME, ctx)

                # Include chip in filename when multiple chips define same peripheral
                if name_counts[name] > 1:
                    filename = f"{name.lower()}_{chip.lower()}.md"
                else:
                    filename = f"{name.lower()}.md"

                output_path = self._peripherals_dir / filename
                output_path.write_text(content, encoding="utf-8")
                output_paths.append(output_path)

                logger.info("Compiled peripheral context: %s", filename)

            logger.info("Compiled %d peripheral context files", len(output_paths))

        except CompileError:
            raise
        except Exception as e:
            raise CompileError(f"Failed to compile peripheral context: {e}") from e

        return output_paths

    def _discover_peripherals(self, svd_chunks: list[Chunk]) -> list[tuple[str, str]]:
        """Extract unique (peripheral_name, chip) pairs from SVD chunk section_paths.

        SVD section_paths follow::

            "DeviceName Register Map > PeripheralName [> SubSection]"

        The peripheral name is the 2nd element in the ``" > "``-split path.

        Args:
            svd_chunks: All SVD-type chunks from the store.

        Returns:
            Sorted list of (peripheral_name, chip) tuples.
        """
        seen: set[tuple[str, str]] = set()
        peripherals: list[tuple[str, str]] = []

        for chunk in svd_chunks:
            parts = chunk.metadata.section_path.split(" > ")
            if len(parts) >= 2:
                peripheral_name = parts[1].strip()
                chip = chunk.metadata.chip
                key = (peripheral_name, chip)
                if key not in seen:
                    seen.add(key)
                    peripherals.append(key)

        peripherals.sort(key=lambda p: p[0])
        return peripherals

    def _extract_register_map(
        self,
        peripheral_name: str,
        svd_chunks: list[Chunk],
        chip: str = "",
    ) -> str:
        """Extract register map content for a peripheral from SVD chunks.

        Filters chunks whose section_path 2nd element matches the peripheral
        name exactly, sorts by chunk_id (preserves document order), and
        concatenates their content.

        When ``chip`` is provided, only chunks for that chip are included
        (prevents cross-chip register map contamination in multi-chip projects).

        Args:
            peripheral_name: Name of the peripheral (e.g. ``"SPI1"``).
            svd_chunks: All SVD-type chunks from the store.
            chip: Optional chip filter for multi-chip disambiguation.

        Returns:
            Concatenated register map markdown, or empty string.
        """
        relevant = [
            c
            for c in svd_chunks
            if self._chunk_belongs_to_peripheral(c, peripheral_name)
            and (not chip or c.metadata.chip == chip)
        ]
        relevant.sort(key=lambda c: c.chunk_id)
        return "\n\n".join(c.content for c in relevant).strip()

    def _gather_peripheral_details(
        self,
        peripheral_name: str,
        non_svd_chunks: list[Chunk],
        chip: str = "",
    ) -> str:
        """Gather additional details about a peripheral from non-SVD documents.

        Matches peripheral name against individual path elements in
        section_path (case-insensitive, exact element match) to avoid
        false positives like ``SPI1`` matching ``SPI10``.

        When ``chip`` is provided, only chunks for that chip are included.

        Limits to ``_MAX_DETAIL_CHUNKS`` to avoid bloat.

        Args:
            peripheral_name: Name of the peripheral (e.g. ``"SPI1"``).
            non_svd_chunks: All non-SVD chunks from the store.
            chip: Optional chip filter for multi-chip disambiguation.

        Returns:
            Concatenated detail content, or empty string.
        """
        relevant = [
            c
            for c in non_svd_chunks
            if self._section_path_mentions_peripheral(c.metadata.section_path, peripheral_name)
            and (not chip or c.metadata.chip == chip)
        ]
        relevant.sort(key=lambda c: c.chunk_id)
        relevant = relevant[:_MAX_DETAIL_CHUNKS]

        if not relevant:
            return ""

        return "\n\n---\n\n".join(c.content for c in relevant).strip()

    @staticmethod
    def _chunk_belongs_to_peripheral(chunk: Chunk, peripheral_name: str) -> bool:
        """Check if a chunk belongs to the given peripheral via section_path.

        The peripheral name must match the 2nd element of the section_path
        exactly (case-sensitive) to avoid cross-peripheral contamination.
        """
        parts = chunk.metadata.section_path.split(" > ")
        return len(parts) >= 2 and parts[1].strip() == peripheral_name

    @staticmethod
    def _section_path_mentions_peripheral(section_path: str, peripheral_name: str) -> bool:
        """Check if any element in section_path matches the peripheral name.

        Uses case-insensitive exact element matching to avoid false
        positives (e.g. ``SPI1`` must not match ``SPI10``).
        """
        parts = section_path.split(" > ")
        needle = peripheral_name.lower()
        return any(needle == part.strip().lower() for part in parts)

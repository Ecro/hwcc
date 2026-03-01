"""Hot context compiler — generates .rag/context/hot.md.

Gathers data from manifest, vector store metadata, and project config,
builds a CompileContext, renders hot_context.md.j2, and writes the result
respecting the configured line budget.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from hwcc.compile.base import BaseCompiler
from hwcc.compile.context import CompileContext, DocumentSummary, PeripheralSummary
from hwcc.compile.templates import TemplateEngine
from hwcc.exceptions import CompileError, ManifestError, StoreError
from hwcc.manifest import load_manifest, save_manifest

if TYPE_CHECKING:
    from pathlib import Path

    from hwcc.config import HwccConfig
    from hwcc.store.base import BaseStore

__all__ = ["HotContextCompiler"]

logger = logging.getLogger(__name__)

_TEMPLATE_NAME = "hot_context.md.j2"


class HotContextCompiler(BaseCompiler):
    """Compiles .rag/context/hot.md from manifest + store + config.

    The hot context file is a concise hardware summary designed to fit
    within the ``hot_context_max_lines`` budget (default 120 lines).
    When content exceeds the budget, lower-priority sections are
    progressively removed.

    Priority order (highest to lowest):
        1. Errata highlights (safety-critical)
        2. Target hardware + software stack (always small)
        3. Indexed documents table
        4. Peripheral list
        5. Coding conventions
    """

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._rag_dir = project_root / ".rag"
        self._context_dir = self._rag_dir / "context"
        self._manifest_path = self._rag_dir / "manifest.json"
        self._engine = TemplateEngine(project_root)

    def compile(self, store: BaseStore, config: HwccConfig) -> list[Path]:
        """Compile the hot context file.

        Gathers document data from the manifest, peripheral names from
        the store metadata, and hardware/software/convention data from
        the config. Renders via ``hot_context.md.j2`` and enforces the
        line budget.

        Args:
            store: Vector store to query for peripheral metadata.
            config: Project configuration.

        Returns:
            Single-element list containing the path to hot.md.

        Raises:
            CompileError: If compilation fails.
        """
        try:
            # Ensure output directory exists
            self._context_dir.mkdir(parents=True, exist_ok=True)

            # Build context from all sources
            context = self._build_context(store, config)

            # Render and enforce line budget
            max_lines = config.output.hot_context_max_lines
            content = self._render_within_budget(context, max_lines)

            # Write output
            output_path = self._context_dir / "hot.md"
            output_path.write_text(content, encoding="utf-8")

            logger.info(
                "Compiled hot context: %d lines (budget: %d)",
                self._count_lines(content),
                max_lines,
            )
        except CompileError:
            raise
        except Exception as e:
            raise CompileError(f"Failed to compile hot context: {e}") from e

        # Update manifest timestamp
        self._update_manifest_timestamp()

        return [output_path]

    def _build_context(self, store: BaseStore, config: HwccConfig) -> CompileContext:
        """Build CompileContext from manifest + store metadata + config."""
        # Start with config data
        context = CompileContext.from_config(config)

        # Add document summaries from manifest
        documents = self._gather_documents()

        # Add peripheral summaries from store metadata
        peripherals = self._gather_peripherals(store)

        # Replace compiled data fields (frozen dataclass requires replace)
        return replace(
            context,
            documents=tuple(documents),
            peripherals=tuple(peripherals),
        )

    def _gather_documents(self) -> list[DocumentSummary]:
        """Extract document summaries from the manifest."""
        if not self._manifest_path.exists():
            return []

        try:
            manifest = load_manifest(self._manifest_path)
        except ManifestError:
            logger.warning("Could not load manifest, skipping document data")
            return []

        summaries: list[DocumentSummary] = []
        for entry in manifest.documents:
            # Derive a human-readable title from the document path
            title = self._derive_title(entry.id, entry.path)
            summaries.append(
                DocumentSummary(
                    doc_id=entry.id,
                    title=title,
                    doc_type=entry.doc_type,
                    chip=entry.chip,
                    chunk_count=entry.chunks,
                )
            )
        return summaries

    def _gather_peripherals(self, store: BaseStore) -> list[PeripheralSummary]:
        """Extract unique peripheral names and register counts from store metadata."""
        try:
            all_metadata = store.get_chunk_metadata()
        except StoreError:
            logger.warning("Could not query store metadata, skipping peripheral data")
            return []

        # Count SVD chunks per (peripheral, chip) for register_count.
        # TODO: Use filtered store.get_chunk_metadata(where={"doc_type": "svd"}).
        svd_counts: dict[tuple[str, str], int] = {}
        seen: set[tuple[str, str]] = set()
        peripheral_keys: list[tuple[str, str]] = []

        for meta in all_metadata:
            if not meta.peripheral:
                continue
            key = (meta.peripheral, meta.chip)
            if key not in seen:
                seen.add(key)
                peripheral_keys.append(key)
            if meta.doc_type == "svd":
                svd_counts[key] = svd_counts.get(key, 0) + 1

        peripherals = [
            PeripheralSummary(
                name=name,
                chip=chip,
                register_count=svd_counts.get((name, chip), 0),
            )
            for name, chip in peripheral_keys
        ]

        # Sort alphabetically for stable output
        peripherals.sort(key=lambda p: p.name)
        return peripherals

    def _render_within_budget(self, context: CompileContext, max_lines: int) -> str:
        """Render template and enforce line budget via priority truncation.

        If the rendered output exceeds max_lines, progressively remove
        lower-priority sections and re-render:
            1. Remove conventions (lowest priority)
            2. Truncate peripheral list
            3. Remove peripheral list entirely
            4. Truncate document table
            5. Remove document table entirely
        Errata and hardware/software info are always kept.
        """
        content = self._engine.render(_TEMPLATE_NAME, context)
        if self._count_lines(content) <= max_lines:
            return content

        # Priority 5 (lowest): remove conventions
        reduced = replace(
            context,
            register_access="",
            error_handling="",
            naming="",
        )
        content = self._engine.render(_TEMPLATE_NAME, reduced)
        if self._count_lines(content) <= max_lines:
            return content

        # Priority 4: truncate peripherals progressively
        if reduced.peripherals:
            current_count = len(reduced.peripherals)
            truncated = reduced
            for limit in (20, 10, 5, 0):
                if limit >= current_count:
                    continue
                truncated = replace(reduced, peripherals=reduced.peripherals[:limit])
                content = self._engine.render(_TEMPLATE_NAME, truncated)
                if self._count_lines(content) <= max_lines:
                    return content
            reduced = truncated

        # Priority 3: truncate documents progressively
        if reduced.documents:
            for limit in (10, 5, 0):
                truncated = replace(reduced, documents=reduced.documents[:limit])
                content = self._engine.render(_TEMPLATE_NAME, truncated)
                if self._count_lines(content) <= max_lines:
                    return content

        # Last resort: return what we have (header + hardware only)
        return content

    def _update_manifest_timestamp(self) -> None:
        """Update manifest.last_compiled to current time."""
        if not self._manifest_path.exists():
            return
        try:
            manifest = load_manifest(self._manifest_path)
            manifest.last_compiled = datetime.now(UTC).isoformat()
            save_manifest(manifest, self._manifest_path)
        except ManifestError:
            logger.warning("Could not update manifest timestamp")

    @staticmethod
    def _derive_title(doc_id: str, path: str) -> str:
        """Derive a human-readable title from document path or ID.

        Prefers the filename stem, falling back to doc_id.
        """
        name = PurePosixPath(path).stem
        if name:
            return name.replace("_", " ").replace("-", " ")
        return doc_id

    @staticmethod
    def _count_lines(content: str) -> int:
        """Count lines in rendered content (including blank lines)."""
        return len(content.strip().splitlines())

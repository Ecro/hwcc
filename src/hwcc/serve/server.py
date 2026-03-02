"""MCP server exposing hwcc's vector store as tools for AI coding agents.

Provides three tools (hw_search, hw_registers, hw_context) and two resources
(hw://peripherals, hw://documents) over stdio transport.  Uses FastMCP with a
lifespan context manager for resource initialisation.

Usage::

    from hwcc.serve.server import run_server
    run_server()  # blocks, serving via stdio
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context, FastMCP

from hwcc.config import load_config
from hwcc.exceptions import HwccError, McpError
from hwcc.manifest import Manifest, load_manifest
from hwcc.project import RAG_DIR, ProjectManager
from hwcc.search import build_where

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from hwcc.embed.base import BaseEmbedder
    from hwcc.search import SearchEngine
    from hwcc.store.base import BaseStore

__all__ = [
    "HwccContext",
    "create_server",
    "handle_hw_context",
    "handle_hw_registers",
    "handle_hw_search",
    "handle_list_documents",
    "handle_list_peripherals",
    "run_server",
]

logger = logging.getLogger(__name__)

# Maximum results a single search can return
_MAX_TOP_K = 50


# ---------------------------------------------------------------------------
# Application context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HwccContext:
    """Typed dependencies shared by all MCP tools (immutable after init)."""

    store: BaseStore
    search_engine: SearchEngine
    project_root: Path
    manifest: Manifest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _validate_peripheral_name(name: str) -> str | None:
    """Validate a peripheral name for safe use in filesystem paths.

    Returns an error message if invalid, or ``None`` if valid.
    """
    if "/" in name or "\\" in name or ".." in name or "\x00" in name:
        return f"Invalid peripheral name: **{name}**"
    return None


def _peripheral_from_section_path(section_path: str) -> str:
    """Extract peripheral name from an SVD section_path.

    SVD section_paths follow::

        "DeviceName Register Map > PeripheralName [> SubSection]"

    Returns the peripheral name (2nd element) or empty string if the
    path cannot be parsed.
    """
    parts = section_path.split(" > ")
    if len(parts) >= 2:
        return parts[1].strip()
    return ""


# ---------------------------------------------------------------------------
# Tool handlers (pure functions — testable without MCP framework)
# ---------------------------------------------------------------------------


def handle_hw_search(
    ctx: HwccContext,
    query: str,
    chip: str = "",
    doc_type: str = "",
    peripheral: str = "",
    top_k: int = 5,
) -> str:
    """Search indexed hardware documentation.

    Returns markdown-formatted results with metadata.
    """
    top_k = max(1, min(top_k, _MAX_TOP_K))

    try:
        results, elapsed = ctx.search_engine.search(
            query, k=top_k, chip=chip, doc_type=doc_type, peripheral=peripheral
        )
    except HwccError as exc:
        logger.error("hw_search failed: %s", exc)
        return f"Search error: {exc}"

    if not results:
        return f"No results found for **{query}**."

    header = f'## Search results for "{query}" ({len(results)} hits, {elapsed:.2f}s)\n'
    lines: list[str] = [header]
    for i, r in enumerate(results, 1):
        meta = r.chunk.metadata
        header_parts: list[str] = []
        if meta.peripheral:
            header_parts.append(meta.peripheral)
        if meta.chip:
            header_parts.append(meta.chip)
        if meta.doc_type:
            header_parts.append(meta.doc_type)
        tag = " | ".join(header_parts) if header_parts else "unknown"

        lines.append(f"### {i}. [{tag}] (score: {r.score:.2f})\n")
        lines.append(r.chunk.content.strip())
        lines.append("")

    return "\n".join(lines)


def handle_hw_registers(
    ctx: HwccContext,
    peripheral: str,
    register: str = "",
    chip: str = "",
) -> str:
    """Get register map documentation for a peripheral.

    Returns markdown register documentation with reset values and fields.
    Filters to ``content_type="register_description"`` by default so only
    SVD-sourced register data is returned (not PDF prose).

    The ``peripheral`` metadata field is not populated during SVD ingestion,
    so we filter by ``section_path`` instead (same approach the compile stage
    uses to discover peripherals).
    """
    where = build_where(
        chip=chip,
        doc_type="svd",
        content_type="register_description",
    )

    try:
        chunks = ctx.store.get_chunks(where=where)
    except HwccError as exc:
        logger.error("hw_registers failed: %s", exc)
        return f"Store error: {exc}"

    # Post-filter by peripheral name extracted from section_path
    periph_upper = peripheral.upper()
    chunks = [
        c
        for c in chunks
        if _peripheral_from_section_path(c.metadata.section_path).upper() == periph_upper
    ]

    # Filter by register name if provided
    if register and chunks:
        register_upper = register.upper()
        chunks = [c for c in chunks if register_upper in c.content.upper()]

    if not chunks:
        qualifier = f" for register {register}" if register else ""
        return f"No register documentation found for **{peripheral}**{qualifier}."

    lines: list[str] = [f"## Registers — {peripheral.upper()}\n"]
    for chunk in chunks:
        lines.append(chunk.content.strip())
        lines.append("")

    return "\n".join(lines)


def handle_hw_context(
    ctx: HwccContext,
    peripheral: str,
    chip: str = "",
) -> str:
    """Get full peripheral context (pre-compiled or from store).

    Looks for pre-compiled files in ``.rag/context/peripherals/`` with
    chip-suffixed names (e.g. ``spi1_stm32f407.md``) first, then plain
    names (``spi1.md``), then a glob fallback.  Falls back to querying
    the store if no pre-compiled file exists.
    """
    error = _validate_peripheral_name(peripheral)
    if error:
        return error
    if chip:
        error = _validate_peripheral_name(chip)
        if error:
            return f"Invalid chip name: **{chip}**"

    periph_lower = peripheral.lower()
    peripherals_dir = (ctx.project_root / RAG_DIR / "context" / "peripherals").resolve()

    # Build candidate file paths: chip-specific first, then generic
    candidates: list[Path] = []
    if chip:
        candidates.append(peripherals_dir / f"{periph_lower}_{chip.lower()}.md")
    candidates.append(peripherals_dir / f"{periph_lower}.md")

    for candidate in candidates:
        if candidate.resolve().is_relative_to(peripherals_dir) and candidate.is_file():
            logger.info("Serving pre-compiled context for %s from %s", peripheral, candidate)
            return candidate.read_text(encoding="utf-8")

    # Glob fallback: find any {periph}_*.md file
    matches = sorted(peripherals_dir.glob(f"{periph_lower}_*.md"))
    matches = [m for m in matches if m.resolve().is_relative_to(peripherals_dir)]
    if matches:
        logger.info("Serving pre-compiled context for %s from %s (glob)", peripheral, matches[0])
        return matches[0].read_text(encoding="utf-8")

    # Store fallback: filter by section_path (peripheral metadata is empty)
    where = build_where(chip=chip, doc_type="svd")

    try:
        chunks = ctx.store.get_chunks(where=where)
    except HwccError as exc:
        logger.error("hw_context failed: %s", exc)
        return f"Store error: {exc}"

    periph_upper = peripheral.upper()
    chunks = [
        c
        for c in chunks
        if _peripheral_from_section_path(c.metadata.section_path).upper() == periph_upper
    ]

    if not chunks:
        return f"No context found for peripheral **{peripheral}**."

    lines: list[str] = [f"## Context — {peripheral.upper()}\n"]
    for chunk in chunks:
        lines.append(chunk.content.strip())
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Resource handlers
# ---------------------------------------------------------------------------


def handle_list_peripherals(ctx: HwccContext) -> str:
    """List all peripherals found in the store.

    Extracts peripheral names from ``section_path`` metadata (the
    ``peripheral`` metadata field is not populated during SVD ingestion).
    """
    try:
        metadata_list = ctx.store.get_chunk_metadata(where={"doc_type": "svd"})
    except HwccError as exc:
        logger.error("list_peripherals failed: %s", exc)
        return f"Store error: {exc}"

    peripherals: dict[str, set[str]] = {}
    for meta in metadata_list:
        periph_name = _peripheral_from_section_path(meta.section_path)
        if periph_name:
            peripherals.setdefault(periph_name, set())
            if meta.chip:
                peripherals[periph_name].add(meta.chip)

    if not peripherals:
        return "No peripherals found in the store."

    lines: list[str] = ["## Indexed Peripherals\n"]
    for name in sorted(peripherals):
        chips = ", ".join(sorted(peripherals[name])) if peripherals[name] else "unknown"
        lines.append(f"- **{name}** ({chips})")

    return "\n".join(lines)


def handle_list_documents(ctx: HwccContext) -> str:
    """List all indexed documents from the manifest."""
    docs = ctx.manifest.documents

    if not docs:
        return "No documents indexed."

    lines: list[str] = ["## Indexed Documents\n"]
    lines.append("| Document | Type | Chip | Chunks |")
    lines.append("|----------|------|------|--------|")
    for doc in docs:
        lines.append(f"| {doc.path} | {doc.doc_type} | {doc.chip or '—'} | {doc.chunks} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP server factory
# ---------------------------------------------------------------------------


def create_server(project_root: Path | None = None) -> FastMCP:
    """Create a FastMCP server instance with hwcc tools and resources.

    Args:
        project_root: Explicit project root.  Defaults to ``cwd`` if *None*.

    The returned server is not started — call ``server.run()`` to serve.
    """
    # Mutable holder for the lifespan context.  Resources in FastMCP 1.x
    # do not support ``Context`` dependency injection (silently dropped),
    # so we use a closure instead.
    _ctx_holder: list[HwccContext] = []

    @asynccontextmanager
    async def _hwcc_lifespan(server: FastMCP) -> AsyncIterator[HwccContext]:
        """Initialise hwcc resources at server startup."""
        project = ProjectManager(root=project_root)
        if not project.is_initialized:
            raise McpError("No hwcc project found. Run 'hwcc init' first.")

        root = project.root
        config = load_config(project.config_path)
        manifest = load_manifest(project.manifest_path)

        # Lazy imports to keep mcp optional at package level
        from hwcc.embed.chromadb_embed import ChromaDBEmbedder
        from hwcc.search import SearchEngine
        from hwcc.store.chroma import ChromaStore

        store = ChromaStore(persist_path=root / RAG_DIR / "index")
        embedder: BaseEmbedder = ChromaDBEmbedder(config)
        engine = SearchEngine(embedder=embedder, store=store)

        logger.info("MCP server initialised (root=%s, chunks=%d)", root, store.count())

        hwcc_ctx = HwccContext(
            store=store,
            search_engine=engine,
            project_root=root,
            manifest=manifest,
        )
        _ctx_holder.append(hwcc_ctx)

        try:
            yield hwcc_ctx
        finally:
            _ctx_holder.clear()
            logger.info("MCP server shutting down")

    mcp = FastMCP("hwcc", lifespan=_hwcc_lifespan)

    # -- Tools ---------------------------------------------------------------

    @mcp.tool()
    def hw_search(
        query: str,
        chip: str = "",
        doc_type: str = "",
        peripheral: str = "",
        top_k: int = 5,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> str:
        """Search indexed hardware documentation.

        Free-text semantic search across all indexed hardware docs (datasheets,
        SVD files, reference manuals).  Use filters to narrow results.
        """
        hwcc_ctx: HwccContext = ctx.request_context.lifespan_context  # type: ignore[union-attr]
        return handle_hw_search(
            hwcc_ctx,
            query=query,
            chip=chip,
            doc_type=doc_type,
            peripheral=peripheral,
            top_k=top_k,
        )

    @mcp.tool()
    def hw_registers(
        peripheral: str,
        register: str = "",
        chip: str = "",
        ctx: Context[Any, Any, Any] | None = None,
    ) -> str:
        """Get register documentation for a peripheral.

        Returns register maps with bit-fields, reset values, and access types
        from SVD data.  Optionally filter to a specific register name.
        """
        hwcc_ctx: HwccContext = ctx.request_context.lifespan_context  # type: ignore[union-attr]
        return handle_hw_registers(hwcc_ctx, peripheral=peripheral, register=register, chip=chip)

    @mcp.tool()
    def hw_context(
        peripheral: str,
        chip: str = "",
        ctx: Context[Any, Any, Any] | None = None,
    ) -> str:
        """Get full peripheral context.

        Returns the complete pre-compiled peripheral context including register
        map, usage patterns, API reference, and errata notes.  Falls back to
        store query if no pre-compiled file exists.
        """
        hwcc_ctx: HwccContext = ctx.request_context.lifespan_context  # type: ignore[union-attr]
        return handle_hw_context(hwcc_ctx, peripheral=peripheral, chip=chip)

    # -- Resources -----------------------------------------------------------
    # FastMCP 1.x silently drops resources whose function signature includes
    # a ``Context`` parameter, so resource functions access the lifespan
    # context via the ``_ctx_holder`` closure instead.

    @mcp.resource("hw://peripherals")
    def peripherals() -> str:
        """List all indexed peripherals with chip information."""
        if not _ctx_holder:
            return "Server not initialized."
        return handle_list_peripherals(_ctx_holder[0])

    @mcp.resource("hw://documents")
    def documents() -> str:
        """List all indexed documents with type, chip, and chunk count."""
        if not _ctx_holder:
            return "Server not initialized."
        return handle_list_documents(_ctx_holder[0])

    return mcp


def run_server(project_root: Path | None = None) -> None:
    """Create and start the MCP server (stdio transport, blocking)."""
    server = create_server(project_root)
    logger.info("Starting hwcc MCP server (stdio)")
    server.run()

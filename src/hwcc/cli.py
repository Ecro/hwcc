"""CLI interface for hwcc.

Typer-based command-line interface with Rich output formatting.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from hwcc import __version__
from hwcc.chunk import MarkdownChunker
from hwcc.config import load_config
from hwcc.exceptions import HwccError
from hwcc.ingest import detect_file_type, get_parser
from hwcc.manifest import (
    DocumentEntry,
    compute_hash,
    load_manifest,
    make_doc_id,
    save_manifest,
)
from hwcc.pipeline import Pipeline
from hwcc.project import ProjectManager
from hwcc.registry import default_registry
from hwcc.store import ChromaStore

__all__ = ["app"]

app = typer.Typer(
    name="hwcc",
    help="Hardware Context Compiler — transforms hardware docs into AI-optimized context.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


def _not_implemented(command: str) -> None:
    """Print a 'not yet implemented' message for stub commands."""
    console.print(
        f"[yellow]hwcc {command}[/yellow] is not yet implemented. Coming in a future release.",
    )
    raise typer.Exit(code=0)


@app.command()
def version() -> None:
    """Show hwcc version."""
    console.print(f"hwcc {__version__}")


@app.command()
def init(
    chip: Annotated[
        str,
        typer.Option("--chip", "-c", help="Target MCU (e.g., STM32F407)"),
    ] = "",
    rtos: Annotated[
        str,
        typer.Option("--rtos", "-r", help="RTOS in use (e.g., FreeRTOS 10.5.1)"),
    ] = "",
    name: Annotated[
        str,
        typer.Option("--name", "-n", help="Project name"),
    ] = "",
) -> None:
    """Initialize a new hwcc project in the current directory."""
    pm = ProjectManager()
    try:
        rag_dir = pm.init(chip=chip, rtos=rtos, name=name)
    except (HwccError, OSError) as e:
        console.print(f"[red]Failed to initialize project:[/red] {e}")
        raise typer.Exit(code=1) from e

    console.print(f"[green]Initialized hwcc project[/green] at {rag_dir}")

    # Print what was created
    console.print("\nCreated:")
    console.print(f"  {rag_dir / 'config.toml'}")
    console.print(f"  {rag_dir / 'manifest.json'}")

    status = pm.status()
    if status.config and status.config.hardware.mcu:
        console.print(f"\n  MCU: [bold]{status.config.hardware.mcu}[/bold]")

    console.print("\nNext steps:")
    console.print("  hwcc add <document>    Add a datasheet, SVD, or reference manual")
    console.print("  hwcc status            Show project status")


def _dir_size(path: Path) -> int:
    """Compute total size in bytes of all files under a directory."""
    if not path.is_dir():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    size_kb = size_bytes / 1024
    if size_kb < 1024:
        return f"{size_kb:.1f} KB"
    size_mb = size_kb / 1024
    return f"{size_mb:.1f} MB"


@app.command()
def status() -> None:
    """Show project status: indexed documents, chunks, config."""
    pm = ProjectManager()
    st = pm.status()

    if not st.initialized:
        console.print("[yellow]No hwcc project found.[/yellow] Run [bold]hwcc init[/bold] first.")
        raise typer.Exit(code=1)

    console.print(f"[bold]hwcc project:[/bold] {st.root.name}")

    if st.config:
        if st.config.hardware.mcu:
            console.print(f"  MCU: {st.config.hardware.mcu}")
        if st.config.software.rtos:
            console.print(f"  RTOS: {st.config.software.rtos}")

    # Summary table
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("metric", style="dim")
    summary.add_column("value", style="bold")
    summary.add_row("Documents", str(st.document_count))
    summary.add_row("Chunks", str(st.chunk_count))

    if st.config:
        embedding_str = f"{st.config.embedding.model} ({st.config.embedding.provider})"
        summary.add_row("Embedding", embedding_str)

    index_size = _dir_size(pm.rag_dir / "index")
    summary.add_row("Index", _format_size(index_size))

    console.print(summary)

    # Per-document table
    if st.document_count > 0:
        manifest = load_manifest(pm.manifest_path)
        doc_table = Table(box=None, padding=(0, 2))
        doc_table.add_column("ID", style="bold")
        doc_table.add_column("Type")
        doc_table.add_column("Chip")
        doc_table.add_column("Chunks", justify="right")
        doc_table.add_column("Added")

        for doc in manifest.documents:
            added_date = doc.added[:10] if len(doc.added) >= 10 else doc.added
            doc_table.add_row(doc.id, doc.doc_type, doc.chip, str(doc.chunks), added_date)

        console.print("\nDocuments:")
        console.print(doc_table)
    else:
        console.print(
            "\n[dim]No documents indexed yet. Run [bold]hwcc add <file>[/bold] to start.[/dim]"
        )


@app.command()
def add(
    paths: Annotated[
        list[str] | None,
        typer.Argument(help="File path(s) to add"),
    ] = None,
    doc_type: Annotated[
        str,
        typer.Option("--type", "-t", help="Document type hint"),
    ] = "auto",
    chip: Annotated[
        str,
        typer.Option("--chip", "-c", help="Chip tag for this document"),
    ] = "",
    watch: Annotated[
        bool,
        typer.Option("--watch", "-w", help="Watch for changes"),
    ] = False,
) -> None:
    """Add document(s) to the index."""
    logger = logging.getLogger(__name__)

    if watch:
        console.print("[yellow]--watch is not yet implemented.[/yellow]")
        raise typer.Exit(code=0)

    pm = ProjectManager()
    if not pm.is_initialized:
        console.print("[yellow]No hwcc project found.[/yellow] Run [bold]hwcc init[/bold] first.")
        raise typer.Exit(code=1)

    if not paths:
        console.print("[yellow]No file paths provided.[/yellow] Usage: hwcc add <file> [file ...]")
        raise typer.Exit(code=1)

    config = load_config(pm.config_path)
    manifest = load_manifest(pm.manifest_path)

    # Build shared pipeline components
    try:
        chunker = MarkdownChunker()
        embedder = default_registry.create("embedding", config.embedding.provider, config)
        store = ChromaStore(
            persist_path=pm.rag_dir / "index",
            collection_name=config.store.collection_name,
        )
    except HwccError as e:
        console.print(f"[red]Failed to initialize pipeline:[/red] {e}")
        raise typer.Exit(code=1) from e

    added_count = 0
    skipped_count = 0
    total_chunks = 0

    for path_str in paths:
        file_path = Path(path_str).resolve()

        if not file_path.exists():
            console.print(f"  [red]File not found:[/red] {path_str}")
            continue

        # Detect file type
        info = detect_file_type(file_path)
        if not info.parser_name:
            console.print(
                f"  [yellow]Unsupported format:[/yellow] {file_path.name} ({info.format})"
            )
            continue

        # Determine effective doc_type and chip
        effective_doc_type = doc_type if doc_type != "auto" else str(info.doc_type)
        effective_chip = chip or config.hardware.mcu

        # Check manifest for changes
        doc_id = make_doc_id(file_path)
        file_hash = compute_hash(file_path)

        if not manifest.is_changed(doc_id, file_hash):
            console.print(f"  [dim]Skipped {file_path.name} (unchanged)[/dim]")
            skipped_count += 1
            continue

        console.print(f"Processing [bold]{file_path.name}[/bold] ...")

        # Remove old chunks if re-indexing a changed document
        if manifest.get_document(doc_id) is not None:
            try:
                store.delete(doc_id)
            except HwccError as e:
                logger.warning("Failed to remove old chunks for %s: %s", doc_id, e)

        # Build pipeline for this file
        try:
            parser = get_parser(info.parser_name)
            pipeline = Pipeline(
                parser=parser,
                chunker=chunker,
                embedder=embedder,
                store=store,
                config=config,
            )
            chunk_count = pipeline.process(
                path=file_path,
                doc_id=doc_id,
                doc_type=effective_doc_type,
                chip=effective_chip,
            )
        except HwccError as e:
            console.print(f"  [red]Error processing {file_path.name}:[/red] {e}")
            logger.error("Failed to process %s: %s", file_path, e)
            continue

        # Store relative path when file is inside the project root
        try:
            stored_path = str(file_path.relative_to(pm.root))
        except ValueError:
            stored_path = str(file_path)

        # Update manifest with the already-computed hash (avoid double-hashing)
        entry = DocumentEntry(
            id=doc_id,
            path=stored_path,
            doc_type=effective_doc_type,
            hash=file_hash,
            added=datetime.now(UTC).isoformat(),
            chunks=chunk_count,
            chip=effective_chip,
        )
        manifest.add_document(entry)
        save_manifest(manifest, pm.manifest_path)

        console.print(f"  [green]Added {file_path.name}[/green] ({chunk_count} chunks)")
        added_count += 1
        total_chunks += chunk_count

    # Summary
    if added_count > 0:
        console.print(
            f"\n[green]Added {added_count} document(s)[/green] ({total_chunks} chunks total)"
        )
    elif skipped_count > 0:
        console.print("\n[dim]No new documents to add.[/dim]")


@app.command()
def remove(
    doc_id: Annotated[str, typer.Argument(help="Document ID or path to remove")],
) -> None:
    """Remove a document from the index."""
    pm = ProjectManager()
    if not pm.is_initialized:
        console.print("[yellow]No hwcc project found.[/yellow] Run [bold]hwcc init[/bold] first.")
        raise typer.Exit(code=1)

    config = load_config(pm.config_path)
    manifest = load_manifest(pm.manifest_path)

    # Resolve doc_id: try direct lookup first, then try as file path
    entry = manifest.get_document(doc_id)
    if entry is None:
        resolved_id = make_doc_id(Path(doc_id))
        entry = manifest.get_document(resolved_id)
        if entry is not None:
            doc_id = resolved_id

    if entry is None:
        console.print(f"[red]Document not found:[/red] {doc_id}")
        raise typer.Exit(code=1)

    # Delete chunks from store
    try:
        store = ChromaStore(
            persist_path=pm.rag_dir / "index",
            collection_name=config.store.collection_name,
        )
        deleted_chunks = store.delete(doc_id)
    except HwccError as e:
        console.print(f"[red]Failed to delete chunks:[/red] {e}")
        raise typer.Exit(code=1) from e

    # Remove from manifest
    manifest.remove_document(doc_id)
    save_manifest(manifest, pm.manifest_path)

    console.print(f"[green]Removed {doc_id}[/green] ({deleted_chunks} chunks deleted)")


@app.command(name="compile")
def compile_cmd(
    target: Annotated[
        str,
        typer.Option("--target", "-t", help="Target tool (claude, codex, cursor, gemini, all)"),
    ] = "all",
) -> None:
    """Regenerate all output context files."""
    _not_implemented("compile")


@app.command()
def context(
    query: Annotated[
        str | None,
        typer.Argument(help="Peripheral name or search query"),
    ] = None,
    copy: Annotated[
        bool,
        typer.Option("--copy", help="Copy to clipboard"),
    ] = False,
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format (md, json, text)"),
    ] = "md",
) -> None:
    """Retrieve context for a peripheral or query."""
    _not_implemented("context")


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    top_k: Annotated[
        int,
        typer.Option("--top-k", "-k", help="Number of results"),
    ] = 5,
) -> None:
    """Search indexed documents."""
    _not_implemented("search")


@app.command()
def mcp(
    port: Annotated[
        int | None,
        typer.Option("--port", "-p", help="HTTP port (default: stdio)"),
    ] = None,
) -> None:
    """Start MCP server."""
    _not_implemented("mcp")


@app.command(name="config")
def config_cmd(
    key: Annotated[
        str | None,
        typer.Argument(help="Config key to get/set"),
    ] = None,
    value: Annotated[
        str | None,
        typer.Argument(help="Value to set"),
    ] = None,
) -> None:
    """Get or set configuration values."""
    _not_implemented("config")

"""CLI interface for hwcc.

Typer-based command-line interface with Rich output formatting.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from hwcc import __version__
from hwcc.chunk import MarkdownChunker
from hwcc.compile.hot_context import HotContextCompiler
from hwcc.compile.output import OutputCompiler
from hwcc.compile.peripheral import PeripheralContextCompiler
from hwcc.compile.templates import TARGET_REGISTRY
from hwcc.config import load_config
from hwcc.exceptions import BenchmarkError, CatalogError, CompileError, HwccError, StoreError
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


@app.callback()
def _main_callback(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug logging"),
    ] = False,
) -> None:
    """Configure global options."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.getLogger("hwcc").setLevel(level)


def _not_implemented(command: str) -> None:
    """Print a 'not yet implemented' message for stub commands."""
    console.print(
        f"[yellow]hwcc {command}[/yellow] is not yet implemented. Coming in a future release.",
    )
    raise typer.Exit(code=0)


def _compile_project(pm: ProjectManager, target: str = "all") -> list[Path]:
    """Run the compile pipeline: Hot → Peripheral → Output.

    Args:
        pm: Initialized ProjectManager.
        target: Target tool name or "all".

    Returns:
        List of generated file paths.

    Raises:
        typer.Exit: On compile errors.
    """
    config = load_config(pm.config_path)

    # Validate and filter targets
    if target != "all":
        if target not in TARGET_REGISTRY:
            supported = ", ".join(sorted(TARGET_REGISTRY))
            console.print(f"[red]Unknown target:[/red] {target!r}. Supported: {supported}")
            raise typer.Exit(code=1)
        config = replace(config, output=replace(config.output, targets=[target]))

    generated: list[Path] = []

    try:
        store = ChromaStore(
            persist_path=pm.rag_dir / "index",
            collection_name=config.store.collection_name,
        )

        # 1. Hot context — must run first (Output reads hot.md)
        hot = HotContextCompiler(pm.root)
        generated.extend(hot.compile(store, config))

        # 2. Peripheral context
        periph = PeripheralContextCompiler(pm.root)
        generated.extend(periph.compile(store, config))

        # 3. Output files (CLAUDE.md, etc.)
        out = OutputCompiler(pm.root)
        generated.extend(out.compile(store, config))
    except (CompileError, StoreError) as e:
        console.print(f"[red]Compile error:[/red] {e}")
        raise typer.Exit(code=1) from e

    return generated


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
    no_compile: Annotated[
        bool,
        typer.Option("--no-compile", help="Skip auto-compile after adding"),
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
        effective_doc_type = doc_type if doc_type != "auto" else info.doc_type.value
        effective_chip = chip or config.hardware.mcu

        # Check manifest for changes
        doc_id = make_doc_id(file_path)
        file_hash = compute_hash(file_path)

        if not manifest.is_changed(doc_id, file_hash):
            console.print(f"  [dim]Skipped {file_path.name} (unchanged)[/dim]")
            skipped_count += 1
            continue

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
            t0 = time.monotonic()
            with console.status(f"Processing [bold]{file_path.name}[/bold] ...", spinner="dots"):
                chunk_count = pipeline.process(
                    path=file_path,
                    doc_id=doc_id,
                    doc_type=effective_doc_type,
                    chip=effective_chip,
                )
            logger.info(
                "Processed %s in %.1fs (%d chunks)",
                file_path.name,
                time.monotonic() - t0,
                chunk_count,
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
        # Auto-compile after successful additions
        if not no_compile:
            with console.status("Compiling context...", spinner="dots"):
                generated = _compile_project(pm)
            if generated:
                console.print(f"[green]Compiled {len(generated)} file(s)[/green]")
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
    pm = ProjectManager()
    if not pm.is_initialized:
        console.print("[yellow]No hwcc project found.[/yellow] Run [bold]hwcc init[/bold] first.")
        raise typer.Exit(code=1)

    generated = _compile_project(pm, target=target)

    if generated:
        console.print(f"\n[green]Compiled {len(generated)} file(s):[/green]")
        for p in generated:
            try:
                rel = p.relative_to(pm.root)
            except ValueError:
                rel = p
            console.print(f"  {rel}")
    else:
        console.print("[dim]Nothing to compile.[/dim]")


@app.command(hidden=True)
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


@app.command(hidden=True)
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    top_k: Annotated[
        int,
        typer.Option("--top-k", "-k", help="Number of results"),
    ] = 5,
) -> None:
    """Search indexed documents."""
    _not_implemented("search")


@app.command(hidden=True)
def mcp(
    port: Annotated[
        int | None,
        typer.Option("--port", "-p", help="HTTP port (default: stdio)"),
    ] = None,
) -> None:
    """Start MCP server."""
    _not_implemented("mcp")


@app.command(name="config", hidden=True)
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


# --- Catalog sub-app ---

catalog_app = typer.Typer(
    name="catalog",
    help="Browse and add SVD files from the cmsis-svd catalog.",
    no_args_is_help=True,
)
app.add_typer(catalog_app)


@catalog_app.command(name="list")
def catalog_list(
    query: Annotated[
        str | None,
        typer.Argument(help="Search query (device name substring)"),
    ] = None,
    vendor: Annotated[
        str,
        typer.Option("--vendor", "-v", help="Filter by vendor name"),
    ] = "",
) -> None:
    """List or search SVD devices in the catalog."""
    from hwcc.catalog import CatalogIndex

    try:
        catalog = CatalogIndex.load()
    except CatalogError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    if query:
        # Search mode
        results = catalog.search(query, vendor=vendor)
        if not results:
            console.print(f"[yellow]No devices matching[/yellow] '{query}'")
            raise typer.Exit(code=0)

        table = Table(title=f"Found {len(results)} device(s) matching '{query}'")
        table.add_column("Device", style="bold")
        table.add_column("Vendor", style="cyan")
        for entry in results:
            table.add_row(entry.name, entry.vendor)
        console.print(table)
        console.print(
            "\n[dim]Use [bold]hwcc catalog add <device>[/bold]"
            " to add to your project.[/dim]"
        )

    elif vendor:
        # Vendor filter mode (no query)
        results = catalog.search("", vendor=vendor)
        if not results:
            console.print(f"[yellow]No devices for vendor[/yellow] '{vendor}'")
            raise typer.Exit(code=0)

        table = Table(title=f"{vendor} — {len(results)} device(s)")
        table.add_column("Device", style="bold")
        for entry in results:
            table.add_row(entry.name)
        console.print(table)

    else:
        # Summary mode — list vendors with counts
        vendors = catalog.vendors()
        title = f"SVD Catalog \u2014 {catalog.device_count} devices from {len(vendors)} vendors"
        table = Table(title=title)
        table.add_column("Vendor", style="bold")
        table.add_column("Devices", justify="right", style="cyan")
        for name, count in vendors:
            table.add_row(name, str(count))
        console.print(table)
        console.print(
            "\n[dim]Use [bold]hwcc catalog list <query>[/bold] to search devices.[/dim]"
        )


@catalog_app.command(name="add")
def catalog_add(
    device: Annotated[
        str,
        typer.Argument(help="Device name to add (e.g. STM32F407)"),
    ],
    chip: Annotated[
        str,
        typer.Option("--chip", "-c", help="Chip tag override"),
    ] = "",
    no_compile: Annotated[
        bool,
        typer.Option("--no-compile", help="Skip auto-compile after adding"),
    ] = False,
) -> None:
    """Download an SVD file from the catalog and add it to the project."""
    import tempfile

    from hwcc.catalog import CatalogIndex, download_svd

    pm = ProjectManager()
    if not pm.is_initialized:
        console.print("[yellow]No hwcc project found.[/yellow] Run [bold]hwcc init[/bold] first.")
        raise typer.Exit(code=1)

    # Load catalog and find device
    try:
        catalog = CatalogIndex.load()
    except CatalogError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    entry = catalog.find_exact(device)
    if entry is None:
        # Try substring search for suggestions
        results = catalog.search(device)
        if results:
            console.print(f"[yellow]No exact match for[/yellow] '{device}'")
            console.print("\n[dim]Did you mean one of these?[/dim]")
            for r in results[:10]:
                console.print(f"  {r.name} ({r.vendor})")
        else:
            console.print(f"[red]No device found matching[/red] '{device}'")
        raise typer.Exit(code=1)

    # Download SVD to temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            msg = f"Downloading [bold]{entry.name}[/bold] from cmsis-svd..."
            with console.status(msg, spinner="dots"):
                svd_path = download_svd(entry, Path(tmpdir))
        except CatalogError as e:
            console.print(f"[red]Download failed:[/red] {e}")
            raise typer.Exit(code=1) from e

        # Process through the standard add pipeline
        config = load_config(pm.config_path)
        manifest = load_manifest(pm.manifest_path)

        effective_chip = chip or entry.name
        doc_id = make_doc_id(svd_path)
        file_hash = compute_hash(svd_path)

        # Remove old chunks if re-indexing
        if manifest.get_document(doc_id) is not None:
            try:
                store = ChromaStore(
                    persist_path=pm.rag_dir / "index",
                    collection_name=config.store.collection_name,
                )
                store.delete(doc_id)
            except HwccError as e:
                logging.getLogger(__name__).warning(
                    "Failed to remove old chunks for %s: %s", doc_id, e,
                )

        try:
            chunker = MarkdownChunker()
            embedder = default_registry.create("embedding", config.embedding.provider, config)
            store = ChromaStore(
                persist_path=pm.rag_dir / "index",
                collection_name=config.store.collection_name,
            )
            parser = get_parser("svd")
            pipeline = Pipeline(
                parser=parser,
                chunker=chunker,
                embedder=embedder,
                store=store,
                config=config,
            )
            with console.status(f"Indexing [bold]{entry.name}[/bold]...", spinner="dots"):
                chunk_count = pipeline.process(
                    path=svd_path,
                    doc_id=doc_id,
                    doc_type="svd",
                    chip=effective_chip,
                )
        except HwccError as e:
            console.print(f"[red]Failed to process {entry.name}:[/red] {e}")
            raise typer.Exit(code=1) from e

        # Update manifest
        manifest_entry = DocumentEntry(
            id=doc_id,
            path=f"catalog:{entry.vendor}/{entry.name}",
            doc_type="svd",
            hash=file_hash,
            added=datetime.now(UTC).isoformat(),
            chunks=chunk_count,
            chip=effective_chip,
        )
        manifest.add_document(manifest_entry)
        save_manifest(manifest, pm.manifest_path)

    console.print(f"[green]Added {entry.name}[/green] ({entry.vendor}, {chunk_count} chunks)")

    # Auto-compile
    if not no_compile:
        with console.status("Compiling context...", spinner="dots"):
            generated = _compile_project(pm)
        if generated:
            console.print(f"[green]Compiled {len(generated)} file(s)[/green]")


# --- Benchmark sub-app ---

bench_app = typer.Typer(
    name="bench",
    help="HwBench — hardware context benchmark suite.",
    no_args_is_help=True,
)
app.add_typer(bench_app)


@bench_app.command(name="generate")
def bench_generate(
    svd_file: Annotated[
        str,
        typer.Argument(help="Path to SVD file"),
    ],
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output dataset JSON path"),
    ] = "",
    peripherals: Annotated[
        int,
        typer.Option("--peripherals", "-p", help="Max peripherals to include"),
    ] = 10,
    chip: Annotated[
        str,
        typer.Option("--chip", "-c", help="Chip name override"),
    ] = "",
) -> None:
    """Generate benchmark dataset from an SVD file."""
    from hwcc.bench.dataset import generate_dataset, save_dataset

    svd_path = Path(svd_file).resolve()
    if not svd_path.exists():
        console.print(f"[red]SVD file not found:[/red] {svd_file}")
        raise typer.Exit(code=1)

    try:
        with console.status("Generating dataset...", spinner="dots"):
            dataset = generate_dataset(svd_path, num_peripherals=peripherals, chip=chip)
    except BenchmarkError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    # Default output path
    out_path = Path(output) if output else Path(f"{dataset.name.lower()}_dataset.json")

    try:
        save_dataset(dataset, out_path)
    except BenchmarkError as e:
        console.print(f"[red]Failed to save:[/red] {e}")
        raise typer.Exit(code=1) from e

    console.print(f"[green]Generated {dataset.question_count} questions[/green]")
    console.print(f"  Chip: {dataset.chip}")
    console.print(f"  Categories: {', '.join(dataset.categories)}")
    console.print(f"  Saved to: {out_path}")


@bench_app.command(name="run")
def bench_run(
    dataset_file: Annotated[
        str,
        typer.Argument(help="Path to dataset JSON file"),
    ],
    provider: Annotated[
        str,
        typer.Option("--provider", help="LLM provider (anthropic, openai, ollama)"),
    ] = "anthropic",
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="Model name"),
    ] = "",
    conditions: Annotated[
        str,
        typer.Option("--conditions", help="Comma-separated condition names"),
    ] = "no_context,hwcc_full",
    context_dir: Annotated[
        str,
        typer.Option("--context-dir", help="Path to .rag/context/ directory"),
    ] = "",
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output report JSON path"),
    ] = "",
    delay: Annotated[
        float,
        typer.Option("--delay", help="Delay between API calls (seconds)"),
    ] = 0.5,
) -> None:
    """Run benchmark against an LLM provider."""
    from rich.progress import Progress

    from hwcc.bench.dataset import load_dataset
    from hwcc.bench.providers import create_provider
    from hwcc.bench.report import generate_report, print_report, save_report
    from hwcc.bench.runner import prepare_conditions, run_benchmark

    # Load dataset
    dataset_path = Path(dataset_file)
    try:
        dataset = load_dataset(dataset_path)
    except BenchmarkError as e:
        console.print(f"[red]Error loading dataset:[/red] {e}")
        raise typer.Exit(code=1) from e

    # Create provider
    try:
        llm = create_provider(provider, model=model)
    except BenchmarkError as e:
        console.print(f"[red]Provider error:[/red] {e}")
        raise typer.Exit(code=1) from e

    # Prepare conditions
    ctx_path = Path(context_dir) if context_dir else None
    if not ctx_path:
        # Try to find .rag/context/ in current directory
        pm = ProjectManager()
        if pm.is_initialized:
            ctx_path = pm.rag_dir / "context"

    requested_conditions = [c.strip() for c in conditions.split(",")]
    peripheral_names = list({q.peripheral for q in dataset.questions})
    all_conditions = prepare_conditions(ctx_path, dataset.chip, peripheral_names)
    filtered = [c for c in all_conditions if c.name in requested_conditions]

    if not filtered:
        console.print(
            f"[red]No valid conditions found.[/red] "
            f"Available: {', '.join(c.name for c in all_conditions)}"
        )
        raise typer.Exit(code=1)

    console.print(f"[bold]HwBench[/bold] — {dataset.chip}")
    console.print(f"  Dataset: {dataset.question_count} questions")
    console.print(f"  Model: {llm.model_name} ({llm.name})")
    console.print(f"  Conditions: {', '.join(c.name for c in filtered)}")
    console.print()

    # Run with progress bar
    with Progress(console=console) as progress:
        task_ids: dict[str, object] = {}

        def on_progress(condition_name: str, idx: int, total: int) -> None:
            if condition_name not in task_ids:
                task_ids[condition_name] = progress.add_task(
                    f"[cyan]{condition_name}[/cyan]", total=total
                )
            progress.update(task_ids[condition_name], completed=idx + 1)  # type: ignore[arg-type]

        try:
            runs = run_benchmark(
                dataset=dataset,
                provider=llm,
                conditions=filtered,
                delay_seconds=delay,
                progress_callback=on_progress,
            )
        except BenchmarkError as e:
            console.print(f"\n[red]Benchmark error:[/red] {e}")
            raise typer.Exit(code=1) from e

    # Generate and display report
    report = generate_report(runs, chip=dataset.chip)
    print_report(report, console=console)

    # Save report
    out_path = Path(output) if output else Path(f"{dataset.name.lower()}_report.json")
    try:
        save_report(report, out_path)
        console.print(f"[green]Report saved to:[/green] {out_path}")
    except BenchmarkError as e:
        console.print(f"[yellow]Warning: failed to save report:[/yellow] {e}")


@bench_app.command(name="report")
def bench_report_cmd(
    report_file: Annotated[
        str,
        typer.Argument(help="Path to report JSON file"),
    ],
) -> None:
    """Display a previously saved benchmark report."""
    from hwcc.bench.report import load_report, print_report

    report_path = Path(report_file)
    try:
        report = load_report(report_path)
    except BenchmarkError as e:
        console.print(f"[red]Error loading report:[/red] {e}")
        raise typer.Exit(code=1) from e

    print_report(report, console=console)

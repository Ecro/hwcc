"""CLI interface for hwcc.

Typer-based command-line interface with Rich output formatting.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from hwcc import __version__
from hwcc.project import ProjectManager

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
    rag_dir = pm.init(chip=chip, rtos=rtos, name=name)

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

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("metric", style="dim")
    table.add_column("value", style="bold")
    table.add_row("Documents", str(st.document_count))
    table.add_row("Chunks", str(st.chunk_count))
    console.print(table)

    if st.document_count == 0:
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
    _not_implemented("add")


@app.command()
def remove(
    doc_id: Annotated[str, typer.Argument(help="Document ID or path to remove")],
) -> None:
    """Remove a document from the index."""
    _not_implemented("remove")


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

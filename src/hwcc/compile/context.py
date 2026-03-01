"""Template context data structures for the compile stage.

These frozen dataclasses define the contract between the compile logic
(which populates them) and the Jinja2 templates (which consume them).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import PurePosixPath

    from hwcc.config import HwccConfig

__all__ = [
    "CompileContext",
    "DocumentSummary",
    "ErrataSummary",
    "PeripheralSummary",
    "TargetInfo",
]


@dataclass(frozen=True)
class TargetInfo:
    """Metadata for an output target (claude, codex, cursor, etc.)."""

    template: str
    output_path: PurePosixPath
    begin_marker: str
    end_marker: str
    description: str


@dataclass(frozen=True)
class DocumentSummary:
    """Summary of an indexed document for template rendering."""

    doc_id: str
    title: str
    doc_type: str
    chip: str = ""
    chunk_count: int = 0


@dataclass(frozen=True)
class PeripheralSummary:
    """Summary of a peripheral for template rendering."""

    name: str
    description: str = ""
    register_count: int = 0
    chip: str = ""


@dataclass(frozen=True)
class ErrataSummary:
    """Summary of an errata entry for template rendering."""

    errata_id: str
    title: str
    description: str = ""
    affected_peripheral: str = ""
    severity: str = "medium"


@dataclass(frozen=True)
class CompileContext:
    """All data available to templates during compilation.

    Populated by the compile stage (tasks 2.1, 2.2) and passed
    to TemplateEngine.render().
    """

    # From config — project
    project_name: str = ""
    project_description: str = ""

    # From config — hardware
    mcu: str = ""
    mcu_family: str = ""
    architecture: str = ""
    clock_mhz: int = 0
    flash_kb: int = 0
    ram_kb: int = 0
    soc: str = ""
    soc_family: str = ""
    board: str = ""

    # From config — software
    rtos: str = ""
    hal: str = ""
    language: str = "C"
    build_system: str = ""
    kernel: str = ""
    bootloader: str = ""
    distro: str = ""

    # From config — conventions
    register_access: str = ""
    error_handling: str = ""
    naming: str = ""

    # Compiled data (populated by tasks 2.1, 2.2)
    documents: tuple[DocumentSummary, ...] = ()
    peripherals: tuple[PeripheralSummary, ...] = ()
    errata: tuple[ErrataSummary, ...] = ()

    # Peripheral-specific (only for peripheral.md.j2)
    peripheral_name: str = ""
    peripheral_description: str = ""
    register_map: str = ""
    peripheral_details: str = ""

    # Metadata
    hwcc_version: str = ""
    generated_at: str = ""
    mcp_available: bool = False

    # Pre-rendered content (for target templates that embed hot context)
    hot_context: str = ""

    @classmethod
    def from_config(cls, config: HwccConfig) -> CompileContext:
        """Create a CompileContext pre-filled from project configuration."""
        from hwcc import __version__

        return cls(
            project_name=config.project.name,
            project_description=config.project.description,
            mcu=config.hardware.mcu,
            mcu_family=config.hardware.mcu_family,
            architecture=config.hardware.architecture,
            clock_mhz=config.hardware.clock_mhz,
            flash_kb=config.hardware.flash_kb,
            ram_kb=config.hardware.ram_kb,
            soc=config.hardware.soc,
            soc_family=config.hardware.soc_family,
            board=config.hardware.board,
            rtos=config.software.rtos,
            hal=config.software.hal,
            language=config.software.language,
            build_system=config.software.build_system,
            kernel=config.software.kernel,
            bootloader=config.software.bootloader,
            distro=config.software.distro,
            register_access=config.conventions.register_access,
            error_handling=config.conventions.error_handling,
            naming=config.conventions.naming,
            hwcc_version=__version__,
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        )

"""CMSIS-SVD file parser — converts SVD files into structured markdown register maps."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hwcc.exceptions import ParseError
from hwcc.ingest.base import BaseParser
from hwcc.types import ParseResult

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from cmsis_svd.model import (
        SVDAccessType,
        SVDDevice,
        SVDField,
        SVDFieldArray,
        SVDPeripheral,
        SVDPeripheralArray,
        SVDRegister,
        SVDRegisterArray,
        SVDRegisterCluster,
        SVDRegisterClusterArray,
    )

    from hwcc.config import HwccConfig

    # SVD register list type from the library
    SvdRegisterItem = SVDRegister | SVDRegisterArray | SVDRegisterCluster | SVDRegisterClusterArray
    SvdFieldItem = SVDField | SVDFieldArray

__all__ = ["SvdParser"]

logger = logging.getLogger(__name__)

# DTD patterns that indicate potentially unsafe XML (XXE attack vectors)
_UNSAFE_XML_PATTERNS = ("<!DOCTYPE", "<!ENTITY")


class SvdParser(BaseParser):
    """Parser for CMSIS-SVD files.

    Extracts peripheral register maps from SVD XML files and generates
    structured markdown with register tables and field-level detail.

    This parser is 100% deterministic — no LLM dependency.
    """

    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100 MB

    def parse(self, path: Path, config: HwccConfig) -> ParseResult:
        """Parse an SVD file into a ParseResult with markdown register maps.

        Args:
            path: Path to the .svd file.
            config: Project configuration.

        Returns:
            ParseResult with structured markdown content.

        Raises:
            ParseError: If the SVD file cannot be parsed.
        """
        try:
            from cmsis_svd.parser import SVDParser
        except ImportError as e:
            msg = "cmsis-svd library is required for SVD parsing: pip install cmsis-svd"
            raise ParseError(msg) from e

        if not path.exists():
            msg = f"SVD file not found: {path.name}"
            raise ParseError(msg)

        file_size = path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            msg = (
                f"SVD file {path.name} ({file_size} bytes) "
                f"exceeds maximum size ({self.MAX_FILE_SIZE} bytes)"
            )
            raise ParseError(msg)

        # XXE mitigation: reject SVD files with DTD declarations before parsing.
        # cmsis-svd uses lxml.etree.parse() which does not disable external
        # entities by default. Vendor SVD files should never contain DTDs.
        _check_xml_safety(path)

        logger.info("Parsing SVD file: %s", path)

        try:
            svd_parser = SVDParser.for_xml_file(str(path))
            device = svd_parser.get_device()
        except ParseError:
            raise
        except Exception as e:
            logger.debug("SVD parse failure (%s): %s", type(e).__name__, e, exc_info=True)
            msg = f"Failed to parse SVD file {path.name}: {e}"
            raise ParseError(msg) from e

        chip_name = device.name or path.stem
        content = self._render_device(device)

        peripheral_count = len(device.peripherals) if device.peripherals else 0
        register_count = self._count_registers(device)
        cpu_name = _get_cpu_name(device)

        metadata = (
            ("peripheral_count", str(peripheral_count)),
            ("register_count", str(register_count)),
            ("cpu", cpu_name),
        )

        logger.info(
            "Parsed %s: %d peripherals, %d registers",
            chip_name,
            peripheral_count,
            register_count,
        )

        return ParseResult(
            doc_id=path.stem.lower().replace("-", "_").replace(" ", "_") + "_svd",
            content=content,
            doc_type="svd",
            title=f"{chip_name} Register Map",
            source_path=str(path),
            chip=chip_name,
            metadata=metadata,
        )

    def supported_extensions(self) -> frozenset[str]:
        """Return supported file extensions."""
        return frozenset({".svd"})

    # --- Internal helpers ---

    def _render_device(self, device: SVDDevice) -> str:
        """Render the full device as markdown."""
        lines: list[str] = []

        # Device header
        lines.append(f"# {device.name} Register Map")
        lines.append("")
        lines.append(f"**Device:** {device.name}")
        if device.description:
            lines.append(f"**Description:** {device.description.strip()}")
        if device.cpu:
            cpu_name = _get_cpu_name(device)
            cpu_info = cpu_name
            if device.cpu.revision:
                cpu_info += f", revision {device.cpu.revision}"
            lines.append(f"**CPU:** {cpu_info}")
        lines.append("")

        # Peripherals (sorted alphabetically)
        if device.peripherals:
            peripherals = _expand_peripherals(device.peripherals)
            peripherals.sort(key=lambda p: p.name or "")
            for peripheral in peripherals:
                lines.append("---")
                lines.append("")
                lines.extend(self._render_peripheral(peripheral))
        else:
            lines.append("*No peripherals defined.*")
            lines.append("")

        return "\n".join(lines)

    def _render_peripheral(self, peripheral: SVDPeripheral) -> list[str]:
        """Render a single peripheral section."""
        lines: list[str] = []

        lines.append(f"## {peripheral.name}")
        lines.append("")
        if peripheral.base_address is not None:
            lines.append(f"**Base Address:** `0x{peripheral.base_address:08X}`")
        if peripheral.description:
            lines.append(f"**Description:** {peripheral.description.strip()}")
        lines.append("")

        if not peripheral.registers:
            lines.append("*No registers defined.*")
            lines.append("")
            return lines

        # Collect all registers (flattening any clusters)
        registers = _collect_registers(peripheral.registers)

        # Sort by address offset
        registers.sort(key=lambda r: r.address_offset if r.address_offset is not None else 0)

        # Register summary table
        lines.append("### Registers")
        lines.append("")
        lines.append("| Register | Offset | Size | Access | Reset | Description |")
        lines.append("|----------|--------|------|--------|-------|-------------|")
        for reg in registers:
            offset = _format_hex(reg.address_offset, 4) if reg.address_offset is not None else "—"
            size = str(reg.size) if reg.size is not None else "—"
            access = _format_access(reg.access)
            reset = _format_hex(reg.reset_value, 8) if reg.reset_value is not None else "—"
            desc = (reg.description or "").strip()
            lines.append(f"| {reg.name} | {offset} | {size} | {access} | {reset} | {desc} |")
        lines.append("")

        # Field detail tables (only for registers that have fields)
        for reg in registers:
            if reg.fields:
                lines.extend(
                    self._render_field_table(reg.name or "?", reg.fields, reg.reset_value)
                )

        return lines

    def _render_field_table(
        self,
        register_name: str,
        fields: Sequence[SvdFieldItem],
        register_reset_value: int | None = None,
    ) -> list[str]:
        """Render a field detail table for a register."""
        from cmsis_svd.model import SVDField

        lines: list[str] = []
        lines.append(f"### {register_name} Fields")
        lines.append("")
        lines.append("| Field | Bits | Access | Reset | Description |")
        lines.append("|-------|------|--------|-------|-------------|")

        # Sort fields by bit position (descending — MSB first)
        typed_fields: list[SVDField] = [f for f in fields if isinstance(f, SVDField)]
        typed_fields.sort(
            key=lambda f: (f.bit_offset or 0) + (f.bit_width or 1) - 1,
            reverse=True,
        )

        for field in typed_fields:
            bit_offset = field.bit_offset or 0
            bit_width = field.bit_width or 1
            bits = _format_bit_range(bit_offset, bit_width)
            access = _format_access(field.access)
            if register_reset_value is not None:
                reset = _compute_field_reset(register_reset_value, bit_offset, bit_width)
            else:
                reset = "—"
            desc = (field.description or "").strip()
            lines.append(f"| {field.name} | {bits} | {access} | {reset} | {desc} |")

        lines.append("")
        return lines

    def _count_registers(self, device: SVDDevice) -> int:
        """Count total registers across all peripherals."""
        total = 0
        if device.peripherals:
            for peripheral in _expand_peripherals(device.peripherals):
                if peripheral.registers:
                    total += len(_collect_registers(peripheral.registers))
        return total


# --- Module-level helpers ---


def _check_xml_safety(path: Path) -> None:
    """Reject SVD files containing DTD declarations (XXE mitigation).

    The cmsis-svd library uses lxml.etree.parse() which does not disable
    external entity resolution by default. Valid CMSIS-SVD files never
    contain DTD declarations, so rejecting them is safe.

    DTD declarations always appear before the root element, so reading
    a prefix is sufficient and avoids loading huge files into memory.

    Raises:
        ParseError: If the file contains unsafe XML constructs.
    """
    # Note: A crafted file with >8KB of comments before the DTD could bypass
    # this check. Full protection requires configuring lxml to disable
    # external entity resolution (tracked as a future improvement).
    _SAFETY_PROBE_SIZE = 8192
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            head = f.read(_SAFETY_PROBE_SIZE)
    except OSError as e:
        msg = f"Cannot read SVD file {path.name}: {e}"
        raise ParseError(msg) from e

    for pattern in _UNSAFE_XML_PATTERNS:
        if pattern in head:
            msg = f"SVD file contains potentially unsafe XML ({pattern}): {path.name}"
            raise ParseError(msg)


def _expand_peripherals(
    items: Sequence[SVDPeripheral | SVDPeripheralArray],
) -> list[SVDPeripheral]:
    """Expand a list of peripheral/peripheral-array items into flat peripheral list."""
    from cmsis_svd.model import SVDPeripheral, SVDPeripheralArray

    result: list[SVDPeripheral] = []
    for item in items:
        if isinstance(item, SVDPeripheral):
            result.append(item)
        elif isinstance(item, SVDPeripheralArray):
            result.extend(item.peripherals)
    return result


def _collect_registers(
    registers: Sequence[SvdRegisterItem],
) -> list[SVDRegister]:
    """Recursively collect all registers, flattening clusters and arrays."""
    from cmsis_svd.model import SVDRegister, SVDRegisterArray, SVDRegisterCluster

    result: list[SVDRegister] = []
    for item in registers:
        if isinstance(item, SVDRegister):
            result.append(item)
        elif isinstance(item, SVDRegisterArray):
            result.extend(item.registers)
        elif isinstance(item, SVDRegisterCluster) and item.registers:
            result.extend(_collect_registers(item.registers))
    return result


def _get_cpu_name(device: SVDDevice) -> str:
    """Extract CPU name string from device."""
    if not device.cpu or not device.cpu.name:
        return ""
    cpu_name_val = device.cpu.name
    return cpu_name_val.name if hasattr(cpu_name_val, "name") else str(cpu_name_val)


def _format_access(access: SVDAccessType | None) -> str:
    """Format SVD access type to a short abbreviation."""
    from cmsis_svd.model import SVDAccessType

    if access is None:
        return "—"

    access_map: dict[SVDAccessType, str] = {
        SVDAccessType.READ_ONLY: "RO",
        SVDAccessType.WRITE_ONLY: "WO",
        SVDAccessType.READ_WRITE: "RW",
        SVDAccessType.WRITE_ONCE: "W1",
        SVDAccessType.READ_WRITE_ONCE: "RW1",
    }

    if isinstance(access, SVDAccessType):
        return access_map.get(access, str(access))
    return str(access)


def _format_hex(value: int | None, width: int = 8) -> str:
    """Format an integer as a hex string with the given nibble width."""
    if value is None:
        return "—"
    return f"0x{value:0{width}X}"


def _compute_field_reset(register_reset: int, bit_offset: int, bit_width: int) -> str:
    """Compute and format a field's reset value from the register reset value.

    Extracts the field's bits from the register-level reset value using:
        field_reset = (register_reset >> bit_offset) & ((1 << bit_width) - 1)

    See TECH_SPEC.md §5.5.
    """
    if bit_width <= 0:
        logger.debug("Field with bit_width=%d, returning 0x0", bit_width)
        return "0x0"
    if bit_offset < 0 or bit_offset >= 64:
        logger.debug("Field with out-of-range bit_offset=%d", bit_offset)
        return "0x0"
    mask = (1 << bit_width) - 1
    value = (register_reset >> bit_offset) & mask
    hex_width = max(1, (bit_width + 3) // 4)
    return f"0x{value:0{hex_width}X}"


def _format_bit_range(offset: int, width: int) -> str:
    """Format bit offset and width as a [MSB:LSB] range string."""
    msb = offset + width - 1
    if width == 1:
        return f"[{msb}]"
    return f"[{msb}:{offset}]"

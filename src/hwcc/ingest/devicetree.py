"""Device tree source parser — thin wrapper with metadata extraction.

Reads .dts/.dtsi files as text and extracts compatible strings for
metadata. The DTS content is kept as-is since it's human-readable
and AI tools parse it natively.

This parser is 100% deterministic — no LLM dependency.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from hwcc.exceptions import ParseError
from hwcc.ingest.base import BaseParser
from hwcc.types import ParseResult

if TYPE_CHECKING:
    from pathlib import Path

    from hwcc.config import HwccConfig

__all__ = ["DeviceTreeParser"]

logger = logging.getLogger(__name__)

MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB

# Match entire compatible = "...", "...", ...; statement (may span multiple lines)
_COMPATIBLE_STMT_RE = re.compile(r'compatible\s*=\s*([^;]+);', re.DOTALL)
# Extract individual quoted strings from a compatible statement
_QUOTED_STR_RE = re.compile(r'"([^"]+)"')

# Match model = "Board Name";
_MODEL_RE = re.compile(r'model\s*=\s*"([^"]+)"')

# Common vendor prefixes → chip family hints
_VENDOR_CHIP_MAP: dict[str, str] = {
    "fsl,imx8mp": "i.MX8MP",
    "fsl,imx8mm": "i.MX8MM",
    "fsl,imx8mn": "i.MX8MN",
    "fsl,imx8mq": "i.MX8MQ",
    "fsl,imx6q": "i.MX6Q",
    "fsl,imx6dl": "i.MX6DL",
    "fsl,imx6ul": "i.MX6UL",
    "fsl,imx93": "i.MX93",
    "ti,am625": "AM625",
    "ti,am62p": "AM62P",
    "ti,am6548": "AM6548",
    "rockchip,rk3588": "RK3588",
    "rockchip,rk3568": "RK3568",
    "rockchip,rk3399": "RK3399",
    "allwinner,sun50i-h616": "H616",
    "allwinner,sun50i-h6": "H6",
    "st,stm32mp157": "STM32MP157",
    "st,stm32mp135": "STM32MP135",
    "st,stm32mp251": "STM32MP251",
    "renesas,r8a774a1": "RZ/G2M",
    "renesas,r8a779g0": "R-Car V4H",
    "qcom,sm8550": "SM8550",
    "amlogic,g12a": "S905X2",
    "nvidia,tegra234": "Tegra234",
    "mediatek,mt8195": "MT8195",
    "brcm,bcm2711": "BCM2711",
    "brcm,bcm2712": "BCM2712",
    "xlnx,zynqmp": "ZynqMP",
}


class DeviceTreeParser(BaseParser):
    """Parser for device tree source files (.dts/.dtsi).

    Reads the file as text and extracts compatible strings for metadata.
    The DTS content is preserved as-is — AI tools read DTS syntax natively.
    """

    def parse(self, path: Path, config: HwccConfig) -> ParseResult:
        """Parse a device tree source file into a ParseResult.

        Args:
            path: Path to the .dts or .dtsi file.
            config: Project configuration.

        Returns:
            ParseResult with DTS content and extracted metadata.

        Raises:
            ParseError: If the file cannot be read.
        """
        if not path.exists():
            msg = f"Device tree file not found: {path}"
            raise ParseError(msg)

        if not path.is_file():
            msg = f"Not a file: {path}"
            raise ParseError(msg)

        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            msg = (
                f"Device tree file {path.name} ({file_size} bytes) "
                f"exceeds maximum size ({MAX_FILE_SIZE} bytes)"
            )
            raise ParseError(msg)

        logger.info("Parsing device tree: %s", path)

        try:
            content = path.read_text(encoding="utf-8")
            # Strip BOM if present
            if content.startswith("\ufeff"):
                content = content[1:]
        except UnicodeDecodeError:
            logger.warning("UTF-8 decode failed for %s, retrying with replacement", path.name)
            content = path.read_bytes().decode("utf-8", errors="replace")
        except OSError as e:
            msg = f"Cannot read device tree file {path.name}: {e}"
            raise ParseError(msg) from e

        # Extract metadata from content
        compatibles = _extract_compatibles(content)
        chip = _detect_chip(compatibles)
        title = _extract_title(content, path)

        metadata_pairs: list[tuple[str, str]] = []
        if compatibles:
            metadata_pairs.append(("compatibles", ", ".join(compatibles)))

        logger.info("Parsed %s: %d chars, %d compatible strings, chip=%s",
                     path.name, len(content), len(compatibles), chip or "(none)")

        return ParseResult(
            doc_id=_make_doc_id(path),
            content=content.strip(),
            doc_type="device_tree",
            title=title,
            source_path=str(path),
            chip=chip,
            metadata=tuple(metadata_pairs),
        )

    def supported_extensions(self) -> frozenset[str]:
        """Return supported file extensions."""
        return frozenset({".dts", ".dtsi"})


def _extract_compatibles(content: str) -> list[str]:
    """Extract all compatible string values from DTS content."""
    result: list[str] = []
    for stmt_match in _COMPATIBLE_STMT_RE.finditer(content):
        for quoted in _QUOTED_STR_RE.findall(stmt_match.group(1)):
            if quoted not in result:
                result.append(quoted)
    return result


def _make_doc_id(path: Path) -> str:
    """Generate a document ID from the file path."""
    return "dt_" + path.stem.lower().replace("-", "_").replace(" ", "_")


def _extract_title(content: str, path: Path) -> str:
    """Extract title from model property or filename."""
    match = _MODEL_RE.search(content)
    if match:
        return match.group(1)
    return path.stem


def _detect_chip(compatibles: list[str]) -> str:
    """Detect chip/SoC from compatible strings."""
    for compat in compatibles:
        if compat in _VENDOR_CHIP_MAP:
            return _VENDOR_CHIP_MAP[compat]
        # Try prefix match (e.g., "fsl,imx8mp-evk" matches "fsl,imx8mp")
        # Require delimiter after prefix to avoid false matches
        for prefix, chip in _VENDOR_CHIP_MAP.items():
            if compat.startswith(prefix + "-") or compat.startswith(prefix + "_"):
                return chip
    return ""

"""Tests for hwcc.ingest.devicetree — DeviceTreeParser."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hwcc.config import HwccConfig
from hwcc.exceptions import ParseError
from hwcc.ingest.devicetree import DeviceTreeParser, _detect_chip
from hwcc.types import ParseResult

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def parser() -> DeviceTreeParser:
    return DeviceTreeParser()


@pytest.fixture
def config() -> HwccConfig:
    return HwccConfig()


@pytest.fixture
def sample_dts(tmp_path: Path) -> Path:
    """Create a sample i.MX8MP board DTS file."""
    dts = tmp_path / "imx8mp-custom.dts"
    dts.write_text(
        """\
/dts-v1/;

#include "imx8mp.dtsi"

/ {
\tmodel = "Custom i.MX8MP Board";
\tcompatible = "custom,board", "fsl,imx8mp";

\tchosen {
\t\tstdout-path = &uart1;
\t};
};

&ecspi1 {
\tstatus = "okay";
\tpinctrl-names = "default";
\tpinctrl-0 = <&pinctrl_ecspi1>;
\tcs-gpios = <&gpio5 9 GPIO_ACTIVE_LOW>;

\tspidev@0 {
\t\tcompatible = "rohm,dh2228fv";
\t\treg = <0>;
\t\tspi-max-frequency = <10000000>;
\t};
};

&i2c1 {
\tstatus = "okay";

\tpmic@25 {
\t\tcompatible = "nxp,pca9450c";
\t\treg = <0x25>;
\t\tinterrupt-parent = <&gpio1>;
\t\tinterrupts = <3 IRQ_TYPE_LEVEL_LOW>;
\t};
};
""",
        encoding="utf-8",
    )
    return dts


@pytest.fixture
def sample_dtsi(tmp_path: Path) -> Path:
    """Create a minimal .dtsi include file."""
    dtsi = tmp_path / "imx8mp.dtsi"
    dtsi.write_text(
        """\
/ {
\tcompatible = "fsl,imx8mp";
\t#address-cells = <2>;
\t#size-cells = <2>;

\tsoc@0 {
\t\tcompatible = "simple-bus";
\t\t#address-cells = <1>;
\t\t#size-cells = <1>;
\t};
};
""",
        encoding="utf-8",
    )
    return dtsi


@pytest.fixture
def result(parser: DeviceTreeParser, config: HwccConfig, sample_dts: Path) -> ParseResult:
    """Parse the sample DTS once, shared across tests."""
    return parser.parse(sample_dts, config)


# ── ParseResult fields ─────────────────────────────────────────────


class TestParseResultFields:
    def test_returns_parse_result(self, result: ParseResult) -> None:
        assert isinstance(result, ParseResult)

    def test_doc_type_is_device_tree(self, result: ParseResult) -> None:
        assert result.doc_type == "device_tree"

    def test_doc_id_has_dt_prefix(self, result: ParseResult) -> None:
        assert result.doc_id == "dt_imx8mp_custom"

    def test_source_path_matches_input(self, result: ParseResult, sample_dts: Path) -> None:
        assert result.source_path == str(sample_dts)

    def test_content_is_non_empty(self, result: ParseResult) -> None:
        assert len(result.content) > 0

    def test_title_from_model_property(self, result: ParseResult) -> None:
        assert result.title == "Custom i.MX8MP Board"

    def test_chip_detected_from_compatible(self, result: ParseResult) -> None:
        assert result.chip == "i.MX8MP"

    def test_metadata_contains_compatibles(self, result: ParseResult) -> None:
        meta_dict = dict(result.metadata)
        assert "compatibles" in meta_dict
        assert "fsl,imx8mp" in meta_dict["compatibles"]
        assert "rohm,dh2228fv" in meta_dict["compatibles"]


# ── Content preservation ───────────────────────────────────────────


class TestContentPreservation:
    def test_preserves_dts_syntax(self, result: ParseResult) -> None:
        assert "/dts-v1/;" in result.content

    def test_preserves_node_references(self, result: ParseResult) -> None:
        assert "&ecspi1" in result.content
        assert "&i2c1" in result.content

    def test_preserves_includes(self, result: ParseResult) -> None:
        assert '#include "imx8mp.dtsi"' in result.content

    def test_preserves_properties(self, result: ParseResult) -> None:
        assert "spi-max-frequency" in result.content
        assert "pinctrl-names" in result.content


# ── DTSI support ───────────────────────────────────────────────────


class TestDtsiSupport:
    def test_parses_dtsi_file(
        self, parser: DeviceTreeParser, config: HwccConfig, sample_dtsi: Path
    ) -> None:
        result = parser.parse(sample_dtsi, config)
        assert result.doc_type == "device_tree"
        assert result.chip == "i.MX8MP"

    def test_dtsi_doc_id(
        self, parser: DeviceTreeParser, config: HwccConfig, sample_dtsi: Path
    ) -> None:
        result = parser.parse(sample_dtsi, config)
        assert result.doc_id == "dt_imx8mp"


# ── Supported extensions ──────────────────────────────────────────


class TestSupportedExtensions:
    def test_supports_dts(self, parser: DeviceTreeParser) -> None:
        assert ".dts" in parser.supported_extensions()

    def test_supports_dtsi(self, parser: DeviceTreeParser) -> None:
        assert ".dtsi" in parser.supported_extensions()

    def test_can_parse_dts(self, parser: DeviceTreeParser, sample_dts: Path) -> None:
        assert parser.can_parse(sample_dts)

    def test_can_parse_dtsi(self, parser: DeviceTreeParser, sample_dtsi: Path) -> None:
        assert parser.can_parse(sample_dtsi)


# ── Chip detection ─────────────────────────────────────────────────


class TestChipDetection:
    def test_imx8mp(self) -> None:
        assert _detect_chip(["fsl,imx8mp"]) == "i.MX8MP"

    def test_imx8mp_board_variant(self) -> None:
        assert _detect_chip(["custom,board", "fsl,imx8mp-evk"]) == "i.MX8MP"

    def test_rk3588(self) -> None:
        assert _detect_chip(["rockchip,rk3588"]) == "RK3588"

    def test_stm32mp157(self) -> None:
        assert _detect_chip(["st,stm32mp157"]) == "STM32MP157"

    def test_bcm2711(self) -> None:
        assert _detect_chip(["brcm,bcm2711"]) == "BCM2711"

    def test_ti_am625(self) -> None:
        assert _detect_chip(["ti,am625"]) == "AM625"

    def test_unknown_compatible(self) -> None:
        assert _detect_chip(["unknown,device"]) == ""

    def test_empty_list(self) -> None:
        assert _detect_chip([]) == ""


# ── Title extraction ───────────────────────────────────────────────


class TestTitleExtraction:
    def test_title_fallback_to_filename(
        self, parser: DeviceTreeParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        """When no model property, title should be the filename stem."""
        dts = tmp_path / "minimal.dts"
        dts.write_text("/dts-v1/;\n/ { };\n", encoding="utf-8")
        result = parser.parse(dts, config)
        assert result.title == "minimal"


# ── Error handling ─────────────────────────────────────────────────


class TestErrorHandling:
    def test_nonexistent_file_raises(
        self, parser: DeviceTreeParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        with pytest.raises(ParseError, match="not found"):
            parser.parse(tmp_path / "does_not_exist.dts", config)

    def test_directory_raises(
        self, parser: DeviceTreeParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        with pytest.raises(ParseError, match="Not a file"):
            parser.parse(tmp_path, config)

    def test_oversized_file_raises(
        self, parser: DeviceTreeParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        huge = tmp_path / "huge.dts"
        huge.write_bytes(b"x" * (11 * 1024 * 1024))
        with pytest.raises(ParseError, match="exceeds maximum size"):
            parser.parse(huge, config)


# ── Empty/minimal files ───────────────────────────────────────────


class TestEdgeCases:
    def test_empty_dts(
        self, parser: DeviceTreeParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        dts = tmp_path / "empty.dts"
        dts.write_text("", encoding="utf-8")
        result = parser.parse(dts, config)
        assert result.doc_type == "device_tree"
        assert result.content == ""
        assert result.chip == ""

    def test_minimal_dts(
        self, parser: DeviceTreeParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        dts = tmp_path / "minimal.dts"
        dts.write_text("/dts-v1/;\n/ { };\n", encoding="utf-8")
        result = parser.parse(dts, config)
        assert result.doc_type == "device_tree"
        assert result.chip == ""
        assert result.metadata == ()

    def test_no_compatible_no_metadata(
        self, parser: DeviceTreeParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        dts = tmp_path / "no_compat.dts"
        dts.write_text("/dts-v1/;\n/ {\n\t#address-cells = <2>;\n};\n", encoding="utf-8")
        result = parser.parse(dts, config)
        assert result.metadata == ()
        assert result.chip == ""

    def test_multiline_compatible(
        self, parser: DeviceTreeParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        """Compatible strings spanning multiple lines should be extracted."""
        dts = tmp_path / "multiline.dts"
        dts.write_text(
            '/dts-v1/;\n/ {\n\tcompatible = "custom,board",\n'
            '\t\t     "fsl,imx8mp";\n};\n',
            encoding="utf-8",
        )
        result = parser.parse(dts, config)
        meta_dict = dict(result.metadata)
        assert "fsl,imx8mp" in meta_dict["compatibles"]
        assert result.chip == "i.MX8MP"

    def test_bom_stripped(
        self, parser: DeviceTreeParser, config: HwccConfig, tmp_path: Path
    ) -> None:
        """UTF-8 BOM should be stripped from content."""
        dts = tmp_path / "bom.dts"
        dts.write_bytes(b"\xef\xbb\xbf/dts-v1/;\n/ { };\n")
        result = parser.parse(dts, config)
        assert result.content.startswith("/dts-v1/")

    def test_prefix_match_requires_delimiter(self) -> None:
        """Prefix match should not match without a delimiter."""
        # "fsl,imx8mplus" should NOT match "fsl,imx8mp" prefix
        assert _detect_chip(["fsl,imx8mplus"]) == ""
        # "fsl,imx8mp-evk" SHOULD match "fsl,imx8mp" prefix
        assert _detect_chip(["fsl,imx8mp-evk"]) == "i.MX8MP"

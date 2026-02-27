"""Tests for hwcc.ingest.svd — CMSIS-SVD parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from hwcc.config import HwccConfig
from hwcc.exceptions import ParseError
from hwcc.ingest.svd import SvdParser, _format_access, _format_bit_range, _format_hex
from hwcc.types import ParseResult

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_SVD = FIXTURE_DIR / "sample.svd"


@pytest.fixture
def parser() -> SvdParser:
    return SvdParser()


@pytest.fixture
def config() -> HwccConfig:
    return HwccConfig()


@pytest.fixture
def result(parser: SvdParser, config: HwccConfig) -> ParseResult:
    return parser.parse(SAMPLE_SVD, config)


# --- ParseResult fields ---


class TestParseResultFields:
    def test_parse_returns_parse_result(self, result):
        assert isinstance(result, ParseResult)

    def test_doc_type_is_svd(self, result):
        assert result.doc_type == "svd"

    def test_chip_extracted_from_device_name(self, result):
        assert result.chip == "TESTCHIP"

    def test_title_contains_device_name(self, result):
        assert result.title == "TESTCHIP Register Map"

    def test_source_path_set(self, result):
        assert result.source_path == str(SAMPLE_SVD)

    def test_doc_id_derived_from_filename(self, result):
        assert result.doc_id == "sample_svd"

    def test_content_is_nonempty_string(self, result):
        assert isinstance(result.content, str)
        assert len(result.content) > 0


class TestMetadata:
    def test_metadata_contains_peripheral_count(self, result):
        meta = dict(result.metadata)
        assert meta["peripheral_count"] == "3"

    def test_metadata_contains_register_count(self, result):
        meta = dict(result.metadata)
        # TIMER0: 3 regs, TIMER1: 3 regs (derived), GPIO: 0 regs = 6 total
        assert meta["register_count"] == "6"

    def test_metadata_contains_cpu(self, result):
        meta = dict(result.metadata)
        assert meta["cpu"] == "CM4"


# --- Peripheral extraction ---


class TestPeripheralExtraction:
    def test_all_peripherals_present(self, result):
        content = result.content
        assert "## GPIO" in content
        assert "## TIMER0" in content
        assert "## TIMER1" in content

    def test_peripheral_count(self, result):
        # Count ## headings (peripheral sections)
        count = result.content.count("\n## ")
        assert count == 3

    def test_base_address_formatted_as_hex(self, result):
        assert "`0x40000000`" in result.content
        assert "`0x40001000`" in result.content
        assert "`0x50000000`" in result.content

    def test_peripheral_description_present(self, result):
        assert "General-purpose timer" in result.content
        assert "General-purpose I/O" in result.content


# --- Derived peripheral ---


class TestDerivedPeripheral:
    def test_derived_peripheral_has_registers(self, result):
        content = result.content
        # TIMER1 is derived from TIMER0 — should have the same registers
        # Find the TIMER1 section and verify it has register table
        timer1_start = content.index("## TIMER1")
        # Find the next peripheral section or end
        next_section = content.find("\n---\n", timer1_start + 1)
        if next_section == -1:
            timer1_section = content[timer1_start:]
        else:
            timer1_section = content[timer1_start:next_section]
        assert "### Registers" in timer1_section
        assert "| CR |" in timer1_section
        assert "| SR |" in timer1_section
        assert "| CNT |" in timer1_section

    def test_derived_peripheral_different_base_address(self, result):
        content = result.content
        timer1_start = content.index("## TIMER1")
        timer1_section = content[timer1_start : timer1_start + 500]
        assert "`0x40001000`" in timer1_section


# --- Register table format ---


class TestRegisterTable:
    def test_register_table_headers(self, result):
        assert "| Register | Offset | Size | Access | Reset | Description |" in result.content

    def test_register_offset_formatted(self, result):
        # CR at offset 0x00
        assert "| CR | 0x0000 |" in result.content

    def test_register_access_formatted(self, result):
        # CR is read-write → RW, SR is read-only → RO
        assert "| RW |" in result.content
        assert "| RO |" in result.content

    def test_register_reset_value_formatted(self, result):
        # SR reset = 0x00000001
        assert "0x00000001" in result.content

    def test_register_with_no_fields_has_no_field_table(self, result):
        # CNT has no fields — should not produce a "CNT Fields" section
        assert "### CNT Fields" not in result.content


# --- Field detail tables ---


class TestFieldTable:
    def test_field_table_headers(self, result):
        assert "| Field | Bits | Access | Reset | Description |" in result.content

    def test_field_bit_range_single_bit(self, result):
        # EN is bit 0, width 1 → [0]
        assert "| EN | [0] |" in result.content

    def test_field_bit_range_multi_bit(self, result):
        # MODE is offset 1, width 2 → [2:1]
        assert "| MODE | [2:1] |" in result.content

    def test_field_description_present(self, result):
        assert "Timer enable" in result.content
        assert "Timer mode" in result.content

    def test_fields_sorted_by_bit_position_descending(self, result):
        content = result.content
        # Find CR Fields section
        cr_start = content.index("### CR Fields")
        rest = content[cr_start + 1 :]
        cr_end = content.index("\n### ", cr_start + 1) if "### " in rest else len(content)
        cr_section = content[cr_start:cr_end]
        # IRQ_EN [3] should come before MODE [2:1] which comes before EN [0]
        irq_pos = cr_section.index("IRQ_EN")
        mode_pos = cr_section.index("MODE")
        en_pos = cr_section.index("| EN |")
        assert irq_pos < mode_pos < en_pos


# --- Edge cases ---


class TestEdgeCases:
    def test_peripheral_with_no_registers(self, result):
        content = result.content
        gpio_start = content.index("## GPIO")
        next_section = content.find("\n---\n", gpio_start + 1)
        if next_section == -1:
            gpio_section = content[gpio_start:]
        else:
            gpio_section = content[gpio_start:next_section]
        assert "*No registers defined.*" in gpio_section

    def test_peripherals_sorted_alphabetically(self, result):
        content = result.content
        gpio_pos = content.index("## GPIO")
        timer0_pos = content.index("## TIMER0")
        timer1_pos = content.index("## TIMER1")
        assert gpio_pos < timer0_pos < timer1_pos


# --- Sorting ---


class TestSorting:
    def test_registers_sorted_by_offset(self, result):
        content = result.content
        # Find TIMER0's register table
        timer0_start = content.index("## TIMER0")
        timer0_end = content.index("\n---\n", timer0_start + 1)
        timer0_section = content[timer0_start:timer0_end]
        # CR (0x00) before SR (0x04) before CNT (0x08)
        cr_pos = timer0_section.index("| CR |")
        sr_pos = timer0_section.index("| SR |")
        cnt_pos = timer0_section.index("| CNT |")
        assert cr_pos < sr_pos < cnt_pos


# --- Error handling ---


class TestErrorHandling:
    def test_nonexistent_file_raises_parse_error(self, parser, config):
        with pytest.raises(ParseError, match="SVD file not found"):
            parser.parse(Path("/nonexistent/file.svd"), config)

    def test_invalid_svd_raises_parse_error(self, parser, config, tmp_path):
        bad_svd = tmp_path / "bad.svd"
        bad_svd.write_text("this is not valid XML", encoding="utf-8")
        with pytest.raises(ParseError, match="Failed to parse SVD"):
            parser.parse(bad_svd, config)

    def test_xxe_doctype_rejected(self, parser, config, tmp_path):
        xxe_svd = tmp_path / "xxe.svd"
        xxe_svd.write_text(
            '<?xml version="1.0"?>\n'
            "<!DOCTYPE foo [\n"
            '  <!ENTITY xxe SYSTEM "file:///etc/passwd">\n'
            "]>\n"
            "<device><name>&xxe;</name></device>",
            encoding="utf-8",
        )
        with pytest.raises(ParseError, match="unsafe XML"):
            parser.parse(xxe_svd, config)

    def test_xxe_entity_rejected(self, parser, config, tmp_path):
        entity_svd = tmp_path / "entity.svd"
        entity_svd.write_text(
            "<?xml version=\"1.0\"?>\n<!ENTITY test 'value'>\n<device><name>test</name></device>",
            encoding="utf-8",
        )
        with pytest.raises(ParseError, match="unsafe XML"):
            parser.parse(entity_svd, config)


# --- supported_extensions and can_parse ---


class TestExtensions:
    def test_supported_extensions(self, parser):
        assert parser.supported_extensions() == frozenset({".svd"})

    def test_can_parse_svd(self, parser):
        assert parser.can_parse(Path("board.svd")) is True

    def test_can_parse_rejects_pdf(self, parser):
        assert parser.can_parse(Path("doc.pdf")) is False

    def test_can_parse_case_insensitive(self, parser):
        assert parser.can_parse(Path("BOARD.SVD")) is True


# --- Formatting helpers ---


class TestFormatAccess:
    def test_read_only(self):
        from cmsis_svd.model import SVDAccessType

        assert _format_access(SVDAccessType.READ_ONLY) == "RO"

    def test_write_only(self):
        from cmsis_svd.model import SVDAccessType

        assert _format_access(SVDAccessType.WRITE_ONLY) == "WO"

    def test_read_write(self):
        from cmsis_svd.model import SVDAccessType

        assert _format_access(SVDAccessType.READ_WRITE) == "RW"

    def test_write_once(self):
        from cmsis_svd.model import SVDAccessType

        assert _format_access(SVDAccessType.WRITE_ONCE) == "W1"

    def test_read_write_once(self):
        from cmsis_svd.model import SVDAccessType

        assert _format_access(SVDAccessType.READ_WRITE_ONCE) == "RW1"

    def test_none_returns_dash(self):
        assert _format_access(None) == "—"


class TestFormatHex:
    def test_zero(self):
        assert _format_hex(0, 8) == "0x00000000"

    def test_small_value(self):
        assert _format_hex(4, 4) == "0x0004"

    def test_large_value(self):
        assert _format_hex(0x40013000, 8) == "0x40013000"

    def test_none_returns_dash(self):
        assert _format_hex(None, 8) == "—"


class TestFormatBitRange:
    def test_single_bit(self):
        assert _format_bit_range(0, 1) == "[0]"

    def test_multi_bit(self):
        assert _format_bit_range(1, 2) == "[2:1]"

    def test_wide_field(self):
        assert _format_bit_range(0, 8) == "[7:0]"

    def test_high_bit(self):
        assert _format_bit_range(16, 1) == "[16]"

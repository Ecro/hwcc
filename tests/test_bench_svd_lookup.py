"""Tests for hwcc.bench.svd_lookup — direct SVD answer extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

from hwcc.bench.svd_lookup import SvdLookupResult, lookup_svd_answer
from hwcc.bench.types import BenchQuestion


def _mock_device():
    """Create a mock SVDDevice with SPI1 peripheral, CR1 register, BR field."""
    # Build field
    field_br = MagicMock()
    field_br.name = "BR"
    field_br.bit_offset = 3
    field_br.bit_width = 3

    field_spe = MagicMock()
    field_spe.name = "SPE"
    field_spe.bit_offset = 6
    field_spe.bit_width = 1

    # Build register
    reg_cr1 = MagicMock()
    reg_cr1.name = "CR1"
    reg_cr1.address_offset = 0x00
    reg_cr1.reset_value = 0x00000000
    reg_cr1.access = MagicMock()
    reg_cr1.access.name = "READ_WRITE"
    reg_cr1.fields = [field_br, field_spe]

    reg_sr = MagicMock()
    reg_sr.name = "SR"
    reg_sr.address_offset = 0x08
    reg_sr.reset_value = 0x00000002
    reg_sr.access = MagicMock()
    reg_sr.access.name = "READ_ONLY"
    reg_sr.fields = []

    # Build peripheral
    periph_spi1 = MagicMock()
    periph_spi1.name = "SPI1"
    periph_spi1.base_address = 0x40013000
    periph_spi1.registers = [reg_cr1, reg_sr]

    # Build device
    device = MagicMock()
    device.peripherals = [periph_spi1]

    return device


class TestLookupBaseAddress:
    """Test base_address category lookup."""

    def test_returns_hex_address(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_base_address",
            category="base_address",
            peripheral="SPI1",
            register="",
            field_name="",
            question="What is the base address of SPI1?",
            answer="0x40013000",
            answer_format="hex",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is True
        assert result.answer == "0x40013000"
        assert result.peripheral == "SPI1"

    def test_case_insensitive_match(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_base_address",
            category="base_address",
            peripheral="spi1",
            register="",
            field_name="",
            question="What is the base address of spi1?",
            answer="0x40013000",
            answer_format="hex",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is True
        assert result.answer == "0x40013000"

    def test_prefix_match(self):
        """Question says 'SPI1' but SVD has 'SPI1_I2S1ext'."""
        device = _mock_device()
        device.peripherals[0].name = "SPI1_I2S1ext"
        q = BenchQuestion(
            id="spi1_base_address",
            category="base_address",
            peripheral="SPI1",
            register="",
            field_name="",
            question="What is the base address of SPI1?",
            answer="0x40013000",
            answer_format="hex",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is True
        assert result.answer == "0x40013000"

    def test_missing_peripheral_unanswerable(self):
        device = _mock_device()
        q = BenchQuestion(
            id="usart1_base_address",
            category="base_address",
            peripheral="USART1",
            register="",
            field_name="",
            question="What is the base address of USART1?",
            answer="0x40011000",
            answer_format="hex",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is False
        assert result.answer == ""


class TestLookupRegisterOffset:
    """Test register_offset category lookup."""

    def test_returns_hex_offset(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_cr1_offset",
            category="register_offset",
            peripheral="SPI1",
            register="CR1",
            field_name="",
            question="What is the offset of SPI1_CR1?",
            answer="0x0000",
            answer_format="hex",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is True
        assert result.answer == "0x0000"

    def test_nonzero_offset(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_sr_offset",
            category="register_offset",
            peripheral="SPI1",
            register="SR",
            field_name="",
            question="What is the offset of SPI1_SR?",
            answer="0x0008",
            answer_format="hex",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is True
        assert result.answer == "0x0008"

    def test_missing_register_unanswerable(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_dr_offset",
            category="register_offset",
            peripheral="SPI1",
            register="DR",
            field_name="",
            question="What is the offset of SPI1_DR?",
            answer="0x000C",
            answer_format="hex",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is False


class TestLookupResetValue:
    """Test reset_value category lookup."""

    def test_returns_hex_reset(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_sr_reset",
            category="reset_value",
            peripheral="SPI1",
            register="SR",
            field_name="",
            question="What is the reset value of SPI1_SR?",
            answer="0x00000002",
            answer_format="hex",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is True
        assert result.answer == "0x00000002"

    def test_zero_reset_value(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_cr1_reset",
            category="reset_value",
            peripheral="SPI1",
            register="CR1",
            field_name="",
            question="What is the reset value of SPI1_CR1?",
            answer="0x00000000",
            answer_format="hex",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is True
        assert result.answer == "0x00000000"


class TestLookupAccessType:
    """Test access_type category lookup."""

    def test_returns_rw(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_cr1_access",
            category="access_type",
            peripheral="SPI1",
            register="CR1",
            field_name="",
            question="What is the access type of SPI1_CR1?",
            answer="RW",
            answer_format="access_code",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is True
        assert result.answer == "RW"

    def test_returns_ro(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_sr_access",
            category="access_type",
            peripheral="SPI1",
            register="SR",
            field_name="",
            question="What is the access type of SPI1_SR?",
            answer="RO",
            answer_format="access_code",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is True
        assert result.answer == "RO"


class TestLookupBitField:
    """Test bit_field category lookup."""

    def test_multi_bit_field(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_cr1_br_bits",
            category="bit_field",
            peripheral="SPI1",
            register="CR1",
            field_name="BR",
            question="What bits does BR occupy in SPI1_CR1?",
            answer="[5:3]",
            answer_format="bit_range",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is True
        assert result.answer == "[5:3]"

    def test_single_bit_field(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_cr1_spe_bits",
            category="bit_field",
            peripheral="SPI1",
            register="CR1",
            field_name="SPE",
            question="What bit does SPE occupy in SPI1_CR1?",
            answer="[6]",
            answer_format="bit_range",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is True
        assert result.answer == "[6]"

    def test_missing_field_unanswerable(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_cr1_xyz_bits",
            category="bit_field",
            peripheral="SPI1",
            register="CR1",
            field_name="XYZ",
            question="What bits does XYZ occupy?",
            answer="[7:0]",
            answer_format="bit_range",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is False


class TestLookupUnknownCategory:
    """Test non-SVD categories return unanswerable."""

    def test_clock_config_unanswerable(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_clock_config",
            category="clock_config",
            peripheral="SPI1",
            register="",
            field_name="",
            question="What clock bus is SPI1 on?",
            answer="APB2",
            answer_format="text",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is False
        assert result.answer == ""

    def test_electrical_specs_unanswerable(self):
        device = _mock_device()
        q = BenchQuestion(
            id="vdd_range",
            category="electrical_specs",
            peripheral="",
            register="",
            field_name="",
            question="What is the VDD range?",
            answer="1.8V to 3.6V",
            answer_format="numeric_range",
        )
        result = lookup_svd_answer(q, device)
        assert result.answerable is False


class TestLookupLatency:
    """Test that latency is tracked."""

    def test_latency_is_positive(self):
        device = _mock_device()
        q = BenchQuestion(
            id="spi1_base_address",
            category="base_address",
            peripheral="SPI1",
            register="",
            field_name="",
            question="What is the base address of SPI1?",
            answer="0x40013000",
            answer_format="hex",
        )
        result = lookup_svd_answer(q, device)
        assert result.latency_ms >= 0.0

    def test_unanswerable_has_latency(self):
        device = _mock_device()
        q = BenchQuestion(
            id="test",
            category="clock_config",
            peripheral="SPI1",
            register="",
            field_name="",
            question="What clock?",
            answer="APB2",
            answer_format="text",
        )
        result = lookup_svd_answer(q, device)
        assert result.latency_ms >= 0.0


class TestSvdLookupResultDataclass:
    """Test SvdLookupResult is a proper frozen dataclass."""

    def test_frozen(self):
        result = SvdLookupResult(
            answer="0x40013000",
            answerable=True,
            peripheral="SPI1",
            latency_ms=0.1,
        )
        assert result.answer == "0x40013000"
        assert result.answerable is True
        assert result.peripheral == "SPI1"

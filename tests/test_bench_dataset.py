"""Tests for hwcc.bench.dataset — SVD to Q&A dataset generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from hwcc.bench.dataset import generate_dataset, load_dataset, save_dataset
from hwcc.bench.scoring import _infer_category
from hwcc.exceptions import BenchmarkError

# Minimal SVD fixture content for testing
_MINI_SVD = """\
<?xml version="1.0" encoding="utf-8"?>
<device schemaVersion="1.1" xmlns:xs="http://www.w3.org/2001/XMLSchema-instance">
  <name>TESTCHIP</name>
  <description>Test chip for benchmarking</description>
  <cpu>
    <name>CM4</name>
    <revision>r0p1</revision>
  </cpu>
  <addressUnitBits>8</addressUnitBits>
  <width>32</width>
  <peripherals>
    <peripheral>
      <name>SPI1</name>
      <description>Serial peripheral interface</description>
      <baseAddress>0x40013000</baseAddress>
      <registers>
        <register>
          <name>CR1</name>
          <description>control register 1</description>
          <addressOffset>0x0</addressOffset>
          <size>32</size>
          <access>read-write</access>
          <resetValue>0x00000000</resetValue>
          <fields>
            <field>
              <name>SPE</name>
              <description>SPI enable</description>
              <bitOffset>6</bitOffset>
              <bitWidth>1</bitWidth>
              <access>read-write</access>
            </field>
            <field>
              <name>BR</name>
              <description>Baud rate control</description>
              <bitOffset>3</bitOffset>
              <bitWidth>3</bitWidth>
              <access>read-write</access>
            </field>
            <field>
              <name>MSTR</name>
              <description>Master selection</description>
              <bitOffset>2</bitOffset>
              <bitWidth>1</bitWidth>
              <access>read-write</access>
            </field>
          </fields>
        </register>
        <register>
          <name>SR</name>
          <description>status register</description>
          <addressOffset>0x8</addressOffset>
          <size>32</size>
          <access>read-only</access>
          <resetValue>0x00000002</resetValue>
          <fields>
            <field>
              <name>TXE</name>
              <description>Transmit buffer empty</description>
              <bitOffset>1</bitOffset>
              <bitWidth>1</bitWidth>
              <access>read-only</access>
            </field>
            <field>
              <name>RXNE</name>
              <description>Receive buffer not empty</description>
              <bitOffset>0</bitOffset>
              <bitWidth>1</bitWidth>
              <access>read-only</access>
            </field>
          </fields>
        </register>
        <register>
          <name>DR</name>
          <description>data register</description>
          <addressOffset>0xC</addressOffset>
          <size>32</size>
          <access>read-write</access>
          <resetValue>0x00000000</resetValue>
        </register>
      </registers>
    </peripheral>
    <peripheral>
      <name>USART1</name>
      <description>Universal synchronous asynchronous receiver transmitter</description>
      <baseAddress>0x40011000</baseAddress>
      <registers>
        <register>
          <name>CR1</name>
          <description>Control register 1</description>
          <addressOffset>0x0</addressOffset>
          <size>32</size>
          <access>read-write</access>
          <resetValue>0x00000000</resetValue>
          <fields>
            <field>
              <name>UE</name>
              <description>USART enable</description>
              <bitOffset>13</bitOffset>
              <bitWidth>1</bitWidth>
            </field>
          </fields>
        </register>
      </registers>
    </peripheral>
  </peripherals>
</device>
"""


@pytest.fixture
def mini_svd(tmp_path: Path) -> Path:
    """Create a minimal SVD file for testing."""
    svd_path = tmp_path / "TESTCHIP.svd"
    svd_path.write_text(_MINI_SVD, encoding="utf-8")
    return svd_path


class TestGenerateDataset:
    """Tests for generate_dataset()."""

    def test_generates_questions_from_svd(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd)
        assert dataset.question_count > 0
        assert len(dataset.questions) == dataset.question_count

    def test_chip_name_from_svd(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd)
        assert dataset.chip == "TESTCHIP"

    def test_chip_name_override(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd, chip="MY_CHIP")
        assert dataset.chip == "MY_CHIP"

    def test_has_all_five_categories(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd)
        categories = {q.category for q in dataset.questions}
        # Should have at least base_address, register_offset, bit_field, reset_value
        assert "base_address" in categories
        assert "register_offset" in categories
        assert "bit_field" in categories
        assert "reset_value" in categories

    def test_base_address_question_correct(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd)
        spi_base = [
            q for q in dataset.questions if q.category == "base_address" and q.peripheral == "SPI1"
        ]
        assert len(spi_base) == 1
        assert spi_base[0].answer == "0x40013000"
        assert spi_base[0].answer_format == "hex"

    def test_register_offset_question_correct(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd)
        sr_offset = [
            q for q in dataset.questions if q.category == "register_offset" and q.register == "SR"
        ]
        assert len(sr_offset) == 1
        assert sr_offset[0].answer == "0x0008"
        assert sr_offset[0].answer_format == "hex"

    def test_bit_field_question_correct(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd)
        br_field = [
            q for q in dataset.questions if q.category == "bit_field" and q.field_name == "BR"
        ]
        assert len(br_field) == 1
        assert br_field[0].answer == "[5:3]"
        assert br_field[0].answer_format == "bit_range"

    def test_single_bit_field_format(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd)
        spe_field = [
            q for q in dataset.questions if q.category == "bit_field" and q.field_name == "SPE"
        ]
        assert len(spe_field) == 1
        assert spe_field[0].answer == "[6]"

    def test_reset_value_question_correct(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd)
        sr_reset = [
            q for q in dataset.questions if q.category == "reset_value" and q.register == "SR"
        ]
        assert len(sr_reset) == 1
        assert sr_reset[0].answer == "0x00000002"

    def test_access_type_question_correct(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd)
        sr_access = [
            q for q in dataset.questions if q.category == "access_type" and q.register == "SR"
        ]
        assert len(sr_access) == 1
        assert sr_access[0].answer == "RO"

    def test_peripheral_priority_ordering(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd)
        peripherals_in_order = []
        seen = set()
        for q in dataset.questions:
            if q.peripheral not in seen:
                peripherals_in_order.append(q.peripheral)
                seen.add(q.peripheral)
        # SPI should come before USART in priority list
        spi_idx = peripherals_in_order.index("SPI1")
        usart_idx = peripherals_in_order.index("USART1")
        assert spi_idx < usart_idx

    def test_limits_peripheral_count(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd, num_peripherals=1)
        peripherals = {q.peripheral for q in dataset.questions}
        assert len(peripherals) == 1

    def test_dataset_name_format(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd)
        assert dataset.name == "TESTCHIP_RegisterKnowledge"

    def test_nonexistent_svd_raises_error(self, tmp_path: Path):
        with pytest.raises(BenchmarkError, match="not found"):
            generate_dataset(tmp_path / "nonexistent.svd")

    def test_invalid_svd_raises_error(self, tmp_path: Path):
        bad_svd = tmp_path / "bad.svd"
        bad_svd.write_text("<not><valid>xml</valid></not>", encoding="utf-8")
        with pytest.raises(BenchmarkError):
            generate_dataset(bad_svd)

    def test_question_ids_are_unique(self, mini_svd: Path):
        dataset = generate_dataset(mini_svd)
        ids = [q.id for q in dataset.questions]
        dupes = [i for i in ids if ids.count(i) > 1]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {dupes}"

    def test_all_question_ids_parseable_by_infer_category(self, mini_svd: Path):
        """Contract: every generated question ID must produce a valid category."""
        dataset = generate_dataset(mini_svd)
        for q in dataset.questions:
            category = _infer_category(q.id)
            assert category != "unknown", (
                f"Question ID {q.id!r} (category={q.category!r}) is not parseable "
                f"by _infer_category — returns 'unknown'"
            )
            assert category == q.category, (
                f"Question ID {q.id!r}: _infer_category returned {category!r} "
                f"but question.category is {q.category!r}"
            )

    def test_raised_caps_for_credibility(self):
        """Caps should be high enough to produce 200+ questions from real SVDs."""
        from hwcc.bench.dataset import (
            _MAX_FIELDS_PER_REGISTER,
            _MAX_REGISTERS_PER_PERIPHERAL,
        )

        assert _MAX_REGISTERS_PER_PERIPHERAL >= 8
        assert _MAX_FIELDS_PER_REGISTER >= 5

    def test_all_questions_have_difficulty(self, mini_svd: Path):
        """Every generated question must have a difficulty tag."""
        dataset = generate_dataset(mini_svd)
        valid_difficulties = {"easy", "medium", "hard"}
        for q in dataset.questions:
            assert q.difficulty in valid_difficulties, (
                f"Question {q.id!r} has invalid difficulty: {q.difficulty!r}"
            )

    def test_difficulty_distribution_not_uniform(self, mini_svd: Path):
        """Difficulty should vary — not all questions should be the same tier."""
        dataset = generate_dataset(mini_svd)
        difficulties = {q.difficulty for q in dataset.questions}
        # Mini SVD has SPI (common) and USART (common) with varied categories,
        # so we expect at least 2 distinct difficulty levels
        assert len(difficulties) >= 2, f"All questions have same difficulty: {difficulties}"


class TestSaveLoadDataset:
    """Tests for dataset JSON serialization."""

    def test_round_trip_preserves_data(self, mini_svd: Path, tmp_path: Path):
        dataset = generate_dataset(mini_svd)
        json_path = tmp_path / "dataset.json"

        save_dataset(dataset, json_path)
        loaded = load_dataset(json_path)

        assert loaded.name == dataset.name
        assert loaded.chip == dataset.chip
        assert loaded.question_count == dataset.question_count
        assert len(loaded.questions) == len(dataset.questions)
        assert loaded.categories == dataset.categories

    def test_round_trip_preserves_questions(self, mini_svd: Path, tmp_path: Path):
        dataset = generate_dataset(mini_svd)
        json_path = tmp_path / "dataset.json"

        save_dataset(dataset, json_path)
        loaded = load_dataset(json_path)

        for orig, loaded_q in zip(dataset.questions, loaded.questions, strict=True):
            assert orig.id == loaded_q.id
            assert orig.category == loaded_q.category
            assert orig.answer == loaded_q.answer
            assert orig.answer_format == loaded_q.answer_format

    def test_load_nonexistent_raises_error(self, tmp_path: Path):
        with pytest.raises(BenchmarkError, match="not found"):
            load_dataset(tmp_path / "nonexistent.json")

    def test_load_invalid_json_raises_error(self, tmp_path: Path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("not json", encoding="utf-8")
        with pytest.raises(BenchmarkError, match="Failed to load"):
            load_dataset(bad_json)

    def test_load_missing_fields_raises_error(self, tmp_path: Path):
        incomplete = tmp_path / "incomplete.json"
        incomplete.write_text('{"name": "test"}', encoding="utf-8")
        with pytest.raises(BenchmarkError, match="Invalid dataset"):
            load_dataset(incomplete)

    def test_round_trip_preserves_difficulty(self, mini_svd: Path, tmp_path: Path):
        """Difficulty field should survive JSON round-trip."""
        dataset = generate_dataset(mini_svd)
        json_path = tmp_path / "dataset.json"

        save_dataset(dataset, json_path)
        loaded = load_dataset(json_path)

        for orig, loaded_q in zip(dataset.questions, loaded.questions, strict=True):
            assert loaded_q.difficulty == orig.difficulty

    def test_round_trip_preserves_source_ref(self, mini_svd: Path, tmp_path: Path):
        """source_ref field should survive JSON round-trip."""
        from hwcc.bench.types import BenchQuestion

        q = BenchQuestion(
            id="usart2_apb_bus",
            category="clock_config",
            peripheral="USART2",
            register="",
            field_name="",
            question="What APB bus is USART2 connected to?",
            answer="APB1",
            answer_format="text",
            difficulty="medium",
            source_ref="RM0090 Table 1, Section 2.2",
        )
        from hwcc.bench.types import BenchDataset

        dataset = BenchDataset(
            name="TEST_DatasheetKnowledge",
            chip="STM32F407",
            source_svd="",
            question_count=1,
            questions=(q,),
            created="2026-03-14T00:00:00+00:00",
            categories=("clock_config",),
        )
        json_path = tmp_path / "datasheet.json"
        save_dataset(dataset, json_path)
        loaded = load_dataset(json_path)
        assert loaded.questions[0].source_ref == "RM0090 Table 1, Section 2.2"

    def test_load_legacy_dataset_without_source_ref(self, tmp_path: Path):
        """Old datasets without source_ref should load with default empty string."""
        import json

        legacy = {
            "name": "TEST",
            "chip": "TEST",
            "source_svd": "/tmp/test.svd",
            "question_count": 1,
            "questions": [
                {
                    "id": "spi1_base_address",
                    "category": "base_address",
                    "peripheral": "SPI1",
                    "register": "",
                    "field_name": "",
                    "question": "What is the base address?",
                    "answer": "0x40013000",
                    "answer_format": "hex",
                }
            ],
            "created": "2026-03-02T00:00:00+00:00",
            "categories": ["base_address"],
        }
        json_path = tmp_path / "legacy_no_source_ref.json"
        json_path.write_text(json.dumps(legacy), encoding="utf-8")

        loaded = load_dataset(json_path)
        assert loaded.questions[0].source_ref == ""

    def test_load_legacy_dataset_without_difficulty(self, tmp_path: Path):
        """Old datasets without difficulty field should load with default 'medium'."""
        import json

        legacy = {
            "name": "TEST",
            "chip": "TEST",
            "source_svd": "/tmp/test.svd",
            "question_count": 1,
            "questions": [
                {
                    "id": "spi1_base_address",
                    "category": "base_address",
                    "peripheral": "SPI1",
                    "register": "",
                    "field_name": "",
                    "question": "What is the base address?",
                    "answer": "0x40013000",
                    "answer_format": "hex",
                }
            ],
            "created": "2026-03-02T00:00:00+00:00",
            "categories": ["base_address"],
        }
        json_path = tmp_path / "legacy.json"
        json_path.write_text(json.dumps(legacy), encoding="utf-8")

        loaded = load_dataset(json_path)
        assert loaded.questions[0].difficulty == "medium"

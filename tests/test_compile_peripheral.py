"""Tests for the peripheral context compiler."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hwcc.compile.peripheral import PeripheralContextCompiler
from hwcc.config import (
    HardwareConfig,
    HwccConfig,
    ProjectConfig,
    SoftwareConfig,
)
from hwcc.store.base import BaseStore
from hwcc.types import Chunk, ChunkMetadata, EmbeddedChunk, SearchResult

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fake store for unit testing (avoids ChromaDB dependency)
# ---------------------------------------------------------------------------


class FakeStore(BaseStore):
    """BaseStore stand-in that holds chunks in memory."""

    def __init__(self, chunks: list[Chunk] | None = None) -> None:
        self._chunks = chunks or []

    def add(self, chunks: list[EmbeddedChunk], doc_id: str) -> int:
        return 0

    def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        where: dict[str, str | dict[str, str]] | None = None,
    ) -> list[SearchResult]:
        return []

    def delete(self, doc_id: str) -> int:
        return 0

    def get_chunk_metadata(
        self,
        where: dict[str, str | dict[str, str]] | None = None,
    ) -> list[ChunkMetadata]:
        chunks = self.get_chunks(where)
        return [c.metadata for c in chunks]

    def get_chunks(
        self,
        where: dict[str, str | dict[str, str]] | None = None,
    ) -> list[Chunk]:
        if where is None:
            return list(self._chunks)
        return [c for c in self._chunks if self._matches(c, where)]

    @staticmethod
    def _matches(chunk: Chunk, where: dict[str, object]) -> bool:
        for key, val in where.items():
            actual = getattr(chunk.metadata, key, None)
            if isinstance(val, dict) and "$ne" in val:
                if actual == val["$ne"]:
                    return False
            elif actual != val:
                return False
        return True

    def count(self) -> int:
        return len(self._chunks)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(
    chunk_id: str,
    content: str,
    doc_type: str = "svd",
    chip: str = "STM32F407",
    section_path: str = "",
    peripheral: str = "",
) -> Chunk:
    """Create a Chunk with the given metadata for testing."""
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        token_count=len(content.split()),
        metadata=ChunkMetadata(
            doc_id=f"test_{doc_type}",
            doc_type=doc_type,
            chip=chip,
            section_path=section_path,
            peripheral=peripheral,
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory with .rag/ structure."""
    rag_dir = tmp_path / ".rag"
    rag_dir.mkdir()
    (rag_dir / "context" / "peripherals").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def config() -> HwccConfig:
    """A config with hardware fields for template rendering."""
    return HwccConfig(
        project=ProjectConfig(name="test-project"),
        hardware=HardwareConfig(
            mcu="STM32F407VGT6",
            mcu_family="STM32F4",
            architecture="Cortex-M4",
            clock_mhz=168,
        ),
        software=SoftwareConfig(language="C"),
    )


@pytest.fixture
def spi_register_table() -> str:
    """Sample SPI register map content."""
    return (
        "### Registers\n\n"
        "| Register | Offset | Size | Access | Reset | Description |\n"
        "|----------|--------|------|--------|-------|-------------|\n"
        "| CR1 | 0x0000 | 32 | RW | 0x00000000 | Control register 1 |\n"
        "| CR2 | 0x0004 | 32 | RW | 0x00000000 | Control register 2 |\n"
        "| SR | 0x0008 | 32 | RO | 0x00000002 | Status register |"
    )


@pytest.fixture
def spi_field_table() -> str:
    """Sample SPI CR1 field table content."""
    return (
        "### CR1 Fields\n\n"
        "| Field | Bits | Access | Reset | Description |\n"
        "|-------|------|--------|-------|-------------|\n"
        "| BIDIMODE | [15] | RW | — | Bidirectional data mode enable |\n"
        "| SPE | [6] | RW | — | SPI enable |"
    )


@pytest.fixture
def spi_chunks(spi_register_table: str, spi_field_table: str) -> list[Chunk]:
    """SVD chunks for SPI1 peripheral."""
    return [
        _make_chunk(
            "stm32_svd_chunk_0000_abc",
            "## SPI1\n\n**Base Address:** `0x40013000`\n"
            "**Description:** Serial peripheral interface",
            section_path="STM32F407 Register Map > SPI1",
        ),
        _make_chunk(
            "stm32_svd_chunk_0001_def",
            spi_register_table,
            section_path="STM32F407 Register Map > SPI1 > Registers",
        ),
        _make_chunk(
            "stm32_svd_chunk_0002_ghi",
            spi_field_table,
            section_path="STM32F407 Register Map > SPI1 > CR1 Fields",
        ),
    ]


@pytest.fixture
def i2c_chunks() -> list[Chunk]:
    """SVD chunks for I2C1 peripheral."""
    return [
        _make_chunk(
            "stm32_svd_chunk_0010_aaa",
            "## I2C1\n\n**Base Address:** `0x40005400`\n**Description:** I2C interface",
            section_path="STM32F407 Register Map > I2C1",
        ),
        _make_chunk(
            "stm32_svd_chunk_0011_bbb",
            (
                "### Registers\n\n"
                "| Register | Offset | Size | Access | Reset | Description |\n"
                "|----------|--------|------|--------|-------|-------------|\n"
                "| CR1 | 0x0000 | 32 | RW | 0x00000000 | Control register 1 |"
            ),
            section_path="STM32F407 Register Map > I2C1 > Registers",
        ),
    ]


@pytest.fixture
def datasheet_chunks() -> list[Chunk]:
    """Non-SVD datasheet chunks that mention SPI1."""
    return [
        _make_chunk(
            "ds_chunk_0005_xyz",
            "SPI1 supports full-duplex synchronous transfers at up to 42 MHz.",
            doc_type="datasheet",
            section_path="STM32F407 Datasheet > SPI1 > Features",
        ),
        _make_chunk(
            "ds_chunk_0006_uvw",
            "The SPI clock is derived from APB2 at 84 MHz.",
            doc_type="datasheet",
            section_path="STM32F407 Datasheet > SPI1 > Clock Configuration",
        ),
    ]


# ---------------------------------------------------------------------------
# Tests: Basic compilation
# ---------------------------------------------------------------------------


class TestPeripheralCompilerBasic:
    """Basic compile() behavior."""

    def test_compile_returns_output_paths(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
    ) -> None:
        store = FakeStore(spi_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        assert len(paths) == 1
        assert paths[0].name == "spi1.md"

    def test_compile_creates_output_file(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
    ) -> None:
        store = FakeStore(spi_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        assert paths[0].exists()
        content = paths[0].read_text(encoding="utf-8")
        assert len(content) > 0

    def test_compile_creates_dir_if_missing(
        self,
        tmp_path: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
    ) -> None:
        # tmp_path has no .rag/ structure at all
        store = FakeStore(spi_chunks)
        compiler = PeripheralContextCompiler(tmp_path)
        paths = compiler.compile(store, config)

        assert len(paths) == 1
        assert paths[0].parent.exists()

    def test_compile_multiple_peripherals(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
        i2c_chunks: list[Chunk],
    ) -> None:
        store = FakeStore(spi_chunks + i2c_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        assert len(paths) == 2
        names = sorted(p.name for p in paths)
        assert names == ["i2c1.md", "spi1.md"]

    def test_multi_chip_same_name_produces_distinct_files(
        self,
        project_dir: Path,
        config: HwccConfig,
    ) -> None:
        """Same peripheral on different chips must not overwrite each other."""
        chunks = [
            _make_chunk(
                "stm32_svd_chunk_0000_a",
                "## SPI1\n\n**Base Address:** `0x40013000`",
                chip="STM32F407",
                section_path="STM32F407 Register Map > SPI1",
            ),
            _make_chunk(
                "nrf_svd_chunk_0000_b",
                "## SPI1\n\n**Base Address:** `0x40003000`",
                chip="nRF52840",
                section_path="nRF52840 Register Map > SPI1",
            ),
        ]
        store = FakeStore(chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        assert len(paths) == 2
        names = sorted(p.name for p in paths)
        assert names == ["spi1_nrf52840.md", "spi1_stm32f407.md"]

        # Verify each file has only its own chip's content
        contents = {p.name: p.read_text(encoding="utf-8") for p in paths}
        assert "0x40013000" in contents["spi1_stm32f407.md"]
        assert "0x40003000" not in contents["spi1_stm32f407.md"]
        assert "0x40003000" in contents["spi1_nrf52840.md"]
        assert "0x40013000" not in contents["spi1_nrf52840.md"]

    def test_compile_wraps_store_error(
        self,
        project_dir: Path,
        config: HwccConfig,
    ) -> None:
        """Non-CompileError from store should be wrapped in CompileError."""
        from hwcc.exceptions import CompileError as CE

        class BrokenStore(FakeStore):
            def get_chunks(
                self, where: dict[str, str | dict[str, str]] | None = None,
            ) -> list[Chunk]:
                msg = "connection lost"
                raise RuntimeError(msg)

        store = BrokenStore()
        compiler = PeripheralContextCompiler(project_dir)
        with pytest.raises(CE, match="connection lost"):
            compiler.compile(store, config)


# ---------------------------------------------------------------------------
# Tests: Empty / no-data edge cases
# ---------------------------------------------------------------------------


class TestPeripheralCompilerEmpty:
    """Edge cases with empty or missing data."""

    def test_empty_store_returns_empty(
        self,
        project_dir: Path,
        config: HwccConfig,
    ) -> None:
        store = FakeStore()
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        assert paths == []

    def test_no_svd_chunks_returns_empty(
        self,
        project_dir: Path,
        config: HwccConfig,
        datasheet_chunks: list[Chunk],
    ) -> None:
        """Only datasheet chunks, no SVD — no peripheral files generated."""
        store = FakeStore(datasheet_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        assert paths == []

    def test_svd_chunk_without_section_path_skipped(
        self,
        project_dir: Path,
        config: HwccConfig,
    ) -> None:
        """SVD chunk with empty or single-element section_path is ignored."""
        chunk = _make_chunk(
            "stm32_svd_chunk_0099_zzz",
            "Some SVD device header content",
            section_path="STM32F407 Register Map",  # only root, no peripheral
        )
        store = FakeStore([chunk])
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        assert paths == []


# ---------------------------------------------------------------------------
# Tests: Peripheral discovery
# ---------------------------------------------------------------------------


class TestPeripheralDiscovery:
    """Tests for _discover_peripherals()."""

    def test_discovers_from_section_path(
        self,
        project_dir: Path,
        spi_chunks: list[Chunk],
    ) -> None:
        compiler = PeripheralContextCompiler(project_dir)
        peripherals = compiler._discover_peripherals(spi_chunks)

        assert len(peripherals) == 1
        assert peripherals[0] == ("SPI1", "STM32F407")

    def test_discovers_multiple_peripherals(
        self,
        project_dir: Path,
        spi_chunks: list[Chunk],
        i2c_chunks: list[Chunk],
    ) -> None:
        compiler = PeripheralContextCompiler(project_dir)
        peripherals = compiler._discover_peripherals(spi_chunks + i2c_chunks)

        assert len(peripherals) == 2
        names = [p[0] for p in peripherals]
        assert "SPI1" in names
        assert "I2C1" in names

    def test_deduplicates_by_name_and_chip(
        self,
        project_dir: Path,
        spi_chunks: list[Chunk],
    ) -> None:
        """Multiple chunks for same peripheral should yield one entry."""
        compiler = PeripheralContextCompiler(project_dir)
        # spi_chunks has 3 chunks all for SPI1/STM32F407
        peripherals = compiler._discover_peripherals(spi_chunks)

        assert len(peripherals) == 1

    def test_multi_chip_peripherals(
        self,
        project_dir: Path,
    ) -> None:
        """Same peripheral name on different chips yields separate entries."""
        chunks = [
            _make_chunk(
                "stm32_svd_chunk_0000_a",
                "## SPI1",
                chip="STM32F407",
                section_path="STM32F407 Register Map > SPI1",
            ),
            _make_chunk(
                "nrf_svd_chunk_0000_b",
                "## SPI1",
                chip="nRF52840",
                section_path="nRF52840 Register Map > SPI1",
            ),
        ]
        compiler = PeripheralContextCompiler(project_dir)
        peripherals = compiler._discover_peripherals(chunks)

        assert len(peripherals) == 2

    def test_sorted_alphabetically(
        self,
        project_dir: Path,
    ) -> None:
        chunks = [
            _make_chunk("z_0000_a", "## USART1", section_path="Dev > USART1"),
            _make_chunk("a_0000_b", "## ADC1", section_path="Dev > ADC1"),
            _make_chunk("m_0000_c", "## I2C1", section_path="Dev > I2C1"),
        ]
        compiler = PeripheralContextCompiler(project_dir)
        peripherals = compiler._discover_peripherals(chunks)

        names = [p[0] for p in peripherals]
        assert names == ["ADC1", "I2C1", "USART1"]


# ---------------------------------------------------------------------------
# Tests: Register map extraction
# ---------------------------------------------------------------------------


class TestRegisterMapExtraction:
    """Tests for _extract_register_map()."""

    def test_extracts_register_content(
        self,
        project_dir: Path,
        spi_chunks: list[Chunk],
        spi_register_table: str,
    ) -> None:
        compiler = PeripheralContextCompiler(project_dir)
        register_map = compiler._extract_register_map("SPI1", spi_chunks)

        assert "CR1" in register_map
        assert "CR2" in register_map
        assert "SR" in register_map

    def test_preserves_document_order(
        self,
        project_dir: Path,
    ) -> None:
        """Chunks should be concatenated in chunk_id order (document order)."""
        chunks = [
            _make_chunk(
                "svd_chunk_0002_c",
                "THIRD content",
                section_path="Dev > SPI1 > Fields",
            ),
            _make_chunk(
                "svd_chunk_0000_a",
                "FIRST content",
                section_path="Dev > SPI1",
            ),
            _make_chunk(
                "svd_chunk_0001_b",
                "SECOND content",
                section_path="Dev > SPI1 > Registers",
            ),
        ]
        compiler = PeripheralContextCompiler(project_dir)
        register_map = compiler._extract_register_map("SPI1", chunks)

        # Verify order: FIRST before SECOND before THIRD
        first_pos = register_map.index("FIRST")
        second_pos = register_map.index("SECOND")
        third_pos = register_map.index("THIRD")
        assert first_pos < second_pos < third_pos

    def test_does_not_mix_peripherals(
        self,
        project_dir: Path,
        spi_chunks: list[Chunk],
        i2c_chunks: list[Chunk],
    ) -> None:
        all_chunks = spi_chunks + i2c_chunks
        compiler = PeripheralContextCompiler(project_dir)

        spi_map = compiler._extract_register_map("SPI1", all_chunks)
        assert "SPI1" in spi_map
        assert "I2C1" not in spi_map

        i2c_map = compiler._extract_register_map("I2C1", all_chunks)
        assert "I2C1" in i2c_map
        assert "SPI1" not in i2c_map

    def test_empty_when_no_matching_chunks(
        self,
        project_dir: Path,
    ) -> None:
        compiler = PeripheralContextCompiler(project_dir)
        register_map = compiler._extract_register_map("NONEXISTENT", [])

        assert register_map == ""


# ---------------------------------------------------------------------------
# Tests: Cross-document details
# ---------------------------------------------------------------------------


class TestPeripheralDetails:
    """Tests for _gather_peripheral_details()."""

    def test_gathers_from_non_svd_chunks(
        self,
        project_dir: Path,
        datasheet_chunks: list[Chunk],
    ) -> None:
        compiler = PeripheralContextCompiler(project_dir)
        details = compiler._gather_peripheral_details("SPI1", datasheet_chunks)

        assert "full-duplex" in details
        assert "APB2" in details

    def test_empty_when_no_matching_chunks(
        self,
        project_dir: Path,
    ) -> None:
        compiler = PeripheralContextCompiler(project_dir)
        details = compiler._gather_peripheral_details("NONEXISTENT", [])

        assert details == ""

    def test_limited_to_max_detail_chunks(
        self,
        project_dir: Path,
    ) -> None:
        """Only first MAX_DETAIL_CHUNKS chunks are included."""
        chunks = [
            _make_chunk(
                f"ds_chunk_{i:04d}_x",
                f"UART detail chunk {i}",
                doc_type="datasheet",
                section_path=f"Datasheet > UART > Section {i}",
            )
            for i in range(10)
        ]
        compiler = PeripheralContextCompiler(project_dir)
        details = compiler._gather_peripheral_details("UART", chunks)

        # Should only contain first 5 chunks (MAX_DETAIL_CHUNKS)
        assert "chunk 0" in details
        assert "chunk 4" in details
        assert "chunk 5" not in details

    def test_case_insensitive_section_path_matching(
        self,
        project_dir: Path,
    ) -> None:
        chunks = [
            _make_chunk(
                "ds_chunk_0000_x",
                "SPI configuration info",
                doc_type="datasheet",
                section_path="Datasheet > spi1",  # lowercase element
            ),
        ]
        compiler = PeripheralContextCompiler(project_dir)
        details = compiler._gather_peripheral_details("SPI1", chunks)

        assert "SPI configuration" in details

    def test_no_false_positive_substring_match(
        self,
        project_dir: Path,
    ) -> None:
        """SPI1 must NOT match SPI10, SPI11, etc."""
        chunks = [
            _make_chunk(
                "ds_chunk_0000_x",
                "SPI10 has extended features",
                doc_type="datasheet",
                section_path="Datasheet > SPI10 > Features",
            ),
            _make_chunk(
                "ds_chunk_0001_y",
                "TIM10 is a general purpose timer",
                doc_type="datasheet",
                section_path="Datasheet > TIM10",
            ),
        ]
        compiler = PeripheralContextCompiler(project_dir)

        # SPI1 should NOT match SPI10
        spi1_details = compiler._gather_peripheral_details("SPI1", chunks)
        assert spi1_details == ""

        # TIM1 should NOT match TIM10
        tim1_details = compiler._gather_peripheral_details("TIM1", chunks)
        assert tim1_details == ""

        # But SPI10 should match SPI10
        spi10_details = compiler._gather_peripheral_details("SPI10", chunks)
        assert "extended features" in spi10_details


# ---------------------------------------------------------------------------
# Tests: Rendered output content
# ---------------------------------------------------------------------------


class TestRenderedOutput:
    """Tests for the final rendered output files."""

    def test_output_contains_peripheral_name(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
    ) -> None:
        store = FakeStore(spi_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        assert "SPI1" in content

    def test_output_contains_mcu(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
    ) -> None:
        store = FakeStore(spi_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        assert "STM32F407VGT6" in content

    def test_output_contains_peripheral_description_as_overview(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
    ) -> None:
        """SVD description should be extracted and rendered as overview text."""
        store = FakeStore(spi_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        # Description should appear before the Register Map section as overview
        reg_map_pos = content.find("## Register Map")
        desc_pos = content.find("Serial peripheral interface")
        assert desc_pos != -1, "Description not found in output"
        assert reg_map_pos != -1, "Register Map section not found"
        assert desc_pos < reg_map_pos, "Description should appear before Register Map"

    def test_output_contains_register_map(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
    ) -> None:
        store = FakeStore(spi_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        assert "## Register Map" in content
        assert "CR1" in content
        assert "0x40013000" in content

    def test_output_contains_cross_doc_details(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
        datasheet_chunks: list[Chunk],
    ) -> None:
        store = FakeStore(spi_chunks + datasheet_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        assert "full-duplex" in content

    def test_output_filename_lowercased(
        self,
        project_dir: Path,
        config: HwccConfig,
    ) -> None:
        chunks = [
            _make_chunk(
                "svd_chunk_0000_a",
                "## USART1\n\n**Base Address:** `0x40011000`",
                section_path="Dev > USART1",
            ),
        ]
        store = FakeStore(chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        assert paths[0].name == "usart1.md"

    def test_output_in_peripherals_dir(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
    ) -> None:
        store = FakeStore(spi_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        expected_dir = project_dir / ".rag" / "context" / "peripherals"
        assert paths[0].parent == expected_dir


# ---------------------------------------------------------------------------
# Tests: Pin assignments in peripheral context
# ---------------------------------------------------------------------------


class TestPinAssignments:
    """Tests for pin filtering and rendering in peripheral context."""

    def test_filter_pins_by_prefix(self, project_dir: Path) -> None:
        compiler = PeripheralContextCompiler(project_dir)
        pins = {"spi1_sck": "PA5", "spi1_mosi": "PA7", "i2c1_scl": "PB6", "led": "PC13"}
        result = compiler._filter_pins_for_peripheral("SPI1", pins)
        assert result == [("MOSI", "PA7"), ("SCK", "PA5")]

    def test_filter_pins_case_insensitive(self, project_dir: Path) -> None:
        compiler = PeripheralContextCompiler(project_dir)
        pins = {"SPI1_SCK": "PA5", "SPI1_MOSI": "PA7"}
        result = compiler._filter_pins_for_peripheral("SPI1", pins)
        assert len(result) == 2

    def test_filter_pins_no_false_positive(self, project_dir: Path) -> None:
        """SPI1 prefix must not match SPI10."""
        compiler = PeripheralContextCompiler(project_dir)
        pins = {"spi10_sck": "PA5"}
        result = compiler._filter_pins_for_peripheral("SPI1", pins)
        assert result == []

    def test_pins_in_rendered_output(
        self,
        project_dir: Path,
        spi_chunks: list[Chunk],
    ) -> None:
        config_with_pins = HwccConfig(
            project=ProjectConfig(name="test-project"),
            hardware=HardwareConfig(mcu="STM32F407VGT6", mcu_family="STM32F4"),
            software=SoftwareConfig(language="C"),
            pins={"spi1_sck": "PA5", "spi1_mosi": "PA7"},
        )
        store = FakeStore(spi_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config_with_pins)

        content = paths[0].read_text(encoding="utf-8")
        assert "## Pin Assignments" in content
        assert "PA5" in content
        assert "PA7" in content

    def test_no_pins_section_when_empty(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
    ) -> None:
        store = FakeStore(spi_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        assert "## Pin Assignments" not in content


# ---------------------------------------------------------------------------
# Tests: Citations in output
# ---------------------------------------------------------------------------


class TestCitationsInOutput:
    """Tests for source provenance citations in compiled output."""

    def test_detail_chunks_have_citations(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
        datasheet_chunks: list[Chunk],
    ) -> None:
        """Non-SVD detail chunks should have inline *Source:* citations."""
        # Create manifest so title_map works
        from hwcc.manifest import DocumentEntry, Manifest, save_manifest

        manifest = Manifest()
        manifest.add_document(DocumentEntry(
            id="test_datasheet",
            path="/docs/STM32F407_Datasheet.pdf",
            doc_type="datasheet",
            hash="abc",
            added="2026-01-01",
            chunks=10,
        ))
        manifest.add_document(DocumentEntry(
            id="test_svd",
            path="/docs/stm32f407.svd",
            doc_type="svd",
            hash="def",
            added="2026-01-01",
            chunks=50,
        ))
        manifest_path = project_dir / ".rag" / "manifest.json"
        save_manifest(manifest, manifest_path)

        store = FakeStore(spi_chunks + datasheet_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        assert "*Source:" in content

    def test_svd_register_map_has_source_citation(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
    ) -> None:
        """SVD register map should have a source citation appended."""
        from hwcc.manifest import DocumentEntry, Manifest, save_manifest

        manifest = Manifest()
        manifest.add_document(DocumentEntry(
            id="test_svd",
            path="/docs/stm32f407.svd",
            doc_type="svd",
            hash="abc",
            added="2026-01-01",
            chunks=50,
        ))
        manifest_path = project_dir / ".rag" / "manifest.json"
        save_manifest(manifest, manifest_path)

        store = FakeStore(spi_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        assert "*Source: stm32f407," in content

    def test_no_manifest_no_crash(
        self,
        project_dir: Path,
        config: HwccConfig,
        spi_chunks: list[Chunk],
    ) -> None:
        """Without manifest, compilation should still work (no citations)."""
        store = FakeStore(spi_chunks)
        compiler = PeripheralContextCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        assert "SPI1" in content
        # No *Source:* because no manifest
        assert "*Source:" not in content


# ---------------------------------------------------------------------------
# Tests: FakeStore.get_chunks()
# ---------------------------------------------------------------------------


class TestFakeStoreGetChunks:
    """Tests for the FakeStore.get_chunks() method."""

    def test_returns_all_chunks_without_filter(self) -> None:
        chunks = [
            _make_chunk("a", "content a", doc_type="svd"),
            _make_chunk("b", "content b", doc_type="datasheet"),
        ]
        store = FakeStore(chunks)
        result = store.get_chunks()

        assert len(result) == 2

    def test_filters_by_doc_type(self) -> None:
        chunks = [
            _make_chunk("a", "content a", doc_type="svd"),
            _make_chunk("b", "content b", doc_type="datasheet"),
            _make_chunk("c", "content c", doc_type="svd"),
        ]
        store = FakeStore(chunks)
        result = store.get_chunks(where={"doc_type": "svd"})

        assert len(result) == 2
        assert all(c.metadata.doc_type == "svd" for c in result)

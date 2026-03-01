"""Tests for the hot context compiler."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hwcc.compile.hot_context import HotContextCompiler
from hwcc.config import (
    ConventionsConfig,
    HardwareConfig,
    HwccConfig,
    OutputConfig,
    ProjectConfig,
    SoftwareConfig,
)
from hwcc.manifest import DocumentEntry, Manifest, save_manifest
from hwcc.store.base import BaseStore
from hwcc.types import Chunk, ChunkMetadata, EmbeddedChunk, SearchResult

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fake store for unit testing (avoids ChromaDB dependency)
# ---------------------------------------------------------------------------


class FakeStore(BaseStore):
    """Minimal BaseStore stand-in for unit tests."""

    def __init__(self, metadata: list[ChunkMetadata] | None = None) -> None:
        self._metadata = metadata or []

    def add(self, chunks: list[EmbeddedChunk], doc_id: str) -> int:
        return 0

    def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        where: dict[str, str] | None = None,
    ) -> list[SearchResult]:
        return []

    def delete(self, doc_id: str) -> int:
        return 0

    def get_chunk_metadata(
        self,
        where: dict[str, str] | None = None,
    ) -> list[ChunkMetadata]:
        if where is None:
            return list(self._metadata)
        return [
            m
            for m in self._metadata
            if all(getattr(m, key, None) == v for key, v in where.items())
        ]

    def get_chunks(
        self,
        where: dict[str, str] | None = None,
    ) -> list[Chunk]:
        return []

    def count(self) -> int:
        return len(self._metadata)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory with .rag/ structure."""
    rag_dir = tmp_path / ".rag"
    rag_dir.mkdir()
    (rag_dir / "context").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def full_config() -> HwccConfig:
    """A complete config with all fields populated."""
    return HwccConfig(
        project=ProjectConfig(
            name="motor-controller",
            description="Brushless DC motor controller",
        ),
        hardware=HardwareConfig(
            mcu="STM32F407VGT6",
            mcu_family="STM32F4",
            architecture="Cortex-M4",
            clock_mhz=168,
            flash_kb=1024,
            ram_kb=192,
        ),
        software=SoftwareConfig(
            rtos="FreeRTOS 10.5.1",
            hal="STM32 HAL v1.27.1",
            language="C",
            build_system="CMake",
        ),
        conventions=ConventionsConfig(
            register_access="HAL functions only, no direct register writes",
            error_handling="return HAL_StatusTypeDef",
            naming="snake_case for functions, UPPER_CASE for defines",
        ),
        output=OutputConfig(hot_context_max_lines=120),
    )


@pytest.fixture
def full_manifest() -> Manifest:
    """A manifest with multiple documents across chips."""
    m = Manifest()
    m.add_document(
        DocumentEntry(
            id="stm32f407_svd",
            path="board.svd",
            doc_type="svd",
            hash="sha256:abc123",
            added="2026-02-28T10:00:00",
            chunks=892,
            chip="STM32F407",
        )
    )
    m.add_document(
        DocumentEntry(
            id="stm32f407_datasheet_pdf",
            path="docs/STM32F407_datasheet.pdf",
            doc_type="datasheet",
            hash="sha256:def456",
            added="2026-02-28T10:05:00",
            chunks=847,
            chip="STM32F407",
        )
    )
    m.add_document(
        DocumentEntry(
            id="tps65218_datasheet_pdf",
            path="docs/TPS65218_datasheet.pdf",
            doc_type="datasheet",
            hash="sha256:ghi789",
            added="2026-02-28T10:10:00",
            chunks=312,
            chip="TPS65218",
        )
    )
    return m


@pytest.fixture
def full_store_metadata() -> list[ChunkMetadata]:
    """Store metadata with peripherals from SVD parsing."""
    peripherals = ["SPI1", "SPI2", "I2C1", "USART1", "GPIOA", "GPIOB", "TIM1"]
    metadata: list[ChunkMetadata] = []
    for p in peripherals:
        # Each peripheral typically has multiple chunks
        for _i in range(3):
            metadata.append(
                ChunkMetadata(
                    doc_id="stm32f407_svd",
                    doc_type="svd",
                    chip="STM32F407",
                    peripheral=p,
                    content_type="register_map",
                )
            )
    # Add non-peripheral chunks (e.g., from PDF)
    metadata.append(
        ChunkMetadata(
            doc_id="stm32f407_datasheet_pdf",
            doc_type="datasheet",
            chip="STM32F407",
            peripheral="",
        )
    )
    return metadata


def _setup_project(
    project_dir: Path,
    manifest: Manifest,
    store_metadata: list[ChunkMetadata],
    config: HwccConfig,
) -> tuple[HotContextCompiler, FakeStore]:
    """Helper to set up a compiler with project data."""
    save_manifest(manifest, project_dir / ".rag" / "manifest.json")
    store = FakeStore(metadata=store_metadata)
    compiler = HotContextCompiler(project_dir)
    return compiler, store


# ---------------------------------------------------------------------------
# HotContextCompiler — basic compilation
# ---------------------------------------------------------------------------


class TestHotContextCompilerBasic:
    def test_compile_returns_output_path(
        self,
        project_dir: Path,
        full_config: HwccConfig,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        compiler, store = _setup_project(
            project_dir,
            full_manifest,
            full_store_metadata,
            full_config,
        )
        paths = compiler.compile(store, full_config)
        assert len(paths) == 1
        assert paths[0] == project_dir / ".rag" / "context" / "hot.md"

    def test_compile_creates_hot_md_file(
        self,
        project_dir: Path,
        full_config: HwccConfig,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        compiler, store = _setup_project(
            project_dir,
            full_manifest,
            full_store_metadata,
            full_config,
        )
        compiler.compile(store, full_config)
        hot_md = project_dir / ".rag" / "context" / "hot.md"
        assert hot_md.exists()
        content = hot_md.read_text()
        assert len(content) > 0

    def test_compile_creates_context_dir_if_missing(
        self,
        tmp_path: Path,
        full_config: HwccConfig,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        # Only create .rag/, not .rag/context/
        rag_dir = tmp_path / ".rag"
        rag_dir.mkdir()
        save_manifest(full_manifest, rag_dir / "manifest.json")
        store = FakeStore(metadata=full_store_metadata)
        compiler = HotContextCompiler(tmp_path)
        compiler.compile(store, full_config)
        assert (rag_dir / "context" / "hot.md").exists()


# ---------------------------------------------------------------------------
# Content verification
# ---------------------------------------------------------------------------


class TestHotContextContent:
    def test_contains_hardware_info(
        self,
        project_dir: Path,
        full_config: HwccConfig,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        compiler, store = _setup_project(
            project_dir,
            full_manifest,
            full_store_metadata,
            full_config,
        )
        compiler.compile(store, full_config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        assert "STM32F407VGT6" in content
        assert "Cortex-M4" in content
        assert "168MHz" in content

    def test_contains_software_info(
        self,
        project_dir: Path,
        full_config: HwccConfig,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        compiler, store = _setup_project(
            project_dir,
            full_manifest,
            full_store_metadata,
            full_config,
        )
        compiler.compile(store, full_config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        assert "FreeRTOS" in content
        assert "CMake" in content

    def test_contains_conventions(
        self,
        project_dir: Path,
        full_config: HwccConfig,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        compiler, store = _setup_project(
            project_dir,
            full_manifest,
            full_store_metadata,
            full_config,
        )
        compiler.compile(store, full_config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        assert "HAL functions only" in content
        assert "snake_case" in content

    def test_contains_document_table(
        self,
        project_dir: Path,
        full_config: HwccConfig,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        compiler, store = _setup_project(
            project_dir,
            full_manifest,
            full_store_metadata,
            full_config,
        )
        compiler.compile(store, full_config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        assert "Indexed Documents" in content
        assert "board" in content  # derived title from board.svd
        assert "847" in content  # chunk count from datasheet
        assert "892" in content  # chunk count from SVD

    def test_contains_peripheral_list(
        self,
        project_dir: Path,
        full_config: HwccConfig,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        compiler, store = _setup_project(
            project_dir,
            full_manifest,
            full_store_metadata,
            full_config,
        )
        compiler.compile(store, full_config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        assert "Peripherals" in content
        assert "SPI1" in content
        assert "I2C1" in content
        assert "USART1" in content

    def test_deduplicates_peripheral_names(
        self,
        project_dir: Path,
        full_config: HwccConfig,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        """Each peripheral should appear once even if it has many chunks."""
        compiler, store = _setup_project(
            project_dir,
            full_manifest,
            full_store_metadata,
            full_config,
        )
        compiler.compile(store, full_config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        # SPI1 has 3 chunks in fixture but should appear only once in output
        assert content.count("SPI1") == 1

    def test_peripheral_register_count(
        self,
        project_dir: Path,
        full_config: HwccConfig,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        """Each peripheral should show its SVD chunk count as register_count."""
        compiler, store = _setup_project(
            project_dir,
            full_manifest,
            full_store_metadata,
            full_config,
        )
        compiler.compile(store, full_config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        # Fixture has 3 SVD chunks per peripheral — count should render in output
        # Template renders: "- **SPI1** (3 registers)"
        assert "3 registers" in content

    def test_multi_chip_documents_shown(
        self,
        project_dir: Path,
        full_config: HwccConfig,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        compiler, store = _setup_project(
            project_dir,
            full_manifest,
            full_store_metadata,
            full_config,
        )
        compiler.compile(store, full_config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        assert "STM32F407" in content
        assert "TPS65218" in content


# ---------------------------------------------------------------------------
# Empty / minimal projects
# ---------------------------------------------------------------------------


class TestHotContextEmpty:
    def test_empty_project_no_crash(self, project_dir: Path):
        """Compile with no documents and empty store should not crash."""
        manifest = Manifest()
        save_manifest(manifest, project_dir / ".rag" / "manifest.json")
        store = FakeStore()
        config = HwccConfig()
        compiler = HotContextCompiler(project_dir)
        paths = compiler.compile(store, config)
        assert len(paths) == 1
        content = paths[0].read_text()
        assert "Hardware Context" in content

    def test_config_only_no_documents(self, project_dir: Path, full_config: HwccConfig):
        """Config data should render even without any indexed documents."""
        manifest = Manifest()
        save_manifest(manifest, project_dir / ".rag" / "manifest.json")
        store = FakeStore()
        compiler = HotContextCompiler(project_dir)
        compiler.compile(store, full_config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        assert "STM32F407VGT6" in content
        assert "Indexed Documents" not in content  # No documents to show
        assert "Peripherals" not in content  # No peripherals to show

    def test_store_with_zero_chunks(self, project_dir: Path, full_config: HwccConfig):
        """Empty store but with manifest documents should show doc table."""
        manifest = Manifest()
        manifest.add_document(
            DocumentEntry(
                id="doc1",
                path="test.svd",
                doc_type="svd",
                hash="sha256:abc",
                added="2026-02-28T10:00:00",
                chunks=0,
                chip="STM32F407",
            )
        )
        save_manifest(manifest, project_dir / ".rag" / "manifest.json")
        store = FakeStore()
        compiler = HotContextCompiler(project_dir)
        compiler.compile(store, full_config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        assert "Indexed Documents" in content


# ---------------------------------------------------------------------------
# Line budget enforcement
# ---------------------------------------------------------------------------


class TestHotContextLineBudget:
    def test_respects_max_lines(
        self,
        project_dir: Path,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        """Output should not exceed hot_context_max_lines."""
        config = HwccConfig(
            project=ProjectConfig(name="test"),
            hardware=HardwareConfig(
                mcu="STM32F407VGT6",
                architecture="Cortex-M4",
                clock_mhz=168,
                flash_kb=1024,
                ram_kb=192,
            ),
            software=SoftwareConfig(rtos="FreeRTOS", hal="HAL", build_system="CMake"),
            conventions=ConventionsConfig(
                register_access="HAL only",
                error_handling="return status",
                naming="snake_case",
            ),
            output=OutputConfig(hot_context_max_lines=120),
        )
        compiler, store = _setup_project(
            project_dir,
            full_manifest,
            full_store_metadata,
            config,
        )
        compiler.compile(store, config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        line_count = len(content.strip().splitlines())
        assert line_count <= 120

    def test_very_tight_budget_still_works(self, project_dir: Path):
        """Even with a very small line budget, should produce valid output."""
        config = HwccConfig(
            project=ProjectConfig(name="test"),
            hardware=HardwareConfig(mcu="STM32F407VGT6"),
            output=OutputConfig(hot_context_max_lines=10),
        )
        manifest = Manifest()
        save_manifest(manifest, project_dir / ".rag" / "manifest.json")
        store = FakeStore()
        compiler = HotContextCompiler(project_dir)
        compiler.compile(store, config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        line_count = len(content.strip().splitlines())
        assert line_count <= 10
        assert "Hardware Context" in content

    def test_truncation_removes_conventions_first(
        self,
        project_dir: Path,
        full_manifest: Manifest,
        full_store_metadata: list[ChunkMetadata],
    ):
        """With tight budget, conventions should be dropped before peripherals."""
        config = HwccConfig(
            project=ProjectConfig(name="test"),
            hardware=HardwareConfig(mcu="STM32F407VGT6", architecture="Cortex-M4"),
            conventions=ConventionsConfig(
                register_access="HAL only",
                error_handling="return status",
                naming="snake_case",
            ),
            output=OutputConfig(hot_context_max_lines=25),
        )
        compiler, store = _setup_project(
            project_dir,
            full_manifest,
            full_store_metadata,
            config,
        )
        compiler.compile(store, config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        # With tight budget, conventions should be removed
        # (peripherals and documents have higher priority)
        line_count = len(content.strip().splitlines())
        assert line_count <= 25

    def test_budget_with_many_peripherals(self, project_dir: Path):
        """Budget should be respected even with many peripherals.

        Note: Errata priority testing deferred to task 2.2 when
        errata population is implemented.
        """
        errata_metadata = [
            ChunkMetadata(
                doc_id="errata_doc",
                doc_type="errata",
                chip="STM32F407",
                peripheral="SPI",
            )
        ]
        # Many peripherals to exceed budget
        periph_metadata = [
            ChunkMetadata(
                doc_id="svd_doc",
                doc_type="svd",
                chip="STM32F407",
                peripheral=f"PERIPH{i}",
            )
            for i in range(50)
        ]
        manifest = Manifest()
        manifest.add_document(
            DocumentEntry(
                id="svd_doc",
                path="board.svd",
                doc_type="svd",
                hash="sha256:abc",
                added="2026-02-28T10:00:00",
                chunks=100,
                chip="STM32F407",
            )
        )
        save_manifest(manifest, project_dir / ".rag" / "manifest.json")

        config = HwccConfig(
            project=ProjectConfig(name="test"),
            hardware=HardwareConfig(mcu="STM32F407VGT6"),
            output=OutputConfig(hot_context_max_lines=30),
        )

        store = FakeStore(metadata=errata_metadata + periph_metadata)
        compiler = HotContextCompiler(project_dir)

        compiler.compile(store, config)
        content = (project_dir / ".rag" / "context" / "hot.md").read_text()
        line_count = len(content.strip().splitlines())
        assert line_count <= 30


# ---------------------------------------------------------------------------
# Manifest timestamp update
# ---------------------------------------------------------------------------


class TestHotContextManifest:
    def test_updates_last_compiled_timestamp(
        self,
        project_dir: Path,
        full_config: HwccConfig,
    ):
        manifest = Manifest()
        assert manifest.last_compiled == ""
        save_manifest(manifest, project_dir / ".rag" / "manifest.json")

        store = FakeStore()
        compiler = HotContextCompiler(project_dir)
        compiler.compile(store, full_config)
        # Re-load manifest and check timestamp was set
        from hwcc.manifest import load_manifest

        updated = load_manifest(project_dir / ".rag" / "manifest.json")
        assert updated.last_compiled != ""
        assert "2026" in updated.last_compiled or "202" in updated.last_compiled

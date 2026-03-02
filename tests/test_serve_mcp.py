"""Tests for the MCP server module (hwcc.serve.server)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from hwcc.exceptions import HwccError, McpError, StoreError
from hwcc.manifest import DocumentEntry, Manifest
from hwcc.types import Chunk, ChunkMetadata, SearchResult

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_store() -> MagicMock:
    """Mock BaseStore."""
    store = MagicMock()
    store.count.return_value = 100
    return store


@pytest.fixture()
def mock_search_engine() -> MagicMock:
    """Mock SearchEngine."""
    return MagicMock()


@pytest.fixture()
def manifest() -> Manifest:
    """Sample manifest with 2 documents."""
    m = Manifest()
    m.add_document(
        DocumentEntry(
            id="stm32f407_svd",
            path="STM32F407.svd",
            doc_type="svd",
            hash="sha256:abc",
            added="2026-01-01T00:00:00",
            chunks=100,
            chip="STM32F407",
        )
    )
    m.add_document(
        DocumentEntry(
            id="rm0090_pdf",
            path="RM0090.pdf",
            doc_type="pdf",
            hash="sha256:def",
            added="2026-01-02T00:00:00",
            chunks=500,
            chip="STM32F407",
        )
    )
    return m


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """Create a temporary project root with .rag/context/peripherals/."""
    peripherals_dir = tmp_path / ".rag" / "context" / "peripherals"
    peripherals_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def hwcc_ctx(
    mock_store: MagicMock,
    mock_search_engine: MagicMock,
    manifest: Manifest,
    project_root: Path,
):
    """Build an HwccContext with mocked dependencies."""
    from hwcc.serve.server import HwccContext

    return HwccContext(
        store=mock_store,
        search_engine=mock_search_engine,
        project_root=project_root,
        manifest=manifest,
    )


def _make_search_result(
    content: str,
    peripheral: str = "",
    chip: str = "",
    doc_type: str = "svd",
) -> SearchResult:
    """Helper to build a SearchResult."""
    return SearchResult(
        chunk=Chunk(
            chunk_id="chunk-1",
            content=content,
            token_count=10,
            metadata=ChunkMetadata(
                doc_id="test_doc",
                doc_type=doc_type,
                chip=chip,
                peripheral=peripheral,
                content_type="register_description",
            ),
        ),
        score=0.85,
        distance=0.15,
    )


def _make_chunk(
    content: str,
    peripheral: str = "",
    content_type: str = "",
    doc_type: str = "svd",
) -> Chunk:
    """Helper to build a Chunk."""
    return Chunk(
        chunk_id="chunk-1",
        content=content,
        token_count=10,
        metadata=ChunkMetadata(
            doc_id="test_doc",
            doc_type=doc_type,
            chip="STM32F407",
            peripheral=peripheral,
            content_type=content_type,
        ),
    )


# ---------------------------------------------------------------------------
# McpError in exception hierarchy
# ---------------------------------------------------------------------------


class TestMcpError:
    def test_mcp_error_is_hwcc_error(self):
        assert issubclass(McpError, HwccError)

    def test_mcp_error_instantiation(self):
        err = McpError("server failed")
        assert str(err) == "server failed"
        assert isinstance(err, HwccError)


# ---------------------------------------------------------------------------
# Imports and entry points
# ---------------------------------------------------------------------------


class TestImports:
    def test_run_server_importable(self):
        from hwcc.serve.server import run_server

        assert callable(run_server)

    def test_hwcc_context_importable(self):
        from hwcc.serve.server import HwccContext

        assert HwccContext is not None

    def test_create_server_importable(self):
        from hwcc.serve.server import create_server

        assert callable(create_server)

    def test_run_server_reexported_from_init(self):
        from hwcc.serve import run_server

        assert callable(run_server)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class TestBuildWhereReexport:
    """Verify that server.py uses the shared build_where from hwcc.search."""

    def test_server_imports_build_where_from_search(self):
        from hwcc.serve import server

        # server module should use the shared build_where from hwcc.search
        assert "build_where" in dir(server)

    def test_build_where_with_content_type(self):
        from hwcc.search import build_where

        result = build_where(peripheral="SPI1", content_type="register_description")
        assert "$and" in result
        assert {"peripheral": "SPI1"} in result["$and"]
        assert {"content_type": "register_description"} in result["$and"]


class TestValidatePeripheralName:
    def test_valid_name(self):
        from hwcc.serve.server import _validate_peripheral_name

        assert _validate_peripheral_name("SPI1") is None
        assert _validate_peripheral_name("USART2") is None
        assert _validate_peripheral_name("I2C1") is None

    def test_rejects_path_traversal(self):
        from hwcc.serve.server import _validate_peripheral_name

        assert _validate_peripheral_name("../etc/passwd") is not None
        assert _validate_peripheral_name("foo/bar") is not None
        assert _validate_peripheral_name("foo\\bar") is not None

    def test_rejects_null_bytes(self):
        from hwcc.serve.server import _validate_peripheral_name

        assert _validate_peripheral_name("SPI1\x00") is not None


# ---------------------------------------------------------------------------
# hw_search
# ---------------------------------------------------------------------------


class TestHwSearch:
    def test_returns_formatted_results(self, hwcc_ctx, mock_search_engine):
        from hwcc.serve.server import handle_hw_search

        results = [
            _make_search_result("SPI1 CR1 register", peripheral="SPI1", chip="STM32F407"),
        ]
        mock_search_engine.search.return_value = (results, 0.05)

        output = handle_hw_search(hwcc_ctx, query="SPI DMA")

        mock_search_engine.search.assert_called_once_with(
            "SPI DMA", k=5, chip="", doc_type="", peripheral=""
        )
        assert "SPI1 CR1 register" in output
        assert "0.05" in output or "score" in output.lower()

    def test_with_filters_passes_them_through(self, hwcc_ctx, mock_search_engine):
        from hwcc.serve.server import handle_hw_search

        mock_search_engine.search.return_value = ([], 0.01)

        handle_hw_search(
            hwcc_ctx,
            query="DMA",
            chip="STM32F407",
            doc_type="svd",
            peripheral="SPI1",
            top_k=10,
        )

        mock_search_engine.search.assert_called_once_with(
            "DMA", k=10, chip="STM32F407", doc_type="svd", peripheral="SPI1"
        )

    def test_empty_results(self, hwcc_ctx, mock_search_engine):
        from hwcc.serve.server import handle_hw_search

        mock_search_engine.search.return_value = ([], 0.01)

        output = handle_hw_search(hwcc_ctx, query="nonexistent")
        assert "no results" in output.lower()

    def test_top_k_clamped_to_max(self, hwcc_ctx, mock_search_engine):
        from hwcc.serve.server import handle_hw_search

        mock_search_engine.search.return_value = ([], 0.01)

        handle_hw_search(hwcc_ctx, query="test", top_k=9999)
        mock_search_engine.search.assert_called_once()
        _, kwargs = mock_search_engine.search.call_args
        assert kwargs["k"] <= 50

    def test_top_k_clamped_to_min(self, hwcc_ctx, mock_search_engine):
        from hwcc.serve.server import handle_hw_search

        mock_search_engine.search.return_value = ([], 0.01)

        handle_hw_search(hwcc_ctx, query="test", top_k=-5)
        _, kwargs = mock_search_engine.search.call_args
        assert kwargs["k"] >= 1

    def test_search_error_returns_message(self, hwcc_ctx, mock_search_engine):
        from hwcc.serve.server import handle_hw_search

        mock_search_engine.search.side_effect = StoreError("connection lost")

        output = handle_hw_search(hwcc_ctx, query="SPI")
        assert "error" in output.lower()


# ---------------------------------------------------------------------------
# hw_registers
# ---------------------------------------------------------------------------


class TestHwRegisters:
    def test_returns_register_chunks(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_hw_registers

        chunks = [
            _make_chunk(
                "## SPI1_CR1\nBit 0: CPHA",
                peripheral="SPI1",
                content_type="register_description",
            ),
        ]
        mock_store.get_chunks.return_value = chunks

        output = handle_hw_registers(hwcc_ctx, peripheral="SPI1")

        assert "SPI1_CR1" in output
        assert "CPHA" in output

    def test_with_register_filter(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_hw_registers

        chunks = [
            _make_chunk("## SPI1_CR1\nBit 0: CPHA", peripheral="SPI1"),
            _make_chunk("## SPI1_CR2\nBit 0: RXDMAEN", peripheral="SPI1"),
        ]
        mock_store.get_chunks.return_value = chunks

        output = handle_hw_registers(hwcc_ctx, peripheral="SPI1", register="CR1")
        assert "CR1" in output

    def test_passes_content_type_register_description(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_hw_registers

        mock_store.get_chunks.return_value = []

        handle_hw_registers(hwcc_ctx, peripheral="SPI1")

        call_kwargs = mock_store.get_chunks.call_args[1]
        where = call_kwargs["where"]
        assert "$and" in where
        assert {"peripheral": "SPI1"} in where["$and"]
        assert {"content_type": "register_description"} in where["$and"]

    def test_with_chip_filter_builds_and_clause(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_hw_registers

        mock_store.get_chunks.return_value = []

        handle_hw_registers(hwcc_ctx, peripheral="SPI1", chip="STM32F407")

        call_kwargs = mock_store.get_chunks.call_args[1]
        where = call_kwargs["where"]
        assert "$and" in where
        assert {"peripheral": "SPI1"} in where["$and"]
        assert {"chip": "STM32F407"} in where["$and"]
        assert {"content_type": "register_description"} in where["$and"]

    def test_no_results(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_hw_registers

        mock_store.get_chunks.return_value = []

        output = handle_hw_registers(hwcc_ctx, peripheral="UNKNOWN")
        assert "no register" in output.lower()

    def test_store_error_returns_message(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_hw_registers

        mock_store.get_chunks.side_effect = StoreError("db error")

        output = handle_hw_registers(hwcc_ctx, peripheral="SPI1")
        assert "error" in output.lower()


# ---------------------------------------------------------------------------
# hw_context
# ---------------------------------------------------------------------------


class TestHwContext:
    def test_reads_precompiled_file(self, hwcc_ctx, project_root):
        from hwcc.serve.server import handle_hw_context

        periph_file = project_root / ".rag" / "context" / "peripherals" / "spi1.md"
        periph_file.write_text("# SPI1\nPre-compiled context for SPI1\n", encoding="utf-8")

        output = handle_hw_context(hwcc_ctx, peripheral="SPI1")
        assert "Pre-compiled context for SPI1" in output

    def test_falls_back_to_store(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_hw_context

        chunks = [
            _make_chunk("SPI1 register data from store", peripheral="SPI1"),
        ]
        mock_store.get_chunks.return_value = chunks

        output = handle_hw_context(hwcc_ctx, peripheral="SPI1")
        assert "SPI1 register data from store" in output

    def test_unknown_peripheral(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_hw_context

        mock_store.get_chunks.return_value = []

        output = handle_hw_context(hwcc_ctx, peripheral="UNKNOWN_PERIPH")
        assert "no context" in output.lower() or "not found" in output.lower()

    def test_with_chip_filter_builds_and_clause(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_hw_context

        mock_store.get_chunks.return_value = []

        handle_hw_context(hwcc_ctx, peripheral="SPI1", chip="STM32F407")

        call_kwargs = mock_store.get_chunks.call_args[1]
        where = call_kwargs["where"]
        assert "$and" in where

    def test_rejects_path_traversal(self, hwcc_ctx):
        from hwcc.serve.server import handle_hw_context

        output = handle_hw_context(hwcc_ctx, peripheral="../../etc/passwd")
        assert "invalid" in output.lower()

    def test_rejects_slashes(self, hwcc_ctx):
        from hwcc.serve.server import handle_hw_context

        output = handle_hw_context(hwcc_ctx, peripheral="foo/bar")
        assert "invalid" in output.lower()

    def test_store_error_returns_message(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_hw_context

        mock_store.get_chunks.side_effect = StoreError("db error")

        output = handle_hw_context(hwcc_ctx, peripheral="TIM1")
        assert "error" in output.lower()


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


class TestResources:
    def test_peripherals_resource(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_list_peripherals

        mock_store.get_chunk_metadata.return_value = [
            ChunkMetadata(doc_id="stm32", chip="STM32F407", peripheral="SPI1"),
            ChunkMetadata(doc_id="stm32", chip="STM32F407", peripheral="SPI1"),
            ChunkMetadata(doc_id="stm32", chip="STM32F407", peripheral="USART1"),
            ChunkMetadata(doc_id="stm32", chip="STM32F407", peripheral="I2C1"),
        ]

        output = handle_list_peripherals(hwcc_ctx)
        assert "SPI1" in output
        assert "USART1" in output
        assert "I2C1" in output

    def test_peripherals_empty_store(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_list_peripherals

        mock_store.get_chunk_metadata.return_value = []

        output = handle_list_peripherals(hwcc_ctx)
        assert "no peripherals" in output.lower()

    def test_peripherals_store_error(self, hwcc_ctx, mock_store):
        from hwcc.serve.server import handle_list_peripherals

        mock_store.get_chunk_metadata.side_effect = StoreError("db error")

        output = handle_list_peripherals(hwcc_ctx)
        assert "error" in output.lower()

    def test_documents_resource(self, hwcc_ctx):
        from hwcc.serve.server import handle_list_documents

        output = handle_list_documents(hwcc_ctx)
        assert "stm32f407_svd" in output or "STM32F407.svd" in output
        assert "rm0090_pdf" in output or "RM0090.pdf" in output

    def test_documents_empty_manifest(self):
        from pathlib import Path

        from hwcc.serve.server import HwccContext, handle_list_documents

        empty_manifest = Manifest()
        ctx = HwccContext(
            store=MagicMock(),
            search_engine=MagicMock(),
            project_root=Path("/tmp"),
            manifest=empty_manifest,
        )
        output = handle_list_documents(ctx)
        assert "no documents" in output.lower()


# ---------------------------------------------------------------------------
# HwccContext
# ---------------------------------------------------------------------------


class TestHwccContext:
    def test_is_frozen(self, hwcc_ctx):
        with pytest.raises(AttributeError):
            hwcc_ctx.manifest = Manifest()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Server creation
# ---------------------------------------------------------------------------


class TestServerCreation:
    def test_create_server_returns_fastmcp(self):
        from hwcc.serve.server import create_server

        server = create_server()
        assert server.name == "hwcc"

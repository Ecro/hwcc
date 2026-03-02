"""Tests for the SVD catalog module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from hwcc.catalog import CatalogEntry, CatalogIndex, download_svd
from hwcc.exceptions import CatalogError

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_SAMPLE_CATALOG = {
    "version": 1,
    "source": "cmsis-svd/cmsis-svd-data",
    "device_count": 5,
    "devices": [
        {"name": "STM32F407", "vendor": "STMicro", "path": "STMicro/STM32F407.svd"},
        {"name": "STM32F411xE", "vendor": "STMicro", "path": "STMicro/STM32F411xE.svd"},
        {"name": "STM32L476", "vendor": "STMicro", "path": "STMicro/STM32L476.svd"},
        {"name": "nRF52840", "vendor": "Nordic", "path": "Nordic/nRF52840.svd"},
        {
            "name": "EFM32G210F128",
            "vendor": "SiliconLabs",
            "path": "SiliconLabs/Series0/EFM32G/EFM32G210F128.svd",
        },
    ],
}


@pytest.fixture
def catalog() -> CatalogIndex:
    """Create a CatalogIndex from sample data."""
    return CatalogIndex.from_dict(_SAMPLE_CATALOG)


# ---------------------------------------------------------------------------
# Tests: CatalogEntry
# ---------------------------------------------------------------------------


class TestCatalogEntry:
    """Tests for CatalogEntry data structure."""

    def test_fields(self) -> None:
        entry = CatalogEntry(name="STM32F407", vendor="STMicro", path="STMicro/STM32F407.svd")
        assert entry.name == "STM32F407"
        assert entry.vendor == "STMicro"
        assert entry.path == "STMicro/STM32F407.svd"

    def test_frozen(self) -> None:
        entry = CatalogEntry(name="STM32F407", vendor="STMicro", path="STMicro/STM32F407.svd")
        with pytest.raises(AttributeError):
            entry.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: CatalogIndex loading
# ---------------------------------------------------------------------------


class TestCatalogIndexLoad:
    """Tests for index loading and structure."""

    def test_load_bundled_index(self) -> None:
        """The bundled catalog index should load without errors."""
        catalog = CatalogIndex.load()
        assert catalog.device_count > 0
        assert catalog.version == 1

    def test_from_dict(self, catalog: CatalogIndex) -> None:
        assert catalog.device_count == 5
        assert catalog.version == 1

    def test_load_failure_raises_catalog_error(self) -> None:
        with patch("hwcc.catalog.resources.files") as mock_files:
            mock_files.side_effect = FileNotFoundError("not found")
            with pytest.raises(CatalogError, match="Failed to load"):
                CatalogIndex.load()


# ---------------------------------------------------------------------------
# Tests: Search
# ---------------------------------------------------------------------------


class TestCatalogSearch:
    """Tests for device search."""

    def test_search_exact_name_case_insensitive(self, catalog: CatalogIndex) -> None:
        results = catalog.search("stm32f407")
        assert len(results) == 1
        assert results[0].name == "STM32F407"

    def test_search_partial_name(self, catalog: CatalogIndex) -> None:
        results = catalog.search("STM32")
        assert len(results) == 3  # STM32F407, STM32F411xE, STM32L476

    def test_search_with_vendor_filter(self, catalog: CatalogIndex) -> None:
        results = catalog.search("", vendor="STMicro")
        assert len(results) == 3
        assert all(r.vendor == "STMicro" for r in results)

    def test_search_with_vendor_and_query(self, catalog: CatalogIndex) -> None:
        results = catalog.search("STM32F4", vendor="STMicro")
        assert len(results) == 2  # STM32F407, STM32F411xE

    def test_search_no_results(self, catalog: CatalogIndex) -> None:
        results = catalog.search("NONEXISTENT")
        assert results == []

    def test_search_vendor_case_insensitive(self, catalog: CatalogIndex) -> None:
        results = catalog.search("", vendor="stmicro")
        assert len(results) == 3

    def test_find_exact(self, catalog: CatalogIndex) -> None:
        entry = catalog.find_exact("STM32F407")
        assert entry is not None
        assert entry.name == "STM32F407"
        assert entry.vendor == "STMicro"

    def test_find_exact_case_insensitive(self, catalog: CatalogIndex) -> None:
        entry = catalog.find_exact("stm32f407")
        assert entry is not None
        assert entry.name == "STM32F407"

    def test_find_exact_not_found(self, catalog: CatalogIndex) -> None:
        entry = catalog.find_exact("NONEXISTENT")
        assert entry is None


# ---------------------------------------------------------------------------
# Tests: Vendor listing
# ---------------------------------------------------------------------------


class TestCatalogVendors:
    """Tests for vendor listing."""

    def test_vendors_with_counts(self, catalog: CatalogIndex) -> None:
        vendors = catalog.vendors()
        assert len(vendors) == 3
        # Sorted alphabetically
        names = [v[0] for v in vendors]
        assert names == ["Nordic", "STMicro", "SiliconLabs"]

    def test_vendor_counts_correct(self, catalog: CatalogIndex) -> None:
        vendors = dict(catalog.vendors())
        assert vendors["STMicro"] == 3
        assert vendors["Nordic"] == 1
        assert vendors["SiliconLabs"] == 1


# ---------------------------------------------------------------------------
# Tests: Download
# ---------------------------------------------------------------------------


class TestDownloadSvd:
    """Tests for SVD file download."""

    def test_download_success(self, tmp_path: Path) -> None:
        """Mocked download should write file to dest."""
        entry = CatalogEntry(
            name="STM32F407",
            vendor="STMicro",
            path="STMicro/STM32F407.svd",
        )

        mock_content = b'<?xml version="1.0"?><device><name>STM32F407</name></device>'

        with patch("hwcc.catalog.urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.read.return_value = mock_content

            result = download_svd(entry, tmp_path)

        assert result.name == "STM32F407.svd"
        assert result.exists()
        assert result.read_bytes() == mock_content

    def test_download_network_error(self, tmp_path: Path) -> None:
        """Network failure should raise CatalogError."""
        import urllib.error

        entry = CatalogEntry(
            name="STM32F407",
            vendor="STMicro",
            path="STMicro/STM32F407.svd",
        )

        with patch("hwcc.catalog.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("connection refused")

            with pytest.raises(CatalogError, match="Failed to download"):
                download_svd(entry, tmp_path)

    def test_download_timeout(self, tmp_path: Path) -> None:
        """Timeout should raise CatalogError."""
        entry = CatalogEntry(
            name="STM32F407",
            vendor="STMicro",
            path="STMicro/STM32F407.svd",
        )

        with patch("hwcc.catalog.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("timed out")

            with pytest.raises(CatalogError, match="timed out"):
                download_svd(entry, tmp_path)

    def test_download_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Paths with traversal components should be rejected."""
        entry = CatalogEntry(
            name="evil",
            vendor="Evil",
            path="../../etc/passwd",
        )

        with pytest.raises(CatalogError, match="Invalid catalog path"):
            download_svd(entry, tmp_path)

    def test_download_nested_path(self, tmp_path: Path) -> None:
        """Download with nested path extracts correct filename."""
        entry = CatalogEntry(
            name="EFM32G210F128",
            vendor="SiliconLabs",
            path="SiliconLabs/Series0/EFM32G/EFM32G210F128.svd",
        )

        with patch("hwcc.catalog.urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.read.return_value = b"<svd/>"

            result = download_svd(entry, tmp_path)

        assert result.name == "EFM32G210F128.svd"


# ---------------------------------------------------------------------------
# Tests: Bundled index content
# ---------------------------------------------------------------------------


class TestBundledIndex:
    """Smoke tests for the actual bundled catalog index."""

    def test_has_stmicro_devices(self) -> None:
        catalog = CatalogIndex.load()
        results = catalog.search("STM32", vendor="STMicro")
        assert len(results) > 50

    def test_has_nordic_devices(self) -> None:
        catalog = CatalogIndex.load()
        results = catalog.search("nRF")
        assert len(results) > 5

    def test_has_multiple_vendors(self) -> None:
        catalog = CatalogIndex.load()
        vendors = catalog.vendors()
        assert len(vendors) >= 20

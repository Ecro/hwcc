"""SVD device catalog — browse and download from cmsis-svd-data.

Provides a searchable index of 1,900+ SVD files from the cmsis-svd-data
GitHub repository.  The index is bundled as a static JSON file and loaded
at runtime.  Individual SVD files are downloaded on demand.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib import resources
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from hwcc.exceptions import CatalogError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["CatalogEntry", "CatalogIndex", "download_svd"]

logger = logging.getLogger(__name__)

_GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/cmsis-svd/cmsis-svd-data/main/data"
)
_DOWNLOAD_TIMEOUT = 30
_INDEX_RESOURCE = "svd_catalog.json"


@dataclass(frozen=True)
class CatalogEntry:
    """A single device in the SVD catalog."""

    name: str
    vendor: str
    path: str  # relative to data/ in cmsis-svd-data repo


class CatalogIndex:
    """SVD device catalog backed by a bundled JSON index.

    The index maps device names to vendor and download paths.  It is
    generated at development time from the cmsis-svd-data GitHub
    repository and shipped with the hwcc package.
    """

    def __init__(self, entries: list[CatalogEntry], version: int = 1) -> None:
        self._entries = entries
        self._version = version

    @classmethod
    def load(cls) -> CatalogIndex:
        """Load the bundled catalog index.

        Returns:
            A CatalogIndex instance with all devices.

        Raises:
            CatalogError: If the index file cannot be loaded.
        """
        try:
            ref = resources.files("hwcc.data").joinpath(_INDEX_RESOURCE)
            data = json.loads(ref.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, TypeError, OSError) as e:
            raise CatalogError(f"Failed to load SVD catalog index: {e}") from e

        entries = [
            CatalogEntry(
                name=d["name"],
                vendor=d["vendor"],
                path=d["path"],
            )
            for d in data.get("devices", [])
        ]
        return cls(entries, version=data.get("version", 1))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogIndex:
        """Create a CatalogIndex from a raw dictionary (for testing)."""
        entries = [
            CatalogEntry(name=d["name"], vendor=d["vendor"], path=d["path"])
            for d in data.get("devices", [])
        ]
        return cls(entries, version=data.get("version", 1))

    def search(self, query: str, vendor: str = "") -> list[CatalogEntry]:
        """Case-insensitive substring search on device name.

        Args:
            query: Search string to match against device names.
            vendor: Optional vendor filter (case-insensitive exact match).

        Returns:
            Matching entries sorted by vendor then name.
        """
        q = query.lower()
        v = vendor.lower()
        results = [
            e for e in self._entries
            if q in e.name.lower()
            and (not v or e.vendor.lower() == v)
        ]
        results.sort(key=lambda e: (e.vendor, e.name))
        return results

    def find_exact(self, name: str) -> CatalogEntry | None:
        """Find a device by exact name match (case-insensitive).

        Args:
            name: Device name to match exactly.

        Returns:
            The matching entry, or None.
        """
        needle = name.lower()
        for e in self._entries:
            if e.name.lower() == needle:
                return e
        return None

    def vendors(self) -> list[tuple[str, int]]:
        """List vendors with device counts, sorted by name.

        Returns:
            List of (vendor_name, device_count) tuples.
        """
        counts: dict[str, int] = {}
        for e in self._entries:
            counts[e.vendor] = counts.get(e.vendor, 0) + 1
        return sorted(counts.items())

    @property
    def device_count(self) -> int:
        """Total number of devices in the catalog."""
        return len(self._entries)

    @property
    def version(self) -> int:
        """Index format version."""
        return self._version


def download_svd(entry: CatalogEntry, dest: Path) -> Path:
    """Download an SVD file from the cmsis-svd-data GitHub repository.

    Args:
        entry: Catalog entry describing the device.
        dest: Directory to save the file to.

    Returns:
        Path to the downloaded SVD file.

    Raises:
        CatalogError: If the download fails.
    """
    # Validate path has no traversal components
    parts = PurePosixPath(entry.path).parts
    if any(p in (".", "..") for p in parts):
        raise CatalogError(f"Invalid catalog path: {entry.path}")

    filename = parts[-1]
    url = f"{_GITHUB_RAW_BASE}/{entry.path}"
    output_path = dest / filename

    logger.info("Downloading %s from %s", filename, url)

    req = urllib.request.Request(url, headers={"User-Agent": "hwcc-catalog"})
    try:
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
            content = resp.read()
    except urllib.error.URLError as e:
        raise CatalogError(f"Failed to download {entry.name}: {e}") from e
    except TimeoutError as e:
        raise CatalogError(f"Download timed out for {entry.name}") from e

    try:
        output_path.write_bytes(content)
    except OSError as e:
        raise CatalogError(f"Failed to save {filename}: {e}") from e

    logger.info("Downloaded %s (%d bytes)", filename, len(content))
    return output_path

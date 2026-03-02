#!/usr/bin/env python3
"""Generate SVD catalog index from the cmsis-svd-data GitHub repository.

Development-time script — NOT part of the user-facing tool.

Usage:
    python scripts/generate_svd_catalog.py

Writes to: src/hwcc/data/svd_catalog.json
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path, PurePosixPath

_REPO = "cmsis-svd/cmsis-svd-data"
_API_URL = f"https://api.github.com/repos/{_REPO}/git/trees/main?recursive=1"
_OUTPUT = Path(__file__).resolve().parent.parent / "src" / "hwcc" / "data" / "svd_catalog.json"


def _fetch_tree() -> dict:
    """Fetch the full repository tree from GitHub API."""
    req = urllib.request.Request(
        _API_URL,
        headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "hwcc-catalog-gen"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    if data.get("truncated"):
        print("WARNING: GitHub tree response was truncated. Some files may be missing.", file=sys.stderr)
    return data


def _extract_devices(tree: dict) -> list[dict[str, str]]:
    """Extract SVD device entries from the GitHub tree response."""
    devices: list[dict[str, str]] = []

    for item in tree.get("tree", []):
        if item["type"] != "blob":
            continue
        path = item["path"]
        if not path.startswith("data/") or not path.endswith(".svd"):
            continue

        # path is like "data/STMicro/STM32F407.svd"
        # or "data/SiliconLabs/Series0/EFM32G/EFM32G210F128.svd"
        rel_path = path.removeprefix("data/")
        parts = PurePosixPath(rel_path).parts

        if len(parts) < 2:
            continue

        vendor = parts[0]
        name = PurePosixPath(parts[-1]).stem  # filename without .svd

        devices.append({
            "name": name,
            "vendor": vendor,
            "path": rel_path,
        })

    devices.sort(key=lambda d: (d["vendor"], d["name"]))
    return devices


def main() -> None:
    """Generate the SVD catalog index."""
    print(f"Fetching repository tree from {_REPO}...")
    tree = _fetch_tree()

    devices = _extract_devices(tree)
    print(f"Found {len(devices)} SVD files across {len({d['vendor'] for d in devices})} vendors")

    # Count per vendor
    vendor_counts: dict[str, int] = {}
    for d in devices:
        vendor_counts[d["vendor"]] = vendor_counts.get(d["vendor"], 0) + 1

    for vendor, count in sorted(vendor_counts.items()):
        print(f"  {vendor}: {count}")

    catalog = {
        "version": 1,
        "source": _REPO,
        "device_count": len(devices),
        "devices": devices,
    }

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote catalog to {_OUTPUT}")
    print(f"File size: {_OUTPUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()

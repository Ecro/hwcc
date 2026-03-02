# Plan: Task 1.13 — SVD Catalog

## Scope Declaration
- **Type:** feature
- **Single Concern:** Add `hwcc catalog` CLI commands to list/search/add SVD files from the cmsis-svd-data GitHub repository
- **Phase:** v0.2 (Quality & Search)
- **Complexity:** Medium
- **Risk:** Low (additive feature, no existing code modified)

## Problem Statement
**What:** Users must manually find and download SVD files before `hwcc add`. The cmsis-svd-data repository has 1,900+ SVD files across 25 vendors. A built-in catalog enables zero-config SVD setup.

**Why:** Reduces friction from "find SVD file → download → hwcc add" to just "hwcc catalog add STM32F407". The Embedder research reference calls this out as a key UX improvement.

**Success:** `hwcc catalog list stm32f4` shows matching devices. `hwcc catalog add STM32F407` downloads the SVD and processes it through the existing pipeline.

---

## Design

### Data Source
The `cmsis-svd/cmsis-svd-data` GitHub repository (`https://github.com/cmsis-svd/cmsis-svd-data`).

Since cmsis-svd v0.5+, the Python package no longer bundles SVD data files. The data lives in this separate repository with structure:
```
data/{Vendor}/{Device}.svd          (most vendors: flat)
data/SiliconLabs/Series0/{Family}/{Device}.svd  (nested)
```

### Strategy: Bundled Index + On-Demand Download

1. **Static JSON index** bundled with the hwcc package (~30KB for 1,900 entries)
2. **Listing/search** reads the bundled index (instant, offline)
3. **Download** fetches individual SVD files from GitHub raw URLs (one file at a time)
4. **Processing** feeds downloaded SVD into existing `Pipeline.process()` flow

Download URL pattern:
```
https://raw.githubusercontent.com/cmsis-svd/cmsis-svd-data/main/data/{path}
```

### Index Format

```json
{
  "version": 1,
  "source": "cmsis-svd/cmsis-svd-data",
  "commit": "abc123",
  "device_count": 1928,
  "devices": [
    {"name": "STM32F407", "vendor": "STMicro", "path": "STMicro/STM32F407.svd"},
    {"name": "EFM32G210F128", "vendor": "SiliconLabs", "path": "SiliconLabs/Series0/EFM32G/EFM32G210F128.svd"}
  ]
}
```

The `path` field is relative to `data/` in the repo, used to construct download URLs.
The `name` is derived from the filename (stem without `.svd`).

### CLI Commands

```
hwcc catalog list                     → Show vendor summary (25 vendors, counts)
hwcc catalog list stm32f4             → Search devices matching "stm32f4" (case-insensitive)
hwcc catalog list --vendor STMicro    → List all STMicro devices
hwcc catalog add STM32F407            → Download + add to project (auto-compile)
hwcc catalog add STM32F407 --no-compile → Download + add, skip auto-compile
```

### Search Algorithm

Case-insensitive substring match on device name. When `--vendor` is provided, filter by vendor first. Results sorted alphabetically, displayed in a Rich table grouped by vendor.

### `catalog add` Flow

1. Search index for exact match (case-insensitive)
2. If no exact match, try prefix match → if single result, use it; if multiple, show list and ask user to be more specific
3. Download SVD from GitHub raw to a temp file
4. Reuse existing `hwcc add` pipeline logic:
   - `detect_file_type()` → `get_parser()` → `Pipeline.process()`
   - Update manifest, auto-compile
5. Clean up temp file

### Index Generation

A development-time script (`scripts/generate_svd_catalog.py`) that:
1. Uses the GitHub API recursive tree endpoint to enumerate all `.svd` files
2. Extracts vendor and device name from paths
3. Writes `src/hwcc/data/svd_catalog.json`

This script is NOT part of the user-facing tool. It runs during hwcc development to refresh the bundled index.

---

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Create index generator script | `scripts/generate_svd_catalog.py` | GitHub API tree scan → JSON index |
| 2 | Generate and bundle the index | `src/hwcc/data/svd_catalog.json`, `pyproject.toml` | Run script, configure package data |
| 3 | Create catalog module | `src/hwcc/catalog.py` | `CatalogIndex` class: load, search, download |
| 4 | Add CatalogError | `src/hwcc/exceptions.py` | New exception class |
| 5 | Add CLI commands | `src/hwcc/cli.py` | `catalog` sub-app with `list` and `add` |
| 6 | Write tests | `tests/test_catalog.py` | Unit tests for index loading, search, download |
| 7 | Verify | — | Full test suite, lint, types |

### Step 3 Detail: `src/hwcc/catalog.py`

```python
class CatalogEntry:
    """A single device in the SVD catalog."""
    name: str       # e.g. "STM32F407"
    vendor: str     # e.g. "STMicro"
    path: str       # e.g. "STMicro/STM32F407.svd"

class CatalogIndex:
    """SVD device catalog backed by bundled JSON index."""

    @classmethod
    def load(cls) -> CatalogIndex:
        """Load the bundled catalog index."""

    def search(self, query: str, vendor: str = "") -> list[CatalogEntry]:
        """Case-insensitive substring search on device name."""

    def vendors(self) -> list[tuple[str, int]]:
        """List vendors with device counts, sorted by name."""

    @property
    def device_count(self) -> int: ...

def download_svd(entry: CatalogEntry, dest: Path) -> Path:
    """Download an SVD file from GitHub to dest directory.
    Returns path to downloaded file.
    Raises CatalogError on network/IO failure."""
```

### Step 5 Detail: CLI `catalog add` integration

The `catalog add` command needs to run the same pipeline as `hwcc add`:
- Initialize `ProjectManager`, check `is_initialized`
- Load config, manifest
- Build pipeline components (chunker, embedder, store)
- Download SVD to temp file
- Process through pipeline
- Update manifest
- Auto-compile (unless `--no-compile`)

To avoid duplicating the `add()` command's logic, extract a `_process_file()` helper that both `add()` and `catalog add` can call. This helper takes `(pm, file_path, doc_type, chip, console)` and handles the parse→chunk→embed→store→manifest flow.

---

## Files to Create

| File | Purpose |
|------|---------|
| `src/hwcc/catalog.py` | Catalog index loading, search, download |
| `src/hwcc/data/__init__.py` | Package marker for data directory |
| `src/hwcc/data/svd_catalog.json` | Bundled device index (~30KB) |
| `scripts/generate_svd_catalog.py` | Dev script to regenerate index from GitHub |
| `tests/test_catalog.py` | Catalog unit tests |

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/cli.py` | modify | Add `catalog` sub-app, extract `_process_file()` helper |
| `src/hwcc/exceptions.py` | modify | Add `CatalogError` |
| `pyproject.toml` | modify | Add `[tool.setuptools.package-data]` for JSON index |

## NON-GOALS (Do NOT Touch)

- [ ] SVD parser changes — existing `SvdParser` is sufficient
- [ ] Embedding/store changes — reuse existing pipeline
- [ ] Compile changes — reuse existing auto-compile
- [ ] Config changes — no new config sections
- [ ] Template changes — catalog is ingest-side only
- [ ] `hwcc search` (task 3.6) — separate feature

---

## Test Plan

### Unit Tests

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Load bundled catalog index | `tests/test_catalog.py` | unit |
| 2 | Search by exact name (case-insensitive) | `tests/test_catalog.py` | unit |
| 3 | Search by partial name (substring) | `tests/test_catalog.py` | unit |
| 4 | Search with vendor filter | `tests/test_catalog.py` | unit |
| 5 | Search with no results returns empty | `tests/test_catalog.py` | unit |
| 6 | Vendor listing with counts | `tests/test_catalog.py` | unit |
| 7 | Download SVD file (mocked network) | `tests/test_catalog.py` | unit |
| 8 | Download failure raises CatalogError | `tests/test_catalog.py` | unit |
| 9 | CatalogEntry data structure | `tests/test_catalog.py` | unit |
| 10 | Index version field present | `tests/test_catalog.py` | unit |

### Manual Acceptance Criteria

| # | Scenario | Expected Result |
|---|----------|----------------|
| 1 | `hwcc catalog list` | Shows 25 vendors with device counts |
| 2 | `hwcc catalog list stm32f4` | Shows STM32F4xx devices |
| 3 | `hwcc catalog list --vendor Nordic` | Shows only Nordic devices |
| 4 | `hwcc catalog add STM32F407` (with project) | Downloads, indexes, auto-compiles |
| 5 | `hwcc catalog add NONEXISTENT` | Shows "no device found" error |

---

## Exit Criteria

```
□ hwcc catalog list shows vendor summary
□ hwcc catalog list <query> searches devices
□ hwcc catalog add <device> downloads and processes SVD
□ Bundled index loads without errors
□ All tests pass: pytest tests/
□ Lint passes: ruff check src/ tests/
□ Types correct: mypy src/hwcc/
□ No scope creep into NON-GOAL areas
```

## Document Updates Needed
- [ ] **TECH_SPEC.md:** Mark catalog command as [DONE]
- [ ] **PLAN.md:** Check off task 1.13

---

> **Last Updated:** 2026-03-02

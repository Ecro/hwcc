# Plan: Fix MCP Server Bugs for v0.3.0

## Scope Declaration
- **Type:** bugfix
- **Single Concern:** Fix 3 MCP server bugs (hw_registers, hw_context, resources) and bump version to 0.3.0
- **Phase:** v0.3 (MCP Server)
- **Complexity:** Medium
- **Risk:** Low (changes confined to `server.py`, tests, and version files)

## Problem Statement
**What:** Demo testing revealed 2/3 MCP tools and 2/2 resources are non-functional. `hw_registers` and `hw_context` return empty results. Both resources return "Unknown resource".

**Why:** These are the primary value propositions of the MCP server — if they don't work, v0.3 can't ship.

**Success:** All 3 tools and 2 resources return correct results when called via MCP JSON-RPC against a real indexed project.

---

## Root Cause Analysis

### Bug 1: `hw_registers` returns no results
- **Root cause:** `peripheral` metadata field is empty string (`""`) for ALL chunks in ChromaDB. The SVD chunker populates `section_path` (e.g., `"STM32F407 Register Map > SPI1 > Registers"`) but never sets `peripheral`.
- **Why tests passed:** Unit tests mock `store.get_chunks()` to return pre-built chunks — they never hit real ChromaDB with empty peripheral metadata.
- **Fix:** Filter chunks by `chip` + `doc_type=svd` + `content_type=register_description`, then post-filter in Python by parsing `section_path` (same approach the compile stage uses).

### Bug 2: `hw_context` file lookup fails
- **Root cause:** Code looks for `{periph_lower}.md` (e.g., `spi1.md`) but compiled files are named `{periph_lower}_{chip_lower}.md` (e.g., `spi1_stm32f407.md`) when multiple chips define the same peripheral.
- **Fix:** Try `{periph}_{chip}.md` first (when chip provided), then `{periph}.md`, then glob `{periph}_*.md`.
- **Store fallback** also fails (same empty peripheral metadata) — apply same section_path filtering fix.

### Bug 3: Resources return "Unknown resource"
- **Root cause:** FastMCP 1.26.0 **silently drops** resources whose function signature includes a `Context` parameter. Confirmed: only resources WITHOUT `ctx: Context` are registered.
- **Fix:** Remove `Context` parameter from resource functions. Use a mutable context holder (list) populated during lifespan, accessed by resource closures.

---

## Impact Analysis

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/serve/server.py` | modify | Fix all 3 bugs: section_path filtering, chip-suffixed file lookup, resource context pattern |
| `tests/test_serve_mcp.py` | modify | Update tests to cover section_path filtering, chip-suffixed files, and resource registration |
| `src/hwcc/__init__.py` | modify | Bump `__version__` to `"0.3.0"` |
| `pyproject.toml` | modify | Bump `version` to `"0.3.0"` |

### Dependency Chain

| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `handle_hw_registers()` | MCP `hw_registers` tool | `store.get_chunks()`, new `_peripheral_from_section_path()` |
| `handle_hw_context()` | MCP `hw_context` tool | `Path.read_text()`, `store.get_chunks()`, `glob()` |
| Resource functions | FastMCP resource dispatch | `handle_list_peripherals()`, `handle_list_documents()` |

### Pipeline Impact
None — all changes are in the serve layer. No modifications to ingest, chunk, embed, store, or compile.

## NON-GOALS (Do NOT Touch)

- [ ] `src/hwcc/ingest/` — Not populating `peripheral` metadata at ingest time (separate future improvement)
- [ ] `src/hwcc/chunk/` — Chunking logic unchanged
- [ ] `src/hwcc/compile/` — Compile logic unchanged (already works via section_path parsing)
- [ ] `src/hwcc/store/` — Store interface unchanged
- [ ] `src/hwcc/search.py` — Search engine unchanged
- [ ] `src/hwcc/cli.py` — CLI unchanged

---

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Add `_peripheral_from_section_path()` helper | `server.py` | Extract peripheral name from section_path (split on `" > "`, take element [1]) |
| 2 | Fix `handle_hw_registers()` | `server.py` | Get chunks by chip+doc_type+content_type only, then post-filter by section_path peripheral match |
| 3 | Fix `handle_hw_context()` file lookup | `server.py` | Try `{periph}_{chip}.md`, then `{periph}.md`, then glob `{periph}_*.md` |
| 4 | Fix `handle_hw_context()` store fallback | `server.py` | Same section_path filtering as hw_registers |
| 5 | Fix resource registration | `server.py` | Remove Context param from resource functions; use `_ctx_holder` list populated during lifespan |
| 6 | Fix `handle_list_peripherals()` | `server.py` | Parse section_path to extract peripheral names (don't rely on empty `peripheral` metadata) |
| 7 | Update tests | `test_serve_mcp.py` | Cover section_path filtering, chip-suffixed files, resource registration |
| 8 | Bump version | `__init__.py`, `pyproject.toml` | `0.2.0` → `0.3.0` |
| 9 | Verify | — | Full test suite, lint, types, manual MCP test |

---

## Detailed Design

### Helper: `_peripheral_from_section_path()`

```python
def _peripheral_from_section_path(section_path: str) -> str:
    """Extract peripheral name from SVD section_path.

    SVD paths follow: "DeviceName Register Map > PeripheralName [> SubSection]"
    Returns peripheral name or empty string if not parseable.
    """
    parts = section_path.split(" > ")
    if len(parts) >= 2:
        return parts[1].strip()
    return ""
```

### Fix: `handle_hw_registers()`

Replace metadata-based peripheral filter with section_path post-filtering:

```python
def handle_hw_registers(ctx, peripheral, register="", chip=""):
    # Build where WITHOUT peripheral (it's always empty in metadata)
    where = build_where(chip=chip, doc_type="svd", content_type="register_description")
    chunks = ctx.store.get_chunks(where=where)

    # Post-filter by peripheral via section_path
    periph_upper = peripheral.upper()
    chunks = [c for c in chunks
              if _peripheral_from_section_path(c.metadata.section_path).upper() == periph_upper]

    # ... rest unchanged
```

### Fix: `handle_hw_context()` file lookup

```python
def handle_hw_context(ctx, peripheral, chip=""):
    periph_lower = peripheral.lower()
    periph_dir = ctx.project_root / RAG_DIR / "context" / "peripherals"

    # Try chip-specific file first, then generic, then glob
    candidates = []
    if chip:
        candidates.append(periph_dir / f"{periph_lower}_{chip.lower()}.md")
    candidates.append(periph_dir / f"{periph_lower}.md")

    for candidate in candidates:
        if candidate.is_file() and candidate.resolve().is_relative_to(periph_dir.resolve()):
            return candidate.read_text(encoding="utf-8")

    # Glob fallback: {periph}_*.md (pick first match)
    matches = sorted(periph_dir.glob(f"{periph_lower}_*.md"))
    # Filter for safety
    matches = [m for m in matches if m.resolve().is_relative_to(periph_dir.resolve())]
    if matches:
        return matches[0].read_text(encoding="utf-8")

    # Store fallback with section_path filtering
    ...
```

### Fix: Resource registration

```python
def create_server(project_root=None):
    _ctx_holder: list[HwccContext] = []

    @asynccontextmanager
    async def _hwcc_lifespan(server):
        ...
        ctx = HwccContext(...)
        _ctx_holder.append(ctx)
        try:
            yield ctx
        finally:
            _ctx_holder.clear()

    mcp = FastMCP("hwcc", lifespan=_hwcc_lifespan)

    # Resources — NO Context parameter (FastMCP 1.26 silently drops them)
    @mcp.resource("hw://peripherals")
    def peripherals() -> str:
        """List all indexed peripherals."""
        if not _ctx_holder:
            return "Server not initialized."
        return handle_list_peripherals(_ctx_holder[0])

    @mcp.resource("hw://documents")
    def documents() -> str:
        """List all indexed documents."""
        if not _ctx_holder:
            return "Server not initialized."
        return handle_list_documents(_ctx_holder[0])
```

### Fix: `handle_list_peripherals()` section_path parsing

```python
def handle_list_peripherals(ctx):
    # Get all SVD chunks metadata
    metadata_list = ctx.store.get_chunk_metadata(where={"doc_type": "svd"})

    peripherals: dict[str, set[str]] = {}
    for meta in metadata_list:
        # Extract peripheral from section_path instead of metadata field
        periph_name = _peripheral_from_section_path(meta.section_path)
        if periph_name:
            peripherals.setdefault(periph_name, set())
            if meta.chip:
                peripherals[periph_name].add(meta.chip)
    ...
```

---

## Test Plan

### Unit Tests

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `_peripheral_from_section_path` extracts peripheral name correctly | `test_serve_mcp.py` | unit |
| 2 | `_peripheral_from_section_path` returns "" for invalid paths | `test_serve_mcp.py` | unit |
| 3 | `hw_registers` filters by section_path (not peripheral metadata) | `test_serve_mcp.py` | unit |
| 4 | `hw_context` finds chip-suffixed file (`spi1_stm32f407.md`) | `test_serve_mcp.py` | unit |
| 5 | `hw_context` falls back to glob when chip not provided | `test_serve_mcp.py` | unit |
| 6 | `hw_context` store fallback uses section_path filtering | `test_serve_mcp.py` | unit |
| 7 | Resources register without Context parameter | `test_serve_mcp.py` | unit |
| 8 | `handle_list_peripherals` extracts from section_path | `test_serve_mcp.py` | unit |

### Acceptance Criteria (Testable)

| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | `hw_registers("SPI1", chip="STM32F407")` via MCP | Returns SPI1 register map | manual |
| 2 | `hw_context("spi1", chip="STM32F407")` via MCP | Returns pre-compiled SPI1 context | manual |
| 3 | `hw_context("spi1")` via MCP (no chip) | Returns first matching `spi1_*.md` | manual |
| 4 | `resources/list` via MCP | Returns 2 resources | manual |
| 5 | `resources/read hw://peripherals` via MCP | Returns peripheral list | manual |
| 6 | `resources/read hw://documents` via MCP | Returns document list | manual |

---

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/serve/server.py` | modify | Fix all 3 bugs |
| `tests/test_serve_mcp.py` | modify | Update and add tests |
| `src/hwcc/__init__.py` | modify | Version bump 0.2.0 → 0.3.0 |
| `pyproject.toml` | modify | Version bump 0.2.0 → 0.3.0 |

## Files to Create

None.

## Exit Criteria
```
□ hw_registers returns register data for real indexed peripherals
□ hw_context returns pre-compiled context files (chip-suffixed)
□ hw_context store fallback works via section_path filtering
□ hw://peripherals resource lists all indexed peripherals
□ hw://documents resource lists all indexed documents
□ All 1106+ tests pass
□ ruff + mypy clean
□ Version bumped to 0.3.0
□ Manual MCP test against ~/hwcc-demo passes
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] Manual MCP test: all 3 tools + 2 resources against ~/hwcc-demo
- [ ] No unintended side effects in: CLI, compile, store, embed modules

## Document Updates Needed
- [ ] **PLAN.md:** Already marks v0.3 as shipped — update after fixes
- [ ] **TECH_SPEC.md:** None needed

---

> **Last Updated:** 2026-03-02

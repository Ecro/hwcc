# Plan: Phase 2.2 — Peripheral Context Generator

## Scope Declaration

- **Type:** feature
- **Single Concern:** Implement `PeripheralContextCompiler` to generate per-peripheral context files from indexed SVD/datasheet/reference manual data
- **Phase:** Phase 2 (Context Compilation), task 2.2
- **Complexity:** Medium
- **Risk:** Low

## Problem Statement

**What:** Build a compiler that generates one `.rag/context/peripherals/<name>.md` file per peripheral, containing its complete register map, description, and (optionally) related content from other indexed documents.

**Why:** Per-peripheral context files are the core deliverable for AI coding tools — when an engineer writes an SPI driver, Claude/Codex/Cursor needs the SPI register map, not the entire chip context. This is the granular context that prevents hallucinated register addresses.

**Success:** Running the compiler produces a well-structured markdown file per peripheral in `.rag/context/peripherals/`, consumable by the existing `peripheral.md.j2` template.

## Impact Analysis

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/store/base.py` | modify | Add `get_chunks(where)` abstract method |
| `src/hwcc/store/chroma.py` | modify | Implement `get_chunks(where)` — returns `list[Chunk]` with content |
| `src/hwcc/compile/peripheral.py` | **create** | `PeripheralContextCompiler(BaseCompiler)` — main deliverable |
| `src/hwcc/compile/__init__.py` | modify | Export `PeripheralContextCompiler` |
| `tests/test_compile_peripheral.py` | **create** | Unit tests for peripheral compiler |
| `tests/test_compile_hot_context.py` | modify | Update `FakeStore` to implement new `get_chunks()` |

### Dependency Chain

| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `BaseStore.get_chunks()` | `PeripheralContextCompiler` | `ChromaStore._collection.get()` |
| `PeripheralContextCompiler.compile()` | Future `hwcc compile` CLI (task 2.5) | `BaseStore.get_chunks()`, `TemplateEngine.render()`, `CompileContext.from_config()` |

### Pipeline Impact

| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Store | New `get_chunks()` method (additive, no breaking changes) | Peripheral compiler consumes stored chunks |
| Compile | Depends on chunks being in the store (via `hwcc add`) | Peripheral files feed into output generators (task 2.4) and `hwcc context` (task 4.1) |

## NON-GOALS (Explicitly Out of Scope)

- [ ] **MarkdownChunker peripheral metadata** — The `peripheral` field in `ChunkMetadata` is never populated by the chunker. Fixing this is a separate concern (enhances _all_ peripheral queries but is not required for this compiler, which uses `section_path` instead).
- [ ] **Errata cross-referencing (Gap G4)** — Marked P2 in PLAN.md. The template already renders errata when present, but populating `ErrataSummary` from errata documents is a separate task.
- [ ] **`hwcc compile` CLI integration (task 2.5)** — This plan builds the compiler class only. CLI wiring is task 2.5.
- [ ] **Output file generators (task 2.4)** — CLAUDE.md/AGENTS.md generation is separate.
- [ ] **Cross-document enrichment via LLM** — Future enhancement. This plan uses deterministic section_path matching only.
- [ ] **Processed markdown files** — `.rag/processed/` is not currently written by the pipeline. Don't depend on it.

## Technical Approach

### Architecture Overview

```
Store (ChromaDB)
    │
    ├── get_chunks(where={"doc_type": "svd"})
    │       → all SVD chunks with content
    │
    └── get_chunks()  (no filter)
            → all chunks for cross-doc matching
    │
    ▼
PeripheralContextCompiler
    │
    ├── _discover_peripherals()
    │       Parse section_path from SVD chunks:
    │       "STM32F407 Register Map > SPI1 > Registers"
    │                                 ^^^^
    │       Extract unique peripheral names
    │
    ├── _extract_register_map(peripheral_name, svd_chunks)
    │       Filter chunks by section_path containing peripheral name
    │       Sort by chunk_id (preserves document order)
    │       Concatenate content → complete register map
    │
    ├── _gather_peripheral_details(peripheral_name, non_svd_chunks)
    │       Filter non-SVD chunks whose section_path mentions the peripheral
    │       Concatenate relevant content → peripheral details
    │
    └── _render_and_write(peripheral_name, register_map, details, config)
            Build CompileContext with peripheral_name, register_map, peripheral_details
            Render peripheral.md.j2
            Write to .rag/context/peripherals/<name_lower>.md
```

### Key Design Decision: section_path vs peripheral metadata

The `ChunkMetadata.peripheral` field is never populated by the current chunker. Rather than modifying the chunker (scope creep), the compiler extracts peripheral names from `section_path` which IS populated:

```
section_path: "STM32F407 Register Map > SPI1 > Registers"
                                        ^^^^
                                   peripheral name = 2nd element
```

SVD documents always follow the pattern: `"<Device> Register Map > <Peripheral> [> <SubSection>]"` because the SVD parser renders `# DeviceName Register Map` as H1 and `## PeripheralName` as H2, and the `_SectionTracker` builds the path accordingly.

### Option A: Store-based chunk retrieval (Recommended)

Retrieve all chunks from the store, group by peripheral name extracted from section_path, reconstruct register maps by concatenating chunks in order.

- **Pros:** Architecturally sound (store = single source of truth), works without processed files, consistent with `HotContextCompiler` pattern
- **Cons:** Must reassemble from chunks (minor — chunks split at heading boundaries which align with register/field boundaries)

### Option B: Processed file parsing (Rejected)

Read `.rag/processed/<doc_id>.md` and parse `## PeripheralName` sections.

- **Pros:** Complete un-chunked content, trivial parsing
- **Cons:** `.rag/processed/` is never written by the current pipeline — would depend on unimplemented feature

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Add `get_chunks()` to BaseStore | `src/hwcc/store/base.py` | New abstract method: `get_chunks(where) -> list[Chunk]` — returns chunks with content, not just metadata |
| 2 | Implement `get_chunks()` in ChromaStore | `src/hwcc/store/chroma.py` | Use `collection.get(where, include=["documents", "metadatas"])`, reconstruct `Chunk` objects |
| 3 | Update FakeStore in tests | `tests/test_compile_hot_context.py` | Add `get_chunks()` to `FakeStore` so existing tests don't break |
| 4 | Create PeripheralContextCompiler | `src/hwcc/compile/peripheral.py` | Main class with `compile()`, `_discover_peripherals()`, `_extract_register_map()`, `_gather_peripheral_details()` |
| 5 | Update compile `__init__.py` | `src/hwcc/compile/__init__.py` | Export `PeripheralContextCompiler` |
| 6 | Write unit tests | `tests/test_compile_peripheral.py` | Comprehensive tests covering all scenarios |
| 7 | Run full test suite | — | Verify no regressions, lint, type check |

### Step 1: Add `get_chunks()` to BaseStore

```python
# In base.py — new abstract method
@abstractmethod
def get_chunks(
    self,
    where: dict[str, str] | None = None,
) -> list[Chunk]:
    """Get chunks with content matching filters (no embedding needed).

    Unlike ``search()``, returns chunks by metadata filter without
    requiring a query embedding. Useful for the compile stage to
    retrieve document content by type, peripheral, etc.

    Args:
        where: Optional metadata filters (e.g., ``{"doc_type": "svd"}``).

    Returns:
        List of Chunk objects with content and metadata.

    Raises:
        StoreError: If the query fails.
    """
```

### Step 2: Implement `get_chunks()` in ChromaStore

```python
# In chroma.py
def get_chunks(
    self,
    where: dict[str, str] | None = None,
) -> list[Chunk]:
    try:
        results = self._collection.get(
            where=where,
            include=["documents", "metadatas"],
        )
    except Exception as e:
        raise StoreError(f"Failed to get chunks: {e}") from e

    ids = results.get("ids", [])
    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])

    chunks: list[Chunk] = []
    for chunk_id, doc, meta in zip(ids, documents or [], metadatas or [], strict=False):
        chunk_meta = self._meta_from_dict(meta)
        token_val = meta.get("token_count", 0) if meta else 0
        chunks.append(Chunk(
            chunk_id=chunk_id,
            content=doc or "",
            token_count=int(token_val) if token_val is not None else 0,
            metadata=chunk_meta,
        ))
    return chunks
```

### Step 4: PeripheralContextCompiler (core logic)

```python
class PeripheralContextCompiler(BaseCompiler):
    """Compiles .rag/context/peripherals/<name>.md per peripheral.

    Sources register maps from SVD chunks and optionally enriches
    with content from datasheet/reference manual chunks.
    """

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._rag_dir = project_root / ".rag"
        self._peripherals_dir = self._rag_dir / "context" / "peripherals"
        self._engine = TemplateEngine(project_root)

    def compile(self, store: BaseStore, config: HwccConfig) -> list[Path]:
        """Compile per-peripheral context files.

        1. Discover peripherals from SVD chunk section_paths
        2. For each peripheral, extract register map + details
        3. Render peripheral.md.j2 and write to output dir
        """
        self._peripherals_dir.mkdir(parents=True, exist_ok=True)

        # Get all chunks (SVD for register maps, others for enrichment)
        svd_chunks = store.get_chunks(where={"doc_type": "svd"})
        if not svd_chunks:
            logger.info("No SVD documents indexed, skipping peripheral compilation")
            return []

        # Discover peripherals from SVD section paths
        peripherals = self._discover_peripherals(svd_chunks)
        if not peripherals:
            logger.info("No peripherals found in SVD data")
            return []

        # Get non-SVD chunks for cross-document enrichment
        all_chunks = store.get_chunks()
        non_svd_chunks = [c for c in all_chunks if c.metadata.doc_type != "svd"]

        # Generate context file per peripheral
        base_context = CompileContext.from_config(config)
        output_paths: list[Path] = []

        for name, chip in peripherals:
            register_map = self._extract_register_map(name, svd_chunks)
            details = self._gather_peripheral_details(name, non_svd_chunks)

            ctx = replace(
                base_context,
                peripheral_name=name,
                register_map=register_map,
                peripheral_details=details,
            )

            content = self._engine.render("peripheral.md.j2", ctx)
            filename = f"{name.lower()}.md"
            output_path = self._peripherals_dir / filename
            output_path.write_text(content, encoding="utf-8")
            output_paths.append(output_path)

            logger.info("Compiled peripheral context: %s", filename)

        return output_paths

    def _discover_peripherals(self, svd_chunks: list[Chunk]) -> list[tuple[str, str]]:
        """Extract unique (peripheral_name, chip) pairs from SVD chunk section_paths.

        SVD section_paths follow: "DeviceName Register Map > PeripheralName [> SubSection]"
        The peripheral name is the 2nd element in the path.
        """
        seen: set[tuple[str, str]] = set()
        peripherals: list[tuple[str, str]] = []

        for chunk in svd_chunks:
            parts = chunk.metadata.section_path.split(" > ")
            if len(parts) >= 2:
                peripheral_name = parts[1].strip()
                chip = chunk.metadata.chip
                key = (peripheral_name, chip)
                if key not in seen:
                    seen.add(key)
                    peripherals.append(key)

        peripherals.sort(key=lambda p: p[0])
        return peripherals

    def _extract_register_map(self, peripheral_name: str, svd_chunks: list[Chunk]) -> str:
        """Extract register map content for a peripheral from SVD chunks.

        Filters chunks whose section_path contains the peripheral name,
        sorts by chunk_id (preserves document order), and concatenates.
        """
        relevant = [
            c for c in svd_chunks
            if self._chunk_belongs_to_peripheral(c, peripheral_name)
        ]
        relevant.sort(key=lambda c: c.chunk_id)
        return "\n\n".join(c.content for c in relevant).strip()

    def _gather_peripheral_details(self, peripheral_name: str, non_svd_chunks: list[Chunk]) -> str:
        """Gather additional details about a peripheral from non-SVD documents.

        Searches section_paths for mentions of the peripheral name.
        Limits to a reasonable number of chunks to avoid bloat.
        """
        MAX_DETAIL_CHUNKS = 5
        relevant = [
            c for c in non_svd_chunks
            if peripheral_name.lower() in c.metadata.section_path.lower()
        ]
        relevant.sort(key=lambda c: c.chunk_id)
        relevant = relevant[:MAX_DETAIL_CHUNKS]

        if not relevant:
            return ""

        return "\n\n---\n\n".join(c.content for c in relevant).strip()

    @staticmethod
    def _chunk_belongs_to_peripheral(chunk: Chunk, peripheral_name: str) -> bool:
        """Check if a chunk belongs to the given peripheral via section_path."""
        parts = chunk.metadata.section_path.split(" > ")
        return len(parts) >= 2 and parts[1].strip() == peripheral_name
```

## Test Plan

### Unit Tests

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Compile produces output files in `.rag/context/peripherals/` | `tests/test_compile_peripheral.py` | unit |
| 2 | Creates output directory if missing | `tests/test_compile_peripheral.py` | unit |
| 3 | Returns empty list when no SVD chunks in store | `tests/test_compile_peripheral.py` | unit |
| 4 | Discovers peripherals from SVD section_paths | `tests/test_compile_peripheral.py` | unit |
| 5 | Handles multi-chip peripheral deduplication | `tests/test_compile_peripheral.py` | unit |
| 6 | Extracts complete register map for a peripheral | `tests/test_compile_peripheral.py` | unit |
| 7 | Register map chunks are in document order | `tests/test_compile_peripheral.py` | unit |
| 8 | Output filename is lowercased peripheral name | `tests/test_compile_peripheral.py` | unit |
| 9 | Rendered output contains peripheral name and MCU | `tests/test_compile_peripheral.py` | unit |
| 10 | Rendered output contains register map content | `tests/test_compile_peripheral.py` | unit |
| 11 | Cross-document details included when section_path matches | `tests/test_compile_peripheral.py` | unit |
| 12 | Cross-document details limited to MAX_DETAIL_CHUNKS | `tests/test_compile_peripheral.py` | unit |
| 13 | Empty store produces no output (no crash) | `tests/test_compile_peripheral.py` | unit |
| 14 | Multiple peripherals generate multiple files | `tests/test_compile_peripheral.py` | unit |
| 15 | get_chunks() returns chunks with content from store | `tests/test_compile_peripheral.py` | unit |
| 16 | get_chunks() with where filter returns filtered results | `tests/test_compile_peripheral.py` | unit |
| 17 | Existing tests still pass with FakeStore.get_chunks() | `tests/test_compile_hot_context.py` | regression |

### Acceptance Criteria (Testable)

| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Store has SVD chunks for SPI1 and I2C1 | Two files created: `spi1.md`, `i2c1.md` | automated |
| 2 | SVD chunk with section_path `"STM32F407 Register Map > SPI1 > Registers"` | SPI1 register table appears in `spi1.md` | automated |
| 3 | No SVD documents indexed | `compile()` returns empty list, no files created | automated |
| 4 | Datasheet chunk with section_path containing "SPI1" | Content appears in `spi1.md` peripheral_details | automated |
| 5 | 10 datasheet chunks mention "UART" | Only first 5 appear in details (MAX_DETAIL_CHUNKS) | automated |

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/store/base.py` | modify | Add `get_chunks()` abstract method |
| `src/hwcc/store/chroma.py` | modify | Implement `get_chunks()` |
| `src/hwcc/compile/__init__.py` | modify | Add `PeripheralContextCompiler` to exports |
| `tests/test_compile_hot_context.py` | modify | Add `get_chunks()` to `FakeStore` |

## Files to Create

| File | Purpose |
|------|---------|
| `src/hwcc/compile/peripheral.py` | `PeripheralContextCompiler` class |
| `tests/test_compile_peripheral.py` | Unit tests for peripheral compiler |

## Exit Criteria

```
□ PeripheralContextCompiler.compile() generates per-peripheral .md files
□ Register maps extracted correctly from SVD chunks
□ Cross-document details gathered from non-SVD chunks via section_path matching
□ peripheral.md.j2 template renders correctly with populated CompileContext
□ Empty store and no-SVD-data edge cases handled gracefully
□ All 17+ unit tests pass
□ All existing tests still pass (no regressions from get_chunks() addition)
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched
```

## Verification Strategy

- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No unintended side effects in: chunker, hot context compiler, CLI, templates

## Document Updates Needed

- [ ] **TECH_SPEC.md:** None (peripheral context described in §4, §6.1 already)
- [ ] **PLAN.md:** Mark task 2.2 as `[x]` after implementation complete

---

> **Last Updated:** 2026-02-28

# Plan: Phase 2, Task 2.1 — Hot Context Generator

## Scope Declaration

### Change Intent
- **Type:** feature
- **Single Concern:** Compile `.rag/context/hot.md` from manifest + store + config data

### Concern Separation Rule
This change is ONLY about: generating the hot context markdown file from indexed data
This change is NOT about:
- Peripheral context files (task 2.2)
- Output file injection into CLAUDE.md/AGENTS.md (task 2.4)
- CLI `hwcc compile` command (task 2.5)
- Auto-compile on `hwcc add` (task 2.6)
- Errata parsing/extraction (task 2.2 concern — we handle errata if present, don't parse it)

---

## Problem Statement

**What:** Create `HotContextCompiler` — a `BaseCompiler` implementation that gathers data from the manifest, vector store metadata, and project config, builds a `CompileContext`, renders `hot_context.md.j2`, and writes the result to `.rag/context/hot.md` within the configured line budget.

**Why:** The hot context file is the primary output of the compile stage — it's what gets embedded into CLAUDE.md, AGENTS.md, etc. by task 2.4. Without it, there's no hardware context for AI tools to consume.

**Success:** Running `HotContextCompiler.compile(store, config)` produces a valid `.rag/context/hot.md` that:
- Contains hardware/software/convention data from config
- Lists all indexed documents from manifest
- Lists peripherals extracted from store metadata
- Respects `hot_context_max_lines` (default 120)
- Handles empty projects gracefully (no documents, no store)

---

## Impact Analysis

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|-------------|
| `src/hwcc/store/base.py` | modify | Add `get_chunk_metadata()` abstract method |
| `src/hwcc/store/chroma.py` | modify | Implement `get_chunk_metadata()` |
| `src/hwcc/compile/hot_context.py` | create | `HotContextCompiler` class |
| `src/hwcc/compile/__init__.py` | modify | Export `HotContextCompiler` |
| `tests/test_compile_hot_context.py` | create | Tests for hot context compiler |
| `tests/test_store_metadata.py` | create | Tests for new store metadata method |

### Dependency Chain

| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `BaseStore.get_chunk_metadata()` | `HotContextCompiler` | (abstract — implemented by ChromaStore) |
| `ChromaStore.get_chunk_metadata()` | `HotContextCompiler` (via BaseStore) | `chromadb.Collection.get()` |
| `HotContextCompiler.compile()` | Future: `hwcc compile` CLI (task 2.5) | `Manifest`, `BaseStore`, `TemplateEngine`, `CompileContext` |

### Pipeline Impact

| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| **Store** (Phase 1) | New abstract method on BaseStore | None — additive change |
| **Compile** (Phase 2) | Consumes manifest + store + config | Produces `.rag/context/hot.md` |
| **Serve** (Phase 3) | None | MCP server may serve hot.md content |

---

## NON-GOALS (Explicitly Out of Scope)

- [ ] `src/hwcc/compile/base.py` — BaseCompiler signature is unchanged
- [ ] `src/hwcc/compile/context.py` — CompileContext is already complete (task 2.3)
- [ ] `src/hwcc/compile/templates.py` — TemplateEngine is already complete (task 2.3)
- [ ] `src/hwcc/templates/hot_context.md.j2` — Template is already complete (task 2.3)
- [ ] `src/hwcc/manifest.py` — Manifest schema is unchanged; read-only usage
- [ ] `src/hwcc/config.py` — Config schema is unchanged; read-only usage
- [ ] `src/hwcc/cli/` — CLI integration is task 2.5
- [ ] Errata parsing — task 2.2 (we handle errata data IF present in context)
- [ ] Output file injection — task 2.4 (CLAUDE.md marker injection)

---

## Technical Approach

### Architecture Decision: Data Sources

The `HotContextCompiler` needs data from three sources:

| Data | Source | Access Method |
|------|--------|--------------|
| Project/hardware/software/conventions | `HwccConfig` | `CompileContext.from_config(config)` |
| Document list (id, type, chip, chunks) | `Manifest` | `load_manifest()` → `manifest.documents` |
| Peripheral names | `BaseStore` chunk metadata | **New:** `store.get_chunk_metadata()` |
| Errata | Not yet available (task 2.2) | Gracefully empty |

### Architecture Decision: BaseStore Extension

**Problem:** `BaseStore.search()` requires embeddings, but the compile stage needs metadata-only queries (e.g., unique peripheral names from chunks).

**Solution:** Add `get_chunk_metadata()` to `BaseStore`:

```python
@abstractmethod
def get_chunk_metadata(
    self,
    where: dict[str, str] | None = None,
) -> list[ChunkMetadata]:
    """Get metadata for all chunks matching filters (no embedding needed).

    Args:
        where: Optional metadata filters (e.g., {"doc_type": "svd"}).

    Returns:
        List of ChunkMetadata for matching chunks.
    """
```

**Justification:**
- The `BaseCompiler.compile(store, config)` contract explicitly passes the store — the compile stage is *designed* to query it
- ChromaDB already supports this internally via `_collection.get()`
- Without this, compile cannot extract peripheral data — the manifest lacks peripheral names
- This is an additive change (new method, existing methods untouched)
- Only one store implementation exists (ChromaStore), so no third-party breakage

### Architecture Decision: Line Budget Enforcement

**Strategy:** Render-check-reduce loop.

1. Build full `CompileContext` with all data
2. Render via `TemplateEngine.render("hot_context.md.j2", context)`
3. Count lines
4. If over `hot_context_max_lines`, reduce data in priority order (lowest priority removed first):
   - Priority 4 (lowest): conventions → remove
   - Priority 3: peripheral list → truncate to top N, then remove
   - Priority 2: document table → truncate to top N, then remove
   - Priority 1 (highest): errata → keep always (safety-critical)
5. Re-render with reduced context
6. Header + target hardware + software stack are always included (they're small, ~10 lines)

**Why not pre-calculate budgets?** Couples too tightly to template structure. The render-check approach works regardless of template modifications.

### Architecture Decision: Compiler Constructor

```python
class HotContextCompiler(BaseCompiler):
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._context_dir = project_root / ".rag" / "context"

    def compile(self, store: BaseStore, config: HwccConfig) -> list[Path]:
        ...
```

The compiler receives `project_root` at construction time (to locate manifest and write output). The `compile()` method matches `BaseCompiler`'s signature.

---

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Add `get_chunk_metadata()` to BaseStore | `src/hwcc/store/base.py` | New abstract method returning `list[ChunkMetadata]` |
| 2 | Implement in ChromaStore | `src/hwcc/store/chroma.py` | Use `_collection.get()` to fetch metadata |
| 3 | Test store metadata query | `tests/test_store_metadata.py` | Unit tests with mock + integration with ChromaStore |
| 4 | Create HotContextCompiler | `src/hwcc/compile/hot_context.py` | Full compiler: manifest → context → render → write |
| 5 | Implement line budget enforcement | `src/hwcc/compile/hot_context.py` | Render-check-reduce loop with priority truncation |
| 6 | Export from __init__ | `src/hwcc/compile/__init__.py` | Add `HotContextCompiler` to exports |
| 7 | Test hot context compiler | `tests/test_compile_hot_context.py` | Full test suite |

---

## Test Plan

### Unit Tests — Store Metadata

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `get_chunk_metadata()` returns empty list when store is empty | `tests/test_store_metadata.py` | unit |
| 2 | `get_chunk_metadata()` returns all metadata when no filter | `tests/test_store_metadata.py` | unit |
| 3 | `get_chunk_metadata()` filters by `doc_type` | `tests/test_store_metadata.py` | unit |
| 4 | `get_chunk_metadata()` filters by `chip` | `tests/test_store_metadata.py` | unit |
| 5 | `get_chunk_metadata()` filters by `peripheral` | `tests/test_store_metadata.py` | unit |

### Unit Tests — HotContextCompiler

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 6 | Compiles hot.md with full project data | `tests/test_compile_hot_context.py` | unit |
| 7 | Compiles hot.md with empty project (no documents) | `tests/test_compile_hot_context.py` | unit |
| 8 | Compiles hot.md with config-only data (no store) | `tests/test_compile_hot_context.py` | unit |
| 9 | Includes document table from manifest | `tests/test_compile_hot_context.py` | unit |
| 10 | Includes peripheral list from store metadata | `tests/test_compile_hot_context.py` | unit |
| 11 | Includes hardware/software/conventions from config | `tests/test_compile_hot_context.py` | unit |
| 12 | Respects hot_context_max_lines limit | `tests/test_compile_hot_context.py` | unit |
| 13 | Priority truncation removes conventions first | `tests/test_compile_hot_context.py` | unit |
| 14 | Priority truncation removes peripherals before errata | `tests/test_compile_hot_context.py` | unit |
| 15 | Creates `.rag/context/` directory if missing | `tests/test_compile_hot_context.py` | unit |
| 16 | Returns list containing output path | `tests/test_compile_hot_context.py` | unit |
| 17 | Multi-chip: documents from multiple chips shown | `tests/test_compile_hot_context.py` | unit |
| 18 | Deduplicates peripheral names across chunks | `tests/test_compile_hot_context.py` | unit |
| 19 | Updates manifest.last_compiled timestamp | `tests/test_compile_hot_context.py` | unit |
| 20 | Handles store with zero chunks gracefully | `tests/test_compile_hot_context.py` | unit |

### Acceptance Criteria (Testable)

| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Compile with STM32F407 SVD + PDF indexed | `hot.md` contains MCU info, document table, peripheral list | automated |
| 2 | Compile with config only (no docs) | `hot.md` has header + hardware section, no doc/peripheral sections | automated |
| 3 | Compile with > 120 lines of content | Output truncated to ≤ 120 lines, errata preserved | automated |
| 4 | Re-compile after adding documents | `hot.md` updated with new document data | automated |

---

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/store/base.py` | modify | Add `get_chunk_metadata()` abstract method |
| `src/hwcc/store/chroma.py` | modify | Implement `get_chunk_metadata()` using `_collection.get()` |
| `src/hwcc/compile/__init__.py` | modify | Add `HotContextCompiler` export |

## Files to Create

| File | Purpose |
|------|---------|
| `src/hwcc/compile/hot_context.py` | `HotContextCompiler` class — main implementation |
| `tests/test_store_metadata.py` | Tests for `BaseStore.get_chunk_metadata()` |
| `tests/test_compile_hot_context.py` | Tests for `HotContextCompiler` |

---

## Exit Criteria

```
□ BaseStore.get_chunk_metadata() abstract method added
□ ChromaStore.get_chunk_metadata() implemented
□ HotContextCompiler.compile() produces .rag/context/hot.md
□ hot_context_max_lines enforced with priority truncation
□ Empty project handled gracefully (no crash, minimal output)
□ Multi-chip project data shown correctly
□ Peripheral names extracted and deduplicated from store
□ All tests pass: pytest tests/
□ Lint clean: ruff check src/ tests/
□ Types clean: mypy src/hwcc/
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched
```

## Verification Strategy

- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] Manual test: create temp project, add SVD, run compiler, inspect hot.md
- [ ] No unintended side effects in: templates, context dataclasses, config, manifest

## Document Updates Needed

- [ ] **TECH_SPEC.md:** None (hot context compiler is already described)
- [ ] **PLAN.md:** Mark task 2.1 as `[x]` complete

---

> **Last Updated:** 2026-02-28

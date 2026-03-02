# Plan: Task 3.6 — CLI Search (`hwcc search`)

## Scope Declaration
- **Type:** feature
- **Single Concern:** Implement `hwcc search` CLI command that queries the vector store and displays results with Rich formatting
- **Phase:** v0.2 (Quality & Search)
- **Complexity:** Low–Medium
- **Risk:** Low (additive feature, no existing code modified except the CLI stub)

## Problem Statement
**What:** Users have no way to interactively query their indexed hardware documentation. The `hwcc search` command stub exists but is not implemented.

**Why:** After `hwcc add` ingests documents, users need to verify what was indexed and find specific information. This also validates the full ingest→embed→store→query pipeline end-to-end from the CLI.

**Success:** `hwcc search "GPIO configuration"` returns relevant chunks with scores, metadata, and formatted output. Filters by `--chip`, `--doc-type`, and `--peripheral` work correctly.

---

## Design

### Command Signature

```
hwcc search <query>                          → Top 5 results from all docs
hwcc search <query> --top-k 10               → Top 10 results
hwcc search <query> --chip STM32F407         → Filter by chip
hwcc search <query> --doc-type svd           → Filter by document type
hwcc search <query> --peripheral GPIOA       → Filter by peripheral
hwcc search <query> --full                   → Show full chunk content (not truncated)
```

### Flow

1. Verify project is initialized (`ProjectManager.is_initialized`)
2. Load config from `.rag/config.toml`
3. Create embedder via registry (same provider used for indexing)
4. Create store (ChromaDB)
5. Embed the query text via `embedder.embed_query(query)`
6. Search the store via `store.search(query_embedding, k=top_k, where=filters)`
7. Display results as a Rich table/panels

### Output Format

```
Found 5 results for "GPIO configuration" (0.23s)

 #1  Score: 0.87  │  STM32F407 / GPIOA  │  svd  │  page 42
 ─────────────────────────────────────────────────────
 ## GPIOA_MODER
 Each pin's mode can be configured as: Input (00), General purpose output (01),
 Alternate function (10), Analog (11). Reset value: 0xA8000000...

 #2  Score: 0.72  │  STM32F407 / GPIOB  │  datasheet  │  page 156
 ─────────────────────────────────────────────────────
 GPIO port configuration lock register (GPIOx_LCKR) is used to lock the
 configuration of the port bits...
```

For truncated mode (default): show first 200 chars of content with `...`
For `--full` mode: show complete chunk content.

### Metadata Filters

ChromaDB `where` clause construction:
- Single filter: `{"chip": "STM32F407"}`
- Multiple filters: `{"$and": [{"chip": "STM32F407"}, {"doc_type": "svd"}]}`

---

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Create search module | `src/hwcc/search.py` | `SearchEngine` class: wraps embedder + store, builds filters, executes query |
| 2 | Implement CLI command | `src/hwcc/cli.py` | Replace stub with real implementation using `SearchEngine` |
| 3 | Write tests | `tests/test_search.py` | Unit tests for SearchEngine + CLI output |
| 4 | Verify | — | Full test suite, lint, types |

## Files to Create

| File | Purpose |
|------|---------|
| `src/hwcc/search.py` | Search engine: query embedding, filter building, result formatting |
| `tests/test_search.py` | Search unit tests |

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/cli.py` | modify | Replace `search` stub with real implementation |

## NON-GOALS (Do NOT Touch)

- [ ] Store internals (`src/hwcc/store/`) — search uses existing `BaseStore.search()` API
- [ ] Embedder internals (`src/hwcc/embed/`) — search uses existing `BaseEmbedder.embed_query()` API
- [ ] Compile stage — search is read-only, doesn't affect context generation
- [ ] Catalog module — separate feature
- [ ] Pipeline module — search is a standalone query, not a pipeline stage
- [ ] Config changes — no new config sections needed
- [ ] Ingest/chunking — search only reads from the store

## Technical Approach

### SearchEngine class

A thin wrapper that composes embedder + store for the search workflow:

```python
@dataclass(frozen=True)
class SearchEngine:
    embedder: BaseEmbedder
    store: BaseStore

    def search(
        self,
        query: str,
        k: int = 5,
        chip: str = "",
        doc_type: str = "",
        peripheral: str = "",
    ) -> list[SearchResult]:
        """Embed query and search the store with optional filters."""
        query_embedding = self.embedder.embed_query(query)
        where = self._build_where(chip=chip, doc_type=doc_type, peripheral=peripheral)
        return self.store.search(query_embedding, k=k, where=where)

    @staticmethod
    def _build_where(...) -> dict | None:
        """Build ChromaDB where clause from filter parameters."""
```

This keeps the CLI command thin (just argument parsing + output formatting) and the search logic testable independently.

### Why a separate module?

1. **Testability**: `SearchEngine` can be tested with mock embedder + store without CLI
2. **Reuse**: MCP server (v0.3) will need the same search logic
3. **Separation**: CLI handles formatting, `SearchEngine` handles query logic

---

## Test Plan

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `_build_where` returns None for no filters | `tests/test_search.py` | unit |
| 2 | `_build_where` returns single filter dict | `tests/test_search.py` | unit |
| 3 | `_build_where` returns `$and` for multiple filters | `tests/test_search.py` | unit |
| 4 | `search()` calls embedder and store correctly | `tests/test_search.py` | unit |
| 5 | `search()` passes filters through to store | `tests/test_search.py` | unit |
| 6 | `search()` returns empty list for no results | `tests/test_search.py` | unit |
| 7 | `search()` propagates EmbeddingError | `tests/test_search.py` | unit |
| 8 | `search()` propagates StoreError | `tests/test_search.py` | unit |
| 9 | `format_results` truncates content by default | `tests/test_search.py` | unit |
| 10 | `format_results` shows full content with flag | `tests/test_search.py` | unit |

## Exit Criteria
```
□ `hwcc search "GPIO"` returns results from indexed store
□ --chip, --doc-type, --peripheral filters work
□ --top-k controls result count
□ --full shows complete chunk content
□ Rich formatted output with scores and metadata
□ All tests pass, lint clean, types clean
□ NON-GOALS remain untouched
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No unintended side effects in: store, embed, compile, catalog modules

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None (search is already mentioned in architecture)
- [ ] **PLAN.md:** Check off task 3.6 when complete

---

> **Last Updated:** 2026-03-02

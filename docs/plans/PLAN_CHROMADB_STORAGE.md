# Plan: ChromaDB Storage (Task 1.7)

## Scope Declaration
- **Type:** feature
- **Single Concern:** Implement ChromaDB-backed vector store that persists embedded chunks and supports similarity search with metadata filtering
- **Phase:** 1 (Document Ingestion)
- **Complexity:** Medium
- **Risk:** Low

## Problem Statement
**What:** Implement `ChromaStore`, a concrete `BaseStore` subclass that uses ChromaDB's `PersistentClient` for file-based vector storage. This is the persistence layer that completes the ingest pipeline: parse → chunk → embed → **store**.

**Why:** Without a store, embedded chunks exist only in memory. ChromaDB provides persistent vector storage with similarity search, enabling the compile and serve phases (Phase 2-3) to query relevant hardware documentation.

**Success:** `ChromaStore` passes all `BaseStore` ABC contract tests, persists to disk, supports add/search/delete/count, and filters by `chip` metadata for multi-vendor queries.

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/store/chroma.py` | create | ChromaStore implementation |
| `src/hwcc/store/__init__.py` | modify | Export ChromaStore, register in registry |
| `src/hwcc/config.py` | modify | Add `StoreConfig` dataclass |
| `tests/test_store.py` | create | Full test suite for ChromaStore |
| `pyproject.toml` | modify | Add `chromadb` dependency, mypy override |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `ChromaStore.add()` | `Pipeline.process()` | `chromadb.Collection.add()` |
| `ChromaStore.search()` | `Pipeline` (future), `hwcc search` CLI | `chromadb.Collection.query()` |
| `ChromaStore.delete()` | `Pipeline.remove()` | `chromadb.Collection.get()`, `chromadb.Collection.delete()` |
| `ChromaStore.count()` | `hwcc status` CLI | `chromadb.Collection.count()` |
| `StoreConfig` | `HwccConfig` | `config.toml` persistence |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Store | Receives `list[EmbeddedChunk]` from embedder | Feeds `SearchResult` to compile/serve |

## NON-GOALS (Explicitly Out of Scope)
- [ ] CLI integration (`hwcc add`, `hwcc search`) — Task 1.8+
- [ ] Pipeline wiring changes — Pipeline already calls `store.add()` / `store.delete()`
- [ ] Embedding providers — Task 1.6 (done)
- [ ] Compile/serve phases — Phase 2-3
- [ ] ChromaDB server mode (HttpClient) — Only PersistentClient for MVP
- [ ] Custom distance metrics — Use ChromaDB defaults (L2)
- [ ] Embedding function in ChromaDB — We provide pre-computed embeddings

## Technical Approach

### Option A: Direct PersistentClient with flat metadata (Recommended)

Use ChromaDB's `PersistentClient` for file-based persistence. Store all `ChunkMetadata` fields as flat metadata (ChromaDB requires flat key-value, no nesting). Use `chunk.chunk_id` as ChromaDB record IDs.

**Key design decisions:**

1. **Constructor signature:** `ChromaStore(persist_path: Path, collection_name: str = "hwcc")`
   - Takes filesystem path directly (not from config) — testable with `tmp_path`
   - Collection name defaults to "hwcc", overridable per project

2. **Metadata mapping:** Flatten `ChunkMetadata` fields into ChromaDB metadata dict:
   - `doc_id`, `doc_type`, `chip`, `section_path`, `chunk_level`, `peripheral`, `content_type` → `str`
   - `page`, `token_count` → `int`
   - All are simple types (ChromaDB requirement: str, int, float, bool only)

3. **Delete strategy:** Use `collection.delete(where={"doc_id": doc_id})` — delete all chunks for a document by metadata filter. Get count first via `collection.get()`.

4. **Search result mapping:** ChromaDB returns distances (lower = more similar). Convert to score: `score = 1.0 / (1.0 + distance)`. Reconstruct `Chunk` + `ChunkMetadata` from stored metadata.

5. **Registry integration:** Register `"chromadb"` in `store/__init__.py`. Since the factory needs `persist_path` (runtime-dependent), use a factory builder pattern or defer full registry wiring to task 1.8.

- **Pros:** Simple, fully testable with real ChromaDB (no mocking needed), matches existing patterns
- **Cons:** Metadata mapping is manual (but ChunkMetadata is stable)

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Add StoreConfig to config | `src/hwcc/config.py`, `tests/test_config.py` | Add `StoreConfig(provider="chromadb", collection_name="hwcc")` to `HwccConfig` |
| 2 | Add chromadb dependency | `pyproject.toml` | Add `chromadb>=0.5` to dependencies, mypy override for `chromadb` |
| 3 | Implement ChromaStore | `src/hwcc/store/chroma.py` | Full implementation of `add`, `search`, `delete`, `count` |
| 4 | Update store __init__ | `src/hwcc/store/__init__.py` | Export ChromaStore, register in registry |
| 5 | Write tests | `tests/test_store.py` | Comprehensive test suite using real ChromaDB with tmp_path |

## Test Plan

### Unit Tests (using real ChromaDB with tmp_path — true integration)
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `test_init_creates_collection` — constructor creates persistent collection | `tests/test_store.py` | integration |
| 2 | `test_add_empty_returns_zero` — empty chunk list returns 0 | `tests/test_store.py` | unit |
| 3 | `test_add_stores_chunks` — add chunks, count increases | `tests/test_store.py` | integration |
| 4 | `test_add_stores_metadata` — all ChunkMetadata fields round-trip | `tests/test_store.py` | integration |
| 5 | `test_add_stores_documents` — chunk content stored as documents | `tests/test_store.py` | integration |
| 6 | `test_add_incremental` — add from different docs, both present | `tests/test_store.py` | integration |
| 7 | `test_search_returns_results` — basic similarity search works | `tests/test_store.py` | integration |
| 8 | `test_search_with_chip_filter` — where={"chip": "STM32F407"} filters correctly | `tests/test_store.py` | integration |
| 9 | `test_search_respects_k` — returns at most k results | `tests/test_store.py` | integration |
| 10 | `test_search_empty_collection` — returns empty list | `tests/test_store.py` | integration |
| 11 | `test_search_result_has_score_and_distance` — score and distance populated | `tests/test_store.py` | integration |
| 12 | `test_search_reconstructs_chunk_metadata` — SearchResult has complete Chunk | `tests/test_store.py` | integration |
| 13 | `test_delete_by_doc_id` — removes all chunks for document | `tests/test_store.py` | integration |
| 14 | `test_delete_nonexistent_returns_zero` — unknown doc_id returns 0 | `tests/test_store.py` | integration |
| 15 | `test_delete_reduces_count` — count decreases after delete | `tests/test_store.py` | integration |
| 16 | `test_count_empty` — empty store returns 0 | `tests/test_store.py` | unit |
| 17 | `test_count_after_add` — reflects number of added chunks | `tests/test_store.py` | integration |
| 18 | `test_config_roundtrip` — StoreConfig survives TOML save/load | `tests/test_config.py` | unit |
| 19 | `test_default_store_config` — defaults are "chromadb" and "hwcc" | `tests/test_config.py` | unit |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Add 10 embedded chunks for doc "board_svd" | count() returns 10 | automated |
| 2 | Search with query embedding, k=3 | Returns 3 SearchResult with scores | automated |
| 3 | Search with where={"chip": "STM32F407"} | Only returns chunks with that chip | automated |
| 4 | Delete "board_svd" | count() decreases by 10 | automated |
| 5 | Data persists across ChromaStore instances | New instance with same path sees old data | automated |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/config.py` | modify | Add `StoreConfig` dataclass to `HwccConfig` |
| `src/hwcc/store/__init__.py` | modify | Export ChromaStore, register in registry |
| `pyproject.toml` | modify | Add chromadb dependency, mypy override |

## Files to Create
| File | Purpose |
|------|---------|
| `src/hwcc/store/chroma.py` | ChromaStore implementation |
| `tests/test_store.py` | Full test suite |

## Exit Criteria
```
□ ChromaStore implements all 4 BaseStore abstract methods
□ All metadata fields (including chip) round-trip correctly
□ Search with where filter works for multi-vendor queries
□ Delete removes all chunks for a doc_id
□ Data persists to disk (PersistentClient)
□ All tests pass: pytest tests/test_store.py tests/test_config.py
□ ruff check clean
□ mypy clean
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/test_store.py tests/test_config.py -v`
- [ ] Lint passes: `ruff check src/hwcc/store/ tests/test_store.py`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No unintended side effects in: embedding providers, pipeline, CLI

## Document Updates Needed
- [ ] **TECH_SPEC.md:** Add ChromaStore to store module documentation (in /wrapup)
- [ ] **PLAN.md:** Mark task 1.7 as `[x]` (in /wrapup)

---

> **Last Updated:** 2026-02-28

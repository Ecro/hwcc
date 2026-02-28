# Plan: Implement `hwcc remove` (Task 1.9)

## Scope Declaration
- **Type:** feature
- **Single Concern:** Implement the `hwcc remove` CLI command that removes a document from the manifest and deletes its chunks from ChromaDB
- **Phase:** 1 (Document Ingestion)
- **Complexity:** Low
- **Risk:** Low — uses existing `Manifest.remove_document()` and `ChromaStore.delete()`

## Problem Statement
**What:** Replace the `hwcc remove` stub with a working command that accepts a doc_id (or file path), deletes chunks from ChromaDB, removes the entry from the manifest, and prints a confirmation.
**Why:** Users need to remove outdated or incorrect documents from their index. Without this, the only way to clean up is to delete the `.rag/` directory and re-add everything.
**Success:** `hwcc remove board_svd` removes all chunks for that document and updates the manifest.

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/cli.py` | modify | Replace `remove` stub with implementation |
| `tests/test_cli_add.py` | modify | Add remove command tests (rename to `test_cli_add_remove.py` is NOT needed — add tests inline) |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `cli.remove()` | Typer CLI | `ProjectManager`, `load_config`, `load_manifest`, `save_manifest`, `ChromaStore.delete`, `Manifest.remove_document`, `make_doc_id` |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| CLI (`remove`) | None | Removes data from store + manifest |

## NON-GOALS (Explicitly Out of Scope)
- [ ] `hwcc add` changes — already implemented
- [ ] `hwcc status` enhancements — task 1.10
- [ ] Processed markdown file cleanup — `.rag/processed/` files don't exist yet (deferred to compile phase)
- [ ] Batch removal / glob patterns — single doc_id at a time
- [ ] Confirmation prompt before deletion — MVP, add later if needed

## Technical Approach

### Design
1. Accept argument as either doc_id (`board_svd`) or file path (`board.svd`)
2. Try lookup by doc_id first; if not found, convert path to doc_id via `make_doc_id()` and retry
3. Delete chunks from ChromaDB via `ChromaStore.delete(doc_id)`
4. Remove from manifest via `Manifest.remove_document(doc_id)`
5. Save manifest
6. Print confirmation with chunk count

### Flow
```
1. Validate project initialized
2. Load config + manifest
3. Resolve doc_id (direct lookup or path → make_doc_id)
4. If not found in manifest → print error, exit 1
5. Construct ChromaStore
6. store.delete(doc_id) → deleted_chunks
7. manifest.remove_document(doc_id)
8. save_manifest()
9. Print "Removed {name} ({N} chunks deleted)"
```

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Write tests (RED) | `tests/test_cli_add.py` | Add TestRemove class with 5 tests |
| 2 | Implement remove command (GREEN) | `src/hwcc/cli.py` | Replace stub with implementation |
| 3 | Verify | — | pytest, ruff, mypy |

## Test Plan

### CLI Integration Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Project not initialized → error, exit 1 | `tests/test_cli_add.py` | integration |
| 2 | Nonexistent doc_id → "not found" error, exit 1 | `tests/test_cli_add.py` | integration |
| 3 | Successful remove by doc_id → manifest updated, chunks deleted | `tests/test_cli_add.py` | integration |
| 4 | Remove by file path → resolves to doc_id, removes | `tests/test_cli_add.py` | integration |
| 5 | Remove updates manifest (count decreases) | `tests/test_cli_add.py` | integration |

### Acceptance Criteria
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | `hwcc remove board_svd` | Chunks deleted, manifest updated | automated |
| 2 | `hwcc remove nonexistent` | "Document not found" error | automated |
| 3 | `hwcc remove board.svd` (path) | Resolves to doc_id, removes | automated |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/cli.py` | modify | Replace remove stub (~25 lines) |
| `tests/test_cli_add.py` | modify | Add TestRemove class (5 tests) |

## Exit Criteria
```
□ `hwcc remove <doc_id>` deletes chunks and updates manifest
□ Path-based removal works (hwcc remove board.svd)
□ Nonexistent doc_id prints error with exit 1
□ Project not initialized prints error with exit 1
□ All changes within declared scope
□ NON-GOALS remain untouched
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No unintended side effects in: add command, store, manifest modules

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None
- [ ] **PLAN.md:** Mark task 1.9 as `[x]`

---

> **Last Updated:** 2026-02-28

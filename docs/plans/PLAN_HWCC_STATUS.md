# Plan: Implement `hwcc status` enhancements (Task 1.10)

## Scope Declaration
- **Type:** feature
- **Single Concern:** Enhance the `hwcc status` CLI command to show per-document details, embedding model info, and store size
- **Phase:** 1 (Document Ingestion)
- **Complexity:** Low
- **Risk:** Low — read-only display changes, no data mutations

## Problem Statement
**What:** Enhance `hwcc status` to show per-document table (name, type, chip, chunks, date), embedding model info, and store size on disk.
**Why:** Users need visibility into what documents are indexed and how the system is configured. The current output only shows total counts.
**Success:** `hwcc status` shows a Rich table with per-document details, embedding config, and index size.

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/cli.py` | modify | Enhance `status()` function with per-document table, embedding info, store size |
| `tests/test_cli.py` | modify | Add tests for enhanced status output |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `cli.status()` | Typer CLI | `ProjectManager.status()`, `load_manifest()`, `pm.rag_dir` |

## NON-GOALS (Explicitly Out of Scope)
- [ ] `hwcc add` / `hwcc remove` changes — already implemented
- [ ] `ProjectStatus` dataclass changes in `project.py` — load manifest directly in CLI
- [ ] ChromaDB collection count query — use manifest chunk counts
- [ ] Total token counts — token info not stored in manifest (deferred)

## Technical Approach

Enhance the existing `status()` function in `cli.py`:

1. **Embedding config section**: Show `config.embedding.model` + `config.embedding.provider`
2. **Store size**: Compute total size of `pm.rag_dir / "index"` directory
3. **Per-document table**: Rich Table from `manifest.documents` with columns: ID, Type, Chip, Chunks, Added

### Expected Output
```
$ hwcc status
hwcc project: my-project
  MCU: STM32F407
  RTOS: FreeRTOS 10.5.1

  Documents  2
  Chunks     137
  Embedding  nomic-embed-text (ollama)
  Index      4.2 MB

Documents:
  ID            Type        Chip         Chunks  Added
  board_svd     svd         STM32F407    42      2026-02-28
  datasheet_pdf datasheet   STM32F407    95      2026-02-28
```

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Write tests (RED) | `tests/test_cli.py` | Add tests for enhanced status output |
| 2 | Implement enhancements (GREEN) | `src/hwcc/cli.py` | Add embedding info, store size, per-document table |
| 3 | Verify | — | pytest, ruff, mypy |

## Test Plan

### CLI Integration Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Status with documents shows per-document info | `tests/test_cli.py` | integration |
| 2 | Status shows embedding model info | `tests/test_cli.py` | integration |
| 3 | Status with no documents shows hint (existing test preserved) | `tests/test_cli.py` | integration |

### Acceptance Criteria
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | `hwcc status` with indexed docs | Shows per-document table with ID, type, chip, chunks | automated |
| 2 | `hwcc status` on fresh project | Shows 0 documents hint + embedding info | automated |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/cli.py` | modify | Enhance status() with ~30 lines |
| `tests/test_cli.py` | modify | Add 2-3 tests for new output |

## Exit Criteria
```
□ Per-document table shows ID, type, chip, chunks, date
□ Embedding model and provider shown
□ Store size on disk shown
□ Existing status tests still pass
□ All changes within declared scope
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No unintended side effects in: add, remove, project modules

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None
- [ ] **PLAN.md:** Mark task 1.10 as `[x]`

---

> **Last Updated:** 2026-02-28

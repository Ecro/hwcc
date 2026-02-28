# Plan: Phase 1 Hardening — Fix Critical Issues from Code Review

## Scope Declaration
- **Type:** bugfix
- **Single Concern:** Fix the 7 critical bugs found during comprehensive Phase 1 review
- **Phase:** 1 (post-completion hardening)
- **Complexity:** Medium
- **Risk:** Medium — touches multiple modules, but each fix is isolated and well-understood

## Problem Statement
**What:** Fix 7 critical issues identified across 4 subsystems during Phase 1 review: silent metadata loss in pipeline, SVD XXE memory safety, PDF broad exception catch, chunk overlap on atomic blocks, ChromaDB filtered search failure, CLI init error handling, and absolute path leakage in manifest.
**Why:** These issues will cause incorrect behavior, resource exhaustion, or runtime failures in production use.
**Success:** All 7 issues fixed, existing tests pass, new tests cover the fixed behavior.

## NON-GOALS (Explicitly Out of Scope)
- [ ] Warning-level issues (W1–W22) — defer to a separate cleanup task
- [ ] Suggestion-level improvements (S1–S24) — defer to Phase 2
- [ ] DRY violations (_make_doc_id duplication, _normalize_whitespace duplication) — refactoring, separate concern
- [ ] `ProviderRegistry` Any usage — refactoring, separate concern
- [ ] New features or Phase 2 work
- [ ] Test coverage gaps for existing working code

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/pipeline.py` | modify | Apply doc_type/chip overrides to ParseResult |
| `src/hwcc/ingest/svd.py` | modify | Add MAX_FILE_SIZE guard; read only header for XXE check |
| `src/hwcc/ingest/pdf.py` | modify | Narrow `except Exception` to specific types; fix header read |
| `src/hwcc/chunk/markdown.py` | modify | Skip overlap injection for atomic blocks |
| `src/hwcc/store/chroma.py` | modify | Handle filtered search k > matching count |
| `src/hwcc/cli.py` | modify | Wrap init in try/except; store relative paths |
| `tests/test_pipeline.py` | modify | Add test for doc_type/chip override |
| `tests/test_ingest_svd.py` | modify | Add test for oversized SVD file |
| `tests/test_ingest_pdf.py` | modify | Add test for narrowed exception types |
| `tests/test_chunk.py` | modify | Add test for atomic block overlap skip |
| `tests/test_store.py` | modify | Add test for filtered search with k > matches |
| `tests/test_cli.py` | modify | Add test for init error handling |
| `tests/test_cli_add.py` | modify | Add test for relative path storage |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Pipeline (C1) | CLI passes doc_type/chip | Chunk metadata now correctly tagged |
| Ingest (C2, C3) | None | Safer parsing, no resource exhaustion |
| Chunk (C4) | ParseResult unchanged | Atomic blocks no longer inflated |
| Store (C5) | None | Filtered search no longer crashes |

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | C1: Pipeline metadata pass-through | `pipeline.py`, `test_pipeline.py` | Apply doc_type/chip to ParseResult via `dataclasses.replace()` |
| 2 | C2: SVD file size guard + header-only XXE check | `svd.py`, `test_ingest_svd.py` | Add MAX_FILE_SIZE; read only 8KB for XXE check |
| 3 | C3: PDF narrow exception catch + bounded header read | `pdf.py`, `test_ingest_pdf.py` | Catch (RuntimeError, ValueError, OSError); read(5) not read_bytes()[:5] |
| 4 | C4: Skip overlap on atomic blocks | `markdown.py`, `test_chunk.py` | Track atomic indices, skip in _add_overlap |
| 5 | C5: ChromaDB filtered search resilience | `chroma.py`, `test_store.py` | Catch "not enough elements" and return available results |
| 6 | C6: CLI init error handling | `cli.py`, `test_cli.py` | Wrap pm.init() in try/except HwccError |
| 7 | C7: Store relative paths in manifest | `cli.py`, `test_cli_add.py` | Use file_path.relative_to(pm.root) with fallback |
| 8 | Verify all | — | pytest, ruff, mypy |

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Pipeline.process() applies doc_type/chip override to ParseResult | `tests/test_pipeline.py` | unit |
| 2 | SVD parser rejects files exceeding MAX_FILE_SIZE | `tests/test_ingest_svd.py` | unit |
| 3 | PDF parser raises ParseError for corrupt files (not generic Exception) | `tests/test_ingest_pdf.py` | unit |
| 4 | Overlap not added to atomic blocks (tables/code) | `tests/test_chunk.py` | unit |
| 5 | ChromaDB search with filter and k > matches returns partial results | `tests/test_store.py` | integration |
| 6 | CLI init catches HwccError and shows user-friendly message | `tests/test_cli.py` | integration |
| 7 | Add command stores relative paths in manifest entries | `tests/test_cli_add.py` | integration |

### Acceptance Criteria
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Pipeline with doc_type="datasheet" | Chunk metadata has doc_type="datasheet" | automated |
| 2 | 200 MB SVD file | ParseError raised before reading entire file | automated |
| 3 | Corrupt PDF (not %PDF-) | ParseError with clear message | automated |
| 4 | Code block followed by text chunks | Code block token count unchanged | automated |
| 5 | Search with chip filter, k=10, only 2 matching | Returns 2 results, no error | automated |
| 6 | Init on read-only directory | User-friendly error, exit 1 | automated |
| 7 | hwcc add file.txt | Manifest stores relative path, not absolute | automated |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/pipeline.py` | modify | ~5 lines: replace() for doc_type/chip |
| `src/hwcc/ingest/svd.py` | modify | ~15 lines: MAX_FILE_SIZE + header-only check |
| `src/hwcc/ingest/pdf.py` | modify | ~5 lines: narrow exception + bounded read |
| `src/hwcc/chunk/markdown.py` | modify | ~15 lines: track atomic indices in _add_overlap |
| `src/hwcc/store/chroma.py` | modify | ~10 lines: catch NotEnoughElements |
| `src/hwcc/cli.py` | modify | ~10 lines: init guard + relative paths |
| `tests/test_pipeline.py` | modify | ~15 lines: 1 new test |
| `tests/test_ingest_svd.py` | modify | ~10 lines: 1 new test |
| `tests/test_ingest_pdf.py` | modify | ~5 lines: verify exception type |
| `tests/test_chunk.py` | modify | ~15 lines: 1 new test |
| `tests/test_store.py` | modify | ~15 lines: 1 new test |
| `tests/test_cli.py` | modify | ~10 lines: 1 new test |
| `tests/test_cli_add.py` | modify | ~10 lines: 1 new test |

## Exit Criteria
```
□ C1: Pipeline.process() forwards doc_type/chip to chunk metadata
□ C2: SVD parser has MAX_FILE_SIZE guard and header-only XXE check
□ C3: PDF parser catches specific exceptions, not bare Exception
□ C4: Atomic blocks (tables/code) are not inflated by overlap
□ C5: ChromaDB filtered search handles k > matching count gracefully
□ C6: CLI init catches errors and shows friendly message
□ C7: Manifest stores relative paths instead of absolute
□ All existing tests pass
□ New tests cover all 7 fixes
□ NON-GOALS remain untouched
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No unintended side effects in: registry, config, project modules

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None
- [ ] **PLAN.md:** None (hardening, not a new task)

---

> **Last Updated:** 2026-02-28

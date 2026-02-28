# Plan: Implement `hwcc add` (Task 1.8)

## Scope Declaration
- **Type:** feature
- **Single Concern:** Implement the `hwcc add` CLI command that runs the full ingest pipeline (detect → parse → chunk → embed → store) with manifest tracking and Rich progress output
- **Phase:** 1 (Document Ingestion)
- **Complexity:** Medium
- **Risk:** Medium — wires together all previous pipeline stages for the first time

## Problem Statement
**What:** Replace the `hwcc add` stub with a working command that accepts file paths, detects file types, runs parse→chunk→embed→store, updates the manifest, and shows progress.
**Why:** This is the core user-facing command — the first end-to-end pipeline execution. Without it, all pipeline stages are isolated modules with no CLI entry point.
**Success:** `hwcc add board.svd` processes the file, stores chunks in ChromaDB, updates manifest.json, and prints a summary.

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/cli.py` | modify | Replace `add` command stub with full implementation |
| `src/hwcc/ingest/__init__.py` | modify | Add `get_parser()` helper function to map parser_name → parser instance |
| `tests/test_cli_add.py` | create | Integration tests for `hwcc add` command |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `cli.add()` | Typer CLI entry point | `ProjectManager`, `detect_file_type`, `get_parser`, `MarkdownChunker`, `default_registry.create("embedding", ...)`, `ChromaStore`, `Pipeline.process`, `manifest.*`, `config.*` |
| `ingest.get_parser()` | `cli.add()` | `PdfParser`, `SvdParser`, `MarkdownParser`, `TextParser` |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| CLI (`add`) | None — this is the entry point | Triggers all stages: parse→chunk→embed→store |
| Manifest | Updated after successful pipeline run | Enables incremental updates on re-add |

## NON-GOALS (Explicitly Out of Scope)
- [ ] `--watch` flag implementation — Save for separate task (requires `watchdog` library)
- [ ] Directory recursion — Only file paths for now (directory support can be added later)
- [ ] `hwcc remove` — Separate task 1.9
- [ ] `hwcc status` chunk count from ChromaDB — Separate task 1.10
- [ ] Registry-based parser/store creation — Parsers instantiated directly (no factory indirection needed yet)
- [ ] Compile stage — Phase 2
- [ ] Error recovery / partial rollback — Document-level atomicity is sufficient for MVP

## Technical Approach

### Option A: Direct wiring in CLI (Recommended)
Wire up all pipeline stages directly in `cli.add()`, using existing modules:
1. `detect_file_type(path)` → `FileInfo` with `parser_name`
2. `get_parser(parser_name)` → `BaseParser` instance (new helper in `ingest/__init__.py`)
3. Construct `MarkdownChunker`, embedder (via registry), `ChromaStore` (direct)
4. Create `Pipeline(parser, chunker, embedder, store, config)`
5. Call `pipeline.process(path, doc_id, doc_type, chip)`
6. Update manifest with chunk count

- **Pros:** Simple, direct, no over-engineering. All wiring visible in one place.
- **Cons:** `cli.add()` will be ~80 lines. Acceptable for now.

### Option B: Factory in ProjectManager
Move pipeline construction into `ProjectManager.build_pipeline()`. Rejected — adds abstraction before it's needed. CLI is the only caller.

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Add `get_parser()` helper | `src/hwcc/ingest/__init__.py` | Map parser_name string → parser instance. Raise `ParseError` for unsupported parsers. |
| 2 | Write tests (RED) | `tests/test_cli_add.py` | Tests for the add command: no args, file not found, unsupported type, successful add (mocked pipeline), incremental skip, chip flag, type override. Uses `typer.testing.CliRunner`. |
| 3 | Implement `hwcc add` (GREEN) | `src/hwcc/cli.py` | Replace stub. Wire: detect → get_parser → build pipeline → process → update manifest. Rich progress output. |
| 4 | Verify all checks pass | — | `pytest`, `ruff check`, `mypy` |

## Detailed Design

### `get_parser(parser_name: str) -> BaseParser`
```python
# In src/hwcc/ingest/__init__.py
_PARSER_MAP: dict[str, type[BaseParser]] = {
    "pdf": PdfParser,
    "svd": SvdParser,
    "markdown": MarkdownParser,
    "text": TextParser,
}

def get_parser(parser_name: str) -> BaseParser:
    cls = _PARSER_MAP.get(parser_name)
    if cls is None:
        raise ParseError(f"No parser for format: {parser_name}")
    return cls()
```

### `cli.add()` flow
```
1. Validate project initialized (pm.is_initialized)
2. Load config + manifest
3. For each path:
   a. Resolve to Path, validate exists
   b. detect_file_type(path) → FileInfo
   c. Determine doc_type: use --type if provided, else FileInfo.doc_type
   d. Determine chip: use --chip if provided, else config.hardware.mcu
   e. make_doc_id(path) → doc_id
   f. compute_hash(path) → hash
   g. Check manifest.is_changed(doc_id, hash) — skip if unchanged
   h. get_parser(FileInfo.parser_name) → parser
   i. Construct Pipeline(parser, chunker, embedder, store, config)
   j. pipeline.process(path, doc_id, doc_type, chip) → chunk_count
   k. Create DocumentEntry, manifest.add_document(entry)
   l. Print success per file
4. save_manifest()
5. Print summary
```

### CLI Output (Rich)
```
$ hwcc add board.svd datasheet.pdf
Processing board.svd ...
  ✓ Detected: SVD (svd) [1.0]
  ✓ Parsed: 15,432 chars
  ✓ Chunked: 42 chunks
  ✓ Embedded & stored: 42 chunks
Processing datasheet.pdf ...
  ✓ Detected: PDF (datasheet) [0.9]
  ✓ Parsed: 128,000 chars
  ✓ Chunked: 95 chunks
  ✓ Embedded & stored: 95 chunks

Added 2 documents (137 chunks total)
```

### Error handling
- File not found → print error, continue to next file
- Unsupported format → print warning, skip
- Pipeline error → print error with details, continue to next file
- No files provided → print usage hint, exit 1
- Project not initialized → print "run hwcc init first", exit 1

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `get_parser("pdf")` returns PdfParser instance | `tests/test_ingest_detect.py` | unit |
| 2 | `get_parser("svd")` returns SvdParser instance | `tests/test_ingest_detect.py` | unit |
| 3 | `get_parser("markdown")` returns MarkdownParser instance | `tests/test_ingest_detect.py` | unit |
| 4 | `get_parser("text")` returns TextParser instance | `tests/test_ingest_detect.py` | unit |
| 5 | `get_parser("unknown")` raises ParseError | `tests/test_ingest_detect.py` | unit |

### CLI Integration Tests (CliRunner with mocked pipeline)
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 6 | No args prints usage hint, exits 1 | `tests/test_cli_add.py` | integration |
| 7 | File not found prints error, continues | `tests/test_cli_add.py` | integration |
| 8 | Project not initialized prints error, exits 1 | `tests/test_cli_add.py` | integration |
| 9 | Successful add with .txt file (full pipeline mocked) | `tests/test_cli_add.py` | integration |
| 10 | Unchanged file is skipped (manifest says no change) | `tests/test_cli_add.py` | integration |
| 11 | `--chip` flag overrides config MCU | `tests/test_cli_add.py` | integration |
| 12 | `--type` flag overrides auto-detected doc type | `tests/test_cli_add.py` | integration |
| 13 | Multiple files processed sequentially | `tests/test_cli_add.py` | integration |
| 14 | Unsupported file format prints warning, skips | `tests/test_cli_add.py` | integration |
| 15 | Pipeline error prints error, continues to next file | `tests/test_cli_add.py` | integration |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | `hwcc add file.txt` on initialized project | File detected, processed, manifest updated | automated |
| 2 | `hwcc add` with no args | Error message + exit 1 | automated |
| 3 | `hwcc add nonexistent.pdf` | Error message, non-zero exit | automated |
| 4 | Re-running `hwcc add file.txt` without changes | "Skipped (unchanged)" message | automated |
| 5 | `hwcc add --chip STM32F407 board.svd` | Chip tag passed to pipeline | automated |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/cli.py` | modify | Replace `add` stub with full implementation |
| `src/hwcc/ingest/__init__.py` | modify | Add `get_parser()` helper + `_PARSER_MAP` |

## Files to Create
| File | Purpose |
|------|---------|
| `tests/test_cli_add.py` | CLI integration tests with mocked pipeline stages |

## Exit Criteria
```
□ `hwcc add <file>` processes file through detect→parse→chunk→embed→store
□ Manifest updated with doc entry after successful add
□ Unchanged files skipped with informative message
□ --chip and --type flags work correctly
□ Rich progress output for each file
□ Errors per-file don't abort remaining files
□ get_parser() maps all 4 implemented parser names
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] Manual test: Create project, add a .txt file, verify manifest updated
- [ ] No unintended side effects in: store, embed, chunk, pipeline modules

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None — CLI commands already documented
- [ ] **PLAN.md:** Mark task 1.8 as `[x]` after completion

---

> **Last Updated:** 2026-02-28

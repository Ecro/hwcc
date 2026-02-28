# Plan: Phase 1 task 1.4 — Markdown/text passthrough parser

## Scope Declaration
- **Type:** feature
- **Single Concern:** Add parsers for markdown and plain text files that normalize content and extract metadata, following the existing `BaseParser` ABC contract
- **Phase:** 1 (Document Ingestion)
- **Complexity:** Low
- **Risk:** Low

## Problem Statement
**What:** Implement two parsers (`MarkdownParser`, `TextParser`) that handle `.md`/`.markdown` and `.txt`/`.text` files respectively, transforming them into `ParseResult` objects ready for the chunking pipeline.

**Why:** The pipeline currently handles PDF and SVD files but cannot ingest markdown or plain text documentation. Task 1.4 from PLAN.md specifies: normalize whitespace and encoding, detect and preserve code blocks, extract front-matter metadata if present.

**Success:** `hwcc add notes.md` and `hwcc add readme.txt` produce valid `ParseResult` objects with normalized content, extracted front-matter metadata, and correct doc_type. All tests pass.

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/ingest/markdown.py` | create | New `MarkdownParser` class |
| `src/hwcc/ingest/text.py` | create | New `TextParser` class |
| `src/hwcc/ingest/__init__.py` | modify | Export new parsers |
| `tests/test_ingest_markdown.py` | create | Tests for MarkdownParser |
| `tests/test_ingest_text.py` | create | Tests for TextParser |
| `tests/fixtures/sample.md` | create | Sample markdown fixture |
| `tests/fixtures/sample_frontmatter.md` | create | Markdown fixture with YAML front-matter |
| `tests/fixtures/sample.txt` | create | Sample plain text fixture |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `MarkdownParser` | Future `hwcc add` command (task 1.8), `Pipeline.process()` | `BaseParser` (base), `ParseResult` (types), `ParseError` (exceptions) |
| `TextParser` | Future `hwcc add` command (task 1.8), `Pipeline.process()` | `BaseParser` (base), `ParseResult` (types), `ParseError` (exceptions) |
| `ingest/__init__.py` | Any consumer importing from `hwcc.ingest` | New parser modules |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Parse (this) | None — these are new leaf parsers | Chunker (task 1.5) will receive `ParseResult` from these parsers |

## NON-GOALS (Explicitly Out of Scope)
- [ ] `detect.py` — already maps `.md`/`.txt` extensions; no changes needed
- [ ] `pipeline.py` — pipeline composition; parser routing is task 1.8
- [ ] `config.py` — no new config fields needed
- [ ] `cli.py` — CLI `hwcc add` command is task 1.8
- [ ] HTML-to-markdown conversion — separate parser for `.html` files
- [ ] Image extraction from markdown — future concern
- [ ] Link resolution/validation — not part of passthrough parsing

## Technical Approach

### Option A: Minimal passthrough with front-matter extraction (Recommended)
Both parsers read file content, normalize whitespace/encoding, and return a `ParseResult`. The `MarkdownParser` additionally extracts YAML front-matter (the `---` delimited block at the top of markdown files) into metadata and preserves code blocks as-is.

- **Pros:** Simple, deterministic, no external dependencies beyond stdlib, follows existing parser patterns exactly
- **Cons:** None significant — passthrough parsers are intentionally simple

### Front-matter parsing approach
Use a minimal hand-rolled parser (split on `---` boundaries) rather than adding a `python-frontmatter` or `pyyaml` dependency. YAML front-matter in hardware docs is simple key-value pairs. If the front-matter is valid YAML, parse it; if not, treat the whole file as content. This avoids a new dependency for a trivial feature.

**Rationale:** The existing codebase avoids unnecessary dependencies (SVD parser lazy-imports `cmsis-svd`, PDF parser lazy-imports `pymupdf`/`pdfplumber`). Front-matter is simple enough to handle with `yaml` from stdlib... except Python stdlib doesn't include YAML. However, `pyyaml` is already a transitive dependency of several existing deps (chromadb, etc.). We'll use a safe `yaml.safe_load()` with a try/except fallback — if PyYAML isn't available, front-matter is stored as raw text.

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Create test fixtures | `tests/fixtures/sample.md`, `sample_frontmatter.md`, `sample.txt` | Small representative files for testing |
| 2 | Implement `MarkdownParser` | `src/hwcc/ingest/markdown.py` | Parse markdown files: read with UTF-8, normalize whitespace, extract YAML front-matter, preserve code blocks, return `ParseResult` |
| 3 | Implement `TextParser` | `src/hwcc/ingest/text.py` | Parse plain text files: read with UTF-8, normalize whitespace, return `ParseResult` |
| 4 | Update `__init__.py` exports | `src/hwcc/ingest/__init__.py` | Add `MarkdownParser` and `TextParser` to `__all__` and imports |
| 5 | Write MarkdownParser tests | `tests/test_ingest_markdown.py` | Full test suite for MarkdownParser |
| 6 | Write TextParser tests | `tests/test_ingest_text.py` | Full test suite for TextParser |
| 7 | Run full test suite | — | `pytest tests/ -v` to verify no regressions |

## Implementation Details

### MarkdownParser behavior
1. **Read file** with UTF-8 encoding (with fallback to `errors="replace"`)
2. **Extract YAML front-matter**: detect `---` at line 1, find closing `---`, parse with `yaml.safe_load()` if available, store as `ParseResult.metadata` tuples
3. **Normalize whitespace**: collapse 3+ consecutive blank lines to 2, strip trailing whitespace per line, ensure single trailing newline
4. **Preserve code blocks**: fenced code blocks (``` and ~~~) pass through unchanged
5. **Generate doc_id**: `{stem}_md` pattern (matching PDF's `{stem}_pdf` and SVD's `{stem}_svd`)
6. **Set doc_type**: `"markdown"`
7. **Extract title**: first `# heading` in content, or front-matter `title` field, or filename stem

### TextParser behavior
1. **Read file** with UTF-8 encoding (with fallback to `errors="replace"`)
2. **Normalize whitespace**: collapse 3+ consecutive blank lines to 2, strip trailing whitespace per line, ensure single trailing newline
3. **Generate doc_id**: `{stem}_txt` pattern
4. **Set doc_type**: `"text"`
5. **Extract title**: first non-empty line, or filename stem
6. **No front-matter extraction** — plain text has no standard metadata format

### Shared patterns (following existing parsers)
- `from __future__ import annotations` at top
- `TYPE_CHECKING` guard for `Path` and `HwccConfig`
- `__all__` export list
- `logger = logging.getLogger(__name__)`
- `ParseError` for file not found / read errors
- `supported_extensions()` returns `frozenset`
- `can_parse()` inherited from `BaseParser`

### File size safety
Both parsers will enforce a reasonable max file size (50 MB) to prevent accidental ingestion of huge files. This follows `PdfParser.MAX_FILE_SIZE` pattern.

## Test Plan

### Unit Tests — MarkdownParser
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `parse()` returns `ParseResult` instance | `tests/test_ingest_markdown.py` | unit |
| 2 | `doc_type` is `"markdown"` | `tests/test_ingest_markdown.py` | unit |
| 3 | `doc_id` follows `{stem}_md` pattern | `tests/test_ingest_markdown.py` | unit |
| 4 | `source_path` matches input path | `tests/test_ingest_markdown.py` | unit |
| 5 | Content preserves code blocks unchanged | `tests/test_ingest_markdown.py` | unit |
| 6 | Content normalizes excessive blank lines | `tests/test_ingest_markdown.py` | unit |
| 7 | Trailing whitespace stripped from lines | `tests/test_ingest_markdown.py` | unit |
| 8 | YAML front-matter extracted into metadata | `tests/test_ingest_markdown.py` | unit |
| 9 | Front-matter `title` field used as ParseResult title | `tests/test_ingest_markdown.py` | unit |
| 10 | First `# heading` used as title when no front-matter | `tests/test_ingest_markdown.py` | unit |
| 11 | Filename stem used as title when no heading or front-matter | `tests/test_ingest_markdown.py` | unit |
| 12 | Front-matter stripped from content body | `tests/test_ingest_markdown.py` | unit |
| 13 | `supported_extensions()` returns `.md` and `.markdown` | `tests/test_ingest_markdown.py` | unit |
| 14 | `can_parse()` returns True for `.md` files | `tests/test_ingest_markdown.py` | unit |
| 15 | `can_parse()` returns False for `.pdf` files | `tests/test_ingest_markdown.py` | unit |
| 16 | Raises `ParseError` for non-existent file | `tests/test_ingest_markdown.py` | unit |
| 17 | Empty file returns empty content | `tests/test_ingest_markdown.py` | unit |
| 18 | Invalid front-matter treated as content | `tests/test_ingest_markdown.py` | unit |
| 19 | UTF-8 encoding with special characters | `tests/test_ingest_markdown.py` | unit |

### Unit Tests — TextParser
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `parse()` returns `ParseResult` instance | `tests/test_ingest_text.py` | unit |
| 2 | `doc_type` is `"text"` | `tests/test_ingest_text.py` | unit |
| 3 | `doc_id` follows `{stem}_txt` pattern | `tests/test_ingest_text.py` | unit |
| 4 | Content normalizes excessive blank lines | `tests/test_ingest_text.py` | unit |
| 5 | Trailing whitespace stripped from lines | `tests/test_ingest_text.py` | unit |
| 6 | First non-empty line used as title | `tests/test_ingest_text.py` | unit |
| 7 | Filename stem used as title for whitespace-only content | `tests/test_ingest_text.py` | unit |
| 8 | `supported_extensions()` returns `.txt` and `.text` | `tests/test_ingest_text.py` | unit |
| 9 | `can_parse()` returns True for `.txt` files | `tests/test_ingest_text.py` | unit |
| 10 | `can_parse()` returns False for `.md` files | `tests/test_ingest_text.py` | unit |
| 11 | Raises `ParseError` for non-existent file | `tests/test_ingest_text.py` | unit |
| 12 | Empty file returns empty content | `tests/test_ingest_text.py` | unit |
| 13 | UTF-8 encoding with special characters | `tests/test_ingest_text.py` | unit |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Parse a markdown file with front-matter and code blocks | ParseResult with metadata, preserved code blocks, normalized whitespace | automated |
| 2 | Parse a plain text file | ParseResult with normalized content, title from first line | automated |
| 3 | Parse non-existent file | Raises ParseError | automated |
| 4 | Existing tests still pass (no regression) | All tests green | automated |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/ingest/__init__.py` | modify | Add imports and exports for MarkdownParser, TextParser |

## Files to Create
| File | Purpose |
|------|---------|
| `src/hwcc/ingest/markdown.py` | MarkdownParser implementation |
| `src/hwcc/ingest/text.py` | TextParser implementation |
| `tests/test_ingest_markdown.py` | MarkdownParser test suite |
| `tests/test_ingest_text.py` | TextParser test suite |
| `tests/fixtures/sample.md` | Test fixture: basic markdown file |
| `tests/fixtures/sample_frontmatter.md` | Test fixture: markdown with YAML front-matter |
| `tests/fixtures/sample.txt` | Test fixture: plain text file |

## Exit Criteria
```
□ MarkdownParser implements BaseParser ABC contract
□ TextParser implements BaseParser ABC contract
□ YAML front-matter extracted from markdown into metadata tuples
□ Code blocks preserved unchanged in markdown
□ Whitespace normalized (collapse blank lines, strip trailing)
□ Both parsers handle encoding issues gracefully
□ Tests pass: pytest tests/test_ingest_markdown.py tests/test_ingest_text.py
□ Full suite passes: pytest tests/ (no regressions)
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No unintended side effects in: detect.py, pipeline.py, config.py, cli.py

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None — markdown/text parsers already listed in §5.1
- [ ] **PLAN.md:** Mark task 1.4 as complete after implementation

---

> **Last Updated:** 2026-02-28

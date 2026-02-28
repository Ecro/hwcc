# Plan: Phase 1 Task 1.3 — PDF Parser with Table Extraction

## Scope Declaration
- **Type:** feature
- **Single Concern:** Implement `PdfParser(BaseParser)` that extracts text and tables from hardware PDF documents and produces high-quality structured markdown `ParseResult`
- **Phase:** 1 (Ingestion Parsers)
- **Complexity:** High
- **Risk:** Medium

### Concern Separation Rule
This change is ONLY about: PDF text + table extraction → structured markdown
This change is NOT about:
- Document type auto-detection (task 1.1)
- Chunking (task 1.5)
- SVD parser changes
- CLI `hwcc add` command wiring
- Embedding, storage, or compilation
- LLM-based enrichment or vision captioning
- Image extraction from PDFs

## Problem Statement
**What:** Implement a PDF parser that extracts text with section hierarchy and tables from hardware datasheets/reference manuals, producing clean markdown suitable for high-quality RAG.

**Why:** PDFs are the #1 document format for hardware docs (datasheets, reference manuals, errata, application notes). Without a quality PDF parser, hwcc can only process SVD files. The parser must produce markdown clean enough that downstream chunking and embedding yield accurate retrieval — register addresses, pin tables, electrical characteristics, timing parameters.

**Success:** `PdfParser().parse(Path("datasheet.pdf"), config)` returns a `ParseResult` with clean markdown where:
- Section headings map to `#`/`##`/`###` hierarchy
- Tables render as clean markdown tables with headers
- No duplicate content from table-text overlap
- No header/footer noise
- Page metadata preserved

## Quality-First Design Principles

> **User requirement: BEST QUALITY RAG is the top priority.**

| Principle | Implementation |
|-----------|---------------|
| Accurate heading hierarchy | Two-pass font analysis — scan all pages to detect heading font size tiers before extraction |
| No table-text double extraction | pdfplumber identifies table bounding boxes, PyMuPDF skips overlapping text blocks |
| Clean tables | pdfplumber extracts tables → markdown with proper headers, None-cell handling, whitespace cleanup |
| No noise | Header/footer removal via clip rectangles; page number stripping |
| Rich metadata | page_count, table_count, TOC structure, title, author |
| Section continuity | Track heading stack across page boundaries |

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `pyproject.toml` | modify | Add `pymupdf>=1.24`, `pdfplumber>=0.11` to dependencies |
| `src/hwcc/ingest/pdf.py` | create | `PdfParser` class with two-pass extraction |
| `src/hwcc/ingest/__init__.py` | modify | Export `PdfParser` |
| `tests/test_ingest_pdf.py` | create | Unit tests for PdfParser |
| `tests/fixtures/generate_pdf.py` | create | Script to generate test fixture PDF |
| `tests/fixtures/sample.pdf` | create | Generated test fixture (binary, ~2 pages) |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `PdfParser.parse()` | Pipeline, future `hwcc add` | PyMuPDF, pdfplumber, ParseResult |
| `PdfParser.supported_extensions()` | Registry, Pipeline | — |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Parse (ingest) | None — new parser | Produces `ParseResult` consumed by chunker (task 1.5) |

## NON-GOALS (Explicitly Out of Scope)
- [ ] `src/hwcc/ingest/svd.py` — SVD parser is complete, do not touch
- [ ] `src/hwcc/ingest/base.py` — BaseParser ABC is stable
- [ ] `src/hwcc/types.py` — ParseResult contract is stable
- [ ] `src/hwcc/cli.py` — CLI wiring is task 1.1
- [ ] `src/hwcc/chunk/` — Chunking is task 1.5
- [ ] Image extraction from PDFs — Future enhancement (requires vision LLM)
- [ ] OCR for scanned PDFs — Out of scope (different library, different approach)
- [ ] Multi-column layout detection — Complex, defer to future enhancement
- [ ] PDF form field extraction — Not relevant for datasheets

## Technical Approach

### Architecture: Two-Pass Font-Adaptive Extraction (Recommended)

**Pass 1 — Font Analysis (fast scan):**
- Iterate all pages with PyMuPDF `get_text("dict", flags=11)`
- Collect all unique `(font_size, is_bold)` pairs with frequency counts
- Determine body text size (most frequent font size)
- Map font sizes above body size to heading levels (h1 = largest, h2 = next, etc.)
- This adapts automatically to each PDF's font scheme

**Pass 2 — Extraction (full processing):**
- For each page, open both PyMuPDF and pdfplumber views
- Step A: pdfplumber `find_tables()` → get table bounding boxes + data
- Step B: PyMuPDF `get_text("dict", flags=11)` → text blocks with font info
- Step C: Filter text blocks — exclude any overlapping with table bounding boxes
- Step D: Classify text blocks — heading (by font tier) or body text
- Step E: Render page as markdown: headings, paragraphs, tables in page order (sorted by Y position)

**Table rendering:**
- Convert `list[list[str|None]]` to markdown table
- First row treated as header (with `|---|` separator)
- None cells → empty string
- Strip whitespace, collapse newlines within cells

**Header/footer removal:**
- Use `clip` parameter on `get_text()` — skip top 60pt and bottom 50pt
- These values handle typical datasheet headers (vendor logo, doc number) and footers (page numbers, revision)

**Safety checks (following SVD parser pattern):**
- Validate `%PDF-` magic header bytes
- Reject files > 200MB (configurable)
- Catch all library exceptions → wrap in `ParseError`

### Option B: Single-Pass (Rejected)
Single-pass processes each page independently without global font analysis. This means heading detection relies on absolute font size thresholds (e.g., "anything > 14pt is a heading") which fails across different vendor PDF styles. Rejected for quality reasons.

### Option C: pdfplumber-Only (Rejected)
pdfplumber can extract both text and tables, but its text extraction (via pdfminer) is significantly slower than PyMuPDF and produces lower-quality output for large documents. Rejected for both quality and performance reasons.

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Add PDF dependencies | `pyproject.toml` | Add `pymupdf>=1.24`, `pdfplumber>=0.11` to `[project.dependencies]` |
| 2 | Create fixture generator | `tests/fixtures/generate_pdf.py` | Script that creates `sample.pdf` using PyMuPDF — 2 pages with headings, body text, tables, headers/footers |
| 3 | Generate fixture | `tests/fixtures/sample.pdf` | Run generator, commit binary fixture |
| 4 | Write tests (RED) | `tests/test_ingest_pdf.py` | Full test suite — ParseResult fields, heading extraction, table extraction, header/footer removal, edge cases, error handling, formatting helpers |
| 5 | Implement PdfParser | `src/hwcc/ingest/pdf.py` | Two-pass parser: font analysis → extraction. Helpers: `_analyze_fonts()`, `_extract_page()`, `_render_table()`, `_classify_block()`, `_check_pdf_safety()` |
| 6 | Export PdfParser | `src/hwcc/ingest/__init__.py` | Add `PdfParser` to imports and `__all__` |
| 7 | Verify all checks | — | `pytest`, `ruff`, `mypy` |

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `parse()` returns ParseResult with correct fields (doc_id, doc_type="pdf", title, source_path) | `tests/test_ingest_pdf.py` | unit |
| 2 | Content is non-empty markdown string | `tests/test_ingest_pdf.py` | unit |
| 3 | Metadata contains page_count, table_count | `tests/test_ingest_pdf.py` | unit |
| 4 | Section headings detected and rendered as markdown `##`/`###` | `tests/test_ingest_pdf.py` | unit |
| 5 | Tables extracted as markdown tables with headers and separator | `tests/test_ingest_pdf.py` | unit |
| 6 | Table content NOT duplicated in body text | `tests/test_ingest_pdf.py` | unit |
| 7 | Headers/footers stripped from output | `tests/test_ingest_pdf.py` | unit |
| 8 | Body text paragraphs preserved | `tests/test_ingest_pdf.py` | unit |
| 9 | Headings sorted by hierarchy (larger font = higher level) | `tests/test_ingest_pdf.py` | unit |
| 10 | `supported_extensions()` returns `{".pdf"}` | `tests/test_ingest_pdf.py` | unit |
| 11 | `can_parse()` accepts `.pdf`, `.PDF`, rejects `.svd` | `tests/test_ingest_pdf.py` | unit |
| 12 | Nonexistent file raises ParseError | `tests/test_ingest_pdf.py` | unit |
| 13 | Non-PDF file raises ParseError | `tests/test_ingest_pdf.py` | unit |
| 14 | `%PDF-` magic header validation | `tests/test_ingest_pdf.py` | unit |
| 15 | Oversized file rejection (>200MB) | `tests/test_ingest_pdf.py` | unit |
| 16 | `_render_table()` formats markdown correctly | `tests/test_ingest_pdf.py` | unit |
| 17 | `_render_table()` handles None cells | `tests/test_ingest_pdf.py` | unit |
| 18 | Font tier mapping produces correct heading levels | `tests/test_ingest_pdf.py` | unit |
| 19 | Page with no tables produces text-only output | `tests/test_ingest_pdf.py` | unit |
| 20 | Page with no text (only tables) handled | `tests/test_ingest_pdf.py` | unit |
| 21 | Multi-page section continuity — heading stack tracks across pages | `tests/test_ingest_pdf.py` | unit |
| 22 | Empty PDF (0 pages) produces meaningful error or empty result | `tests/test_ingest_pdf.py` | unit |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Parse 2-page sample PDF | ParseResult with headings, tables, body text as clean markdown | automated |
| 2 | Table in output matches expected markdown format | `\| Header \| Header \|` with separator row | automated |
| 3 | Header/footer text absent from output | No "Page X of Y" or repeated vendor name in content | automated |
| 4 | Register table extracted with correct values | All cells present, no garbled content | automated |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `pyproject.toml` | modify | Add pymupdf and pdfplumber dependencies |
| `src/hwcc/ingest/__init__.py` | modify | Add PdfParser import and export |

## Files to Create
| File | Purpose |
|------|---------|
| `src/hwcc/ingest/pdf.py` | PdfParser implementation |
| `tests/test_ingest_pdf.py` | Unit tests |
| `tests/fixtures/generate_pdf.py` | Fixture generation script |
| `tests/fixtures/sample.pdf` | Generated test fixture (binary) |

## PdfParser Class Outline

```python
class PdfParser(BaseParser):
    """Parser for PDF documents (datasheets, reference manuals, app notes).

    Two-pass architecture for quality-first extraction:
    1. Font analysis pass — detect heading font size tiers
    2. Extraction pass — text + tables → structured markdown
    """

    # Configurable margins for header/footer removal (points)
    HEADER_MARGIN: int = 60   # ~0.83 inch from top
    FOOTER_MARGIN: int = 50   # ~0.69 inch from bottom
    MAX_FILE_SIZE: int = 200 * 1024 * 1024  # 200MB

    def parse(self, path: Path, config: HwccConfig) -> ParseResult: ...
    def supported_extensions(self) -> frozenset[str]: ...

    # Internal
    def _analyze_fonts(self, doc) -> dict[int, int]:
        """Pass 1: Build font_size → heading_level mapping."""
    def _extract_page(self, mu_page, plumb_page, font_map, heading_stack) -> str:
        """Pass 2: Extract one page as markdown."""
    def _render_table(self, table_data: list[list[str | None]]) -> str:
        """Render table data as markdown table."""
```

## Module-Level Helpers

```python
def _check_pdf_safety(path: Path) -> None:
    """Validate PDF magic header and file size."""

def _render_table(table_data: list[list[str | None]]) -> str:
    """Convert table data to markdown table with header separator."""

def _classify_block(block: dict, font_map: dict[float, int]) -> tuple[str, str]:
    """Classify a text block as 'heading' or 'body', return (type, text)."""

def _build_font_map(font_histogram: dict[tuple[float, bool], int]) -> dict[float, int]:
    """Convert font size histogram into font_size → heading_level mapping."""
```

## Exit Criteria
```
□ PdfParser.parse() returns valid ParseResult from sample PDF
□ Section headings correctly detected and rendered as markdown headings
□ Tables extracted as clean markdown tables with header rows
□ No table-text double extraction
□ Headers/footers stripped from output
□ Error handling: nonexistent file, non-PDF, corrupt PDF, oversized file
□ supported_extensions() returns frozenset({".pdf"})
□ can_parse() works correctly
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
- [ ] Manual test: Parse a real vendor datasheet (STM32 or similar) and inspect markdown output quality
- [ ] No unintended side effects in: SVD parser, existing tests, base classes

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None (PDF parser already documented in spec)
- [ ] **PLAN.md:** Check off task 1.3

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Table extraction fails on some datasheets | Medium | High | Use "lines" strategy (most datasheets have bordered tables); fallback to "text" strategy |
| Heading detection wrong for unusual fonts | Low | Medium | Two-pass font analysis adapts per document |
| Coordinate mismatch between PyMuPDF and pdfplumber | Low | High | Validate on fixture; both use top-origin in modern versions |
| Large PDFs cause memory issues | Low | Medium | Page-by-page processing, flags=11 to skip images |
| pdfplumber slow on large documents | Medium | Low | Only used for tables, not full text extraction |

---

> **Last Updated:** 2026-02-28

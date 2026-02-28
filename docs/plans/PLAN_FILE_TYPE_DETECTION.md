# Plan: Phase 1 Task 1.1 — File Type Detection

## Scope Declaration
- **Type:** feature
- **Single Concern:** File type detection, format classification, and document type inference for routing files to the correct parser
- **Phase:** Phase 1 (Document Ingestion)
- **Complexity:** Medium
- **Risk:** Low

## Scope Separation

This change is ONLY about: Detecting what kind of file was provided and what document type it represents.

This change is NOT about:
- Building new parsers (markdown, text, DTS, C/H — separate tasks 1.4+)
- Modifying the Pipeline class to support multi-parser dispatch
- Registering parsers in the registry
- Implementing `hwcc add` end-to-end
- Changing the CLI interface

## Problem Statement
**What:** Create a `detect.py` module in `src/hwcc/ingest/` that identifies file types by extension and magic bytes, maps them to parser names, and auto-classifies the semantic document type (datasheet, reference manual, errata, etc.).

**Why:** The `hwcc add` command needs to automatically route files to the correct parser and assign meaningful document types. Currently, parsers know their own extensions but there is no centralized detection or routing logic.

**Success:** Given any file path, the detection module returns a `FileInfo` with the file format, document type classification, and which parser should handle it.

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/ingest/detect.py` | create | New detection module with `detect_file_type()`, enums, and `FileInfo` |
| `src/hwcc/ingest/__init__.py` | modify | Export new public API from detect module |
| `tests/test_detect.py` | create | Unit tests for detection logic |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `detect_file_type()` | Future: `hwcc add` command, Pipeline dispatcher | `Path.suffix`, `Path.open()` for magic bytes |
| `FileFormat` enum | `detect.py` internals, future: registry routing | None |
| `DocType` constants | `detect.py` internals, future: manifest entries | None |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Pre-parse (detection) | None — this is the entry point | Informs which parser to use for parse stage |

## NON-GOALS (Explicitly Out of Scope)
- [ ] New parsers (markdown, text, DTS, C/H) — Task 1.4+
- [ ] Modifying `Pipeline` class for multi-parser dispatch — separate concern
- [ ] Registering parsers in `ProviderRegistry` — separate concern
- [ ] Implementing `hwcc add` command — Task 1.8
- [ ] Modifying `ParseResult` or `ChunkMetadata` types — they already use `str` which is compatible
- [ ] Adding external dependencies (python-magic, filetype) — manual magic bytes is sufficient

## Technical Approach

### Option A: Manual Magic Bytes + Extension Map (Recommended)
Use hardcoded extension-to-format mapping with manual magic byte confirmation for ambiguous cases. No new dependencies needed — the existing PDF parser already does `%PDF-` header checking internally.

- **Pros:** Zero new dependencies, simple, deterministic, testable, fast
- **Cons:** Must maintain magic byte signatures manually (but the set is small and stable)

### Option B: python-magic Library
Use `python-magic` (wraps libmagic) for MIME type detection, then map MIME types to formats.

- **Pros:** Handles exotic formats, widely used
- **Cons:** New dependency, requires libmagic system library (portability concern on Windows), overkill for ~15 known file types

**Decision:** Option A. The supported file types are well-known and stable. Manual checks are simpler and more reliable for this domain.

### Design Details

#### Enums (str-based for backward compatibility)

`FileFormat(str, Enum)` — structural file format:
- `PDF`, `SVD`, `MARKDOWN`, `TEXT`, `DEVICE_TREE`, `C_HEADER`, `C_SOURCE`, `RUST`, `HTML`, `JSON_FORMAT`, `YAML`, `CUBEMX`, `IMAGE`, `UNKNOWN`

`DocType(str, Enum)` — semantic document classification:
- `DATASHEET`, `REFERENCE_MANUAL`, `ERRATA`, `APP_NOTE`, `SCHEMATIC`, `SVD`, `DEVICE_TREE`, `CODE`, `DOCUMENTATION`, `UNKNOWN`

Using `str` enums means `DocType.DATASHEET == "datasheet"` evaluates to `True`, maintaining backward compatibility with existing `doc_type: str` fields in `ParseResult`, `ChunkMetadata`, and `DocumentEntry`.

#### FileInfo (frozen dataclass)

```python
@dataclass(frozen=True)
class FileInfo:
    path: Path
    format: FileFormat
    doc_type: DocType
    parser_name: str      # maps to registry key, e.g. "pdf", "svd"
    confidence: float     # 1.0 = extension match, 0.8 = magic bytes only
```

#### Detection Logic

1. **Extension check** (primary): Map `path.suffix.lower()` → `FileFormat`
2. **Magic byte check** (secondary): Read first 16 bytes to confirm or override
3. **SVD disambiguation**: `.xml` files need content check for `<device` tag
4. **Parser mapping**: `FileFormat` → parser name string
5. **Doc type classification**: Heuristic from filename patterns + file format

#### Magic Byte Signatures

| Signature | Format |
|-----------|--------|
| `%PDF-` | PDF |
| `\x89PNG\r\n\x1a\n` | IMAGE (PNG) |
| `\xff\xd8\xff` | IMAGE (JPEG) |
| `<?xml` + `<device` | SVD (confirmed XML+SVD) |

#### Document Type Heuristics

| Filename Pattern | Doc Type |
|------------------|----------|
| `*datasheet*`, `*_ds_*`, `*_ds.*` | datasheet |
| `*reference*`, `*ref_manual*`, `*_rm_*`, `*_rm.*` | reference_manual |
| `*errata*`, `*_es_*`, `*_es.*`, `*erratum*` | errata |
| `*app_note*`, `*appnote*`, `*_an_*`, `*_an.*` | app_note |
| `*schematic*` | schematic |
| `.svd` extension | svd |
| `.dts`/`.dtsi` extension | device_tree |
| `.c`/`.h`/`.rs` extension | code |
| `.md` extension | documentation |
| No match | unknown |

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Create `FileFormat` and `DocType` str enums | `src/hwcc/ingest/detect.py` | Define all supported file formats and document types as `str` enums for backward compat |
| 2 | Create `FileInfo` frozen dataclass | `src/hwcc/ingest/detect.py` | Detection result type with path, format, doc_type, parser_name, confidence |
| 3 | Implement extension mapping | `src/hwcc/ingest/detect.py` | `_EXTENSION_MAP: dict[str, FileFormat]` — maps lowercase extensions to formats |
| 4 | Implement parser name mapping | `src/hwcc/ingest/detect.py` | `_FORMAT_PARSER_MAP: dict[FileFormat, str]` — maps formats to parser registry keys |
| 5 | Implement magic byte checking | `src/hwcc/ingest/detect.py` | `_check_magic_bytes(path) -> FileFormat | None` — reads file header, returns format or None |
| 6 | Implement doc type classification | `src/hwcc/ingest/detect.py` | `classify_doc_type(path, format) -> DocType` — heuristic from filename patterns + format |
| 7 | Implement main `detect_file_type()` | `src/hwcc/ingest/detect.py` | Public function: extension check → magic bytes → parser mapping → doc type → `FileInfo` |
| 8 | Implement `get_supported_extensions()` | `src/hwcc/ingest/detect.py` | Returns all known extensions for user-facing help/validation |
| 9 | Update `__init__.py` exports | `src/hwcc/ingest/__init__.py` | Export `detect_file_type`, `FileFormat`, `DocType`, `FileInfo` |
| 10 | Write unit tests | `tests/test_detect.py` | Full test coverage for all detection scenarios |

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `detect_file_type` returns correct `FileFormat` for each known extension (.pdf, .svd, .md, .txt, .dts, .dtsi, .h, .c, .rs, .html, .json, .yaml, .yml, .ioc, .png, .jpg) | `tests/test_detect.py` | unit |
| 2 | `detect_file_type` returns `UNKNOWN` for unrecognized extensions | `tests/test_detect.py` | unit |
| 3 | `detect_file_type` is case-insensitive (`.PDF`, `.Svd`, `.MD`) | `tests/test_detect.py` | unit |
| 4 | `detect_file_type` maps each format to correct `parser_name` | `tests/test_detect.py` | unit |
| 5 | Magic bytes: PDF file with `.pdf` extension → PDF format, confidence 1.0 | `tests/test_detect.py` | unit |
| 6 | Magic bytes: PDF file with wrong extension (e.g. `.bin`) → PDF format, confidence 0.8 | `tests/test_detect.py` | unit |
| 7 | Magic bytes: non-PDF file with `.pdf` extension → PDF format (extension wins, but lower confidence) | `tests/test_detect.py` | unit |
| 8 | SVD XML disambiguation: `.xml` file containing `<device` → SVD format | `tests/test_detect.py` | unit |
| 9 | Doc type classification: filename containing "datasheet" → `DocType.DATASHEET` | `tests/test_detect.py` | unit |
| 10 | Doc type classification: filename containing "reference" or "rm_" → `DocType.REFERENCE_MANUAL` | `tests/test_detect.py` | unit |
| 11 | Doc type classification: filename containing "errata" or "es_" → `DocType.ERRATA` | `tests/test_detect.py` | unit |
| 12 | Doc type classification: filename containing "app_note" or "an_" → `DocType.APP_NOTE` | `tests/test_detect.py` | unit |
| 13 | Doc type classification: `.svd` files → `DocType.SVD` regardless of filename | `tests/test_detect.py` | unit |
| 14 | Doc type classification: `.dts`/`.dtsi` → `DocType.DEVICE_TREE` | `tests/test_detect.py` | unit |
| 15 | Doc type classification: `.c`/`.h`/`.rs` → `DocType.CODE` | `tests/test_detect.py` | unit |
| 16 | Doc type classification: `.md` → `DocType.DOCUMENTATION` | `tests/test_detect.py` | unit |
| 17 | Doc type classification: no filename pattern match → `DocType.UNKNOWN` | `tests/test_detect.py` | unit |
| 18 | `detect_file_type` raises `ParseError` for non-existent file | `tests/test_detect.py` | unit |
| 19 | `get_supported_extensions()` returns all known extensions | `tests/test_detect.py` | unit |
| 20 | `FileFormat` and `DocType` are str-compatible (e.g. `DocType.DATASHEET == "datasheet"`) | `tests/test_detect.py` | unit |
| 21 | `FileInfo` is frozen (immutable) | `tests/test_detect.py` | unit |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Pass a `.pdf` path to `detect_file_type()` | Returns `FileInfo(format=PDF, doc_type=..., parser_name="pdf")` | automated |
| 2 | Pass a `.svd` path to `detect_file_type()` | Returns `FileInfo(format=SVD, doc_type=SVD, parser_name="svd")` | automated |
| 3 | Pass a file with no extension | Falls back to magic bytes or returns UNKNOWN | automated |
| 4 | All returned enums work as plain strings | `str(DocType.DATASHEET) == "datasheet"` | automated |

## Files to Create
| File | Purpose |
|------|---------|
| `src/hwcc/ingest/detect.py` | File type detection module |
| `tests/test_detect.py` | Unit tests for detection |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/ingest/__init__.py` | modify | Add exports for `detect_file_type`, `FileFormat`, `DocType`, `FileInfo` |

## Exit Criteria
```
□ detect_file_type() correctly identifies all 16+ supported extensions
□ Magic byte checking works for PDF, PNG, JPEG, SVD-XML
□ Document type heuristics classify filenames correctly
□ str enums are backward-compatible with existing str fields
□ All 21 unit tests pass
□ ruff check passes
□ mypy passes
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/test_detect.py -v`
- [ ] All tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/hwcc/ingest/detect.py tests/test_detect.py`
- [ ] Format correct: `ruff format --check src/hwcc/ingest/detect.py tests/test_detect.py`
- [ ] Types correct: `mypy src/hwcc/ingest/detect.py`
- [ ] No unintended side effects in: Pipeline, BaseParser, types.py, cli.py, config.py

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None — §5.1 already describes detection, implementation matches spec
- [ ] **PLAN.md:** Mark task 1.1 as complete after execution

---

> **Last Updated:** 2026-02-28

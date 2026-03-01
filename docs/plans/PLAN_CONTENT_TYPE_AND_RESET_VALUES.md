# Plan: Tasks 1.11 & 1.12 — Content Type Taxonomy + SVD Field Reset Values

## Scope Declaration

### Change Intent
- **Type:** feature
- **Single Concern:** Improve chunk classification and SVD output fidelity
- **Two tightly-related improvements:**
  - 1.11: Extend `_detect_content_type()` from 4 generic types to 12 hardware-domain types
  - 1.12: Compute per-field reset values from register-level reset in SVD output

### Concern Separation Rule
This change is ONLY about: chunk content classification and SVD field reset value computation
This change is NOT about: compile output, template changes, MCP search, store queries, config changes

---

## Problem Statement

**What:** The chunker classifies all content into just 4 types (`code`, `table`, `section`, `prose`) — too coarse for hardware docs. And SVD field tables show `—` for reset values despite the data being available.

**Why:**
- Content type taxonomy enables Phase 2 features (targeted retrieval for peripheral context compilation, usage pattern extraction via `config_procedure` type matching)
- Per-field reset values are critical for engineers understanding peripheral state after reset — a P0 strategic gap

**Success:** `_detect_content_type()` returns 12 hardware-aware types via regex. SVD field tables show computed hex reset values.

---

## Impact Analysis

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/chunk/markdown.py` | modify | Add 6 compiled regex patterns, rewrite `_detect_content_type()` with priority-ordered detection |
| `src/hwcc/ingest/svd.py` | modify | Add `register_reset_value` param to `_render_field_table()`, compute per-field resets, add `_compute_field_reset()` helper |
| `tests/test_chunk.py` | modify | Expand `TestContentType` with tests for all 12 types |
| `tests/test_ingest_svd.py` | modify | Update field reset assertions from `—` to computed hex values, add dedicated reset computation tests |

### Dependency Chain

| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `_detect_content_type()` | `MarkdownChunker._do_chunk()` line 380 | New regex patterns (module-level) |
| `_render_field_table()` | `_render_peripheral()` line 210 | `_format_bit_range()`, `_format_access()`, new `_compute_field_reset()` |
| `_compute_field_reset()` | `_render_field_table()` | None (pure computation) |

### Pipeline Impact

| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Chunk (1.11) | None — classification is post-split | `ChunkMetadata.content_type` values change from 4 to 12 possible strings. ChromaDB stores these as metadata. Compile stage can filter by new types in Phase 2. |
| Ingest/Parse (1.12) | None — SVD parser is independent | Markdown output changes: field reset column shows hex values instead of `—`. Chunks downstream contain richer content. |

### Backward Compatibility

- **1.11:** `content_type` is a free-text string field in `ChunkMetadata`. No enum constraint. Existing stored chunks with old types remain valid. New chunks get more specific types. The 4 original types are still used (code, table, section, prose) as fallbacks, so no downstream breakage.
- **1.12:** Only changes rendered markdown content — no API or data contract changes.

---

## NON-GOALS (Explicitly Out of Scope)

- [ ] `src/hwcc/compile/` — No template or compiler changes
- [ ] `src/hwcc/store/` — No query changes
- [ ] `src/hwcc/config.py` — No config changes
- [ ] `src/hwcc/types.py` — No data contract changes
- [ ] `api_reference` content type — Deferred to Phase 5 (requires C header parsing)
- [ ] Using new content types for retrieval filtering — That's Phase 2 (tasks 2.7, 2.8)

---

## Technical Approach

### Task 1.11: Content Type Taxonomy

**New module-level compiled regex patterns:**

```python
# Register-related keywords (tables and prose)
_REGISTER_KW_RE = re.compile(
    r"\b(register|offset|reset\s*value|bit\s*field|"
    r"read.write|read.only|write.only|base\s*address)\b"
    r"|0x[0-9A-Fa-f]{4,}",
    re.IGNORECASE,
)

# Timing specification keywords
_TIMING_KW_RE = re.compile(
    r"\b\d+\s*(?:ns|µs|us|ms|MHz|kHz|GHz)\b"
    r"|\b(?:setup\s*time|hold\s*time|propagation\s*delay|"
    r"clock\s*(?:speed|frequency|period)|baud\s*rate)\b",
    re.IGNORECASE,
)

# Configuration/initialization procedure keywords
_CONFIG_PROC_KW_RE = re.compile(
    r"\b(?:step\s*\d|initialization\s*sequence|configure\s*the|"
    r"enable\s*the|programming\s*procedure|following\s*steps|"
    r"must\s*be\s*set|should\s*be\s*configured)\b",
    re.IGNORECASE,
)

# Errata keywords
_ERRATA_KW_RE = re.compile(
    r"\b(?:errat(?:a|um)|workaround|limitation|silicon\s*bug|"
    r"advisory|known\s*issue)\b"
    r"|ES\d{4}",
    re.IGNORECASE,
)

# Pin mapping keywords
_PIN_MAP_KW_RE = re.compile(
    r"\b(?:alternate\s*function|AF\d+|"
    r"pin\s*(?:mapping|assignment|configuration)|remap)\b"
    r"|\bGPIO[A-Z]\d*\b",
    re.IGNORECASE,
)

# Electrical specification keywords
_ELECTRICAL_KW_RE = re.compile(
    r"\b\d+\.?\d*\s*(?:mA|µA|uA|kΩ)\b"
    r"|\b(?:power\s*supply|current\s*consumption|"
    r"voltage\s*(?:range|level))\b"
    r"|\bV[DCS]{2}\b",
    re.IGNORECASE,
)
```

**Rewritten `_detect_content_type()`:**

```python
def _detect_content_type(self, text: str) -> str:
    """Detect the primary content type of a chunk.

    Priority order: structural types first (code, table subtypes),
    then domain-specific prose types, then generic fallbacks.
    """
    # 1. Code blocks (unambiguous structural marker)
    if _FENCE_RE.search(text):
        return "code"

    # 2. Table-based types (structural + keyword refinement)
    if _TABLE_SEP_RE.search(text):
        if _REGISTER_KW_RE.search(text):
            return "register_table"
        if _PIN_MAP_KW_RE.search(text):
            return "pin_mapping"
        if _ELECTRICAL_KW_RE.search(text):
            return "electrical_spec"
        if _TIMING_KW_RE.search(text):
            return "timing_spec"
        return "table"

    # 3. Domain-specific prose types (keyword-based)
    if _ERRATA_KW_RE.search(text):
        return "errata"
    if _CONFIG_PROC_KW_RE.search(text):
        return "config_procedure"
    if _REGISTER_KW_RE.search(text):
        return "register_description"
    if _TIMING_KW_RE.search(text):
        return "timing_spec"
    if _PIN_MAP_KW_RE.search(text):
        return "pin_mapping"
    if _ELECTRICAL_KW_RE.search(text):
        return "electrical_spec"

    # 4. Generic structural fallbacks
    if _HEADING_RE.search(text):
        return "section"
    return "prose"
```

**Key design decisions:**
- Errata checked before register_description in prose — errata docs often mention registers but the errata classification is more specific/useful
- `config_procedure` before `register_description` — initialization sequences mention registers but the procedure context is more valuable
- `api_reference` omitted — requires C header parsing, deferred to Phase 5
- Tables get subtype refinement first since table structure + keywords is higher confidence than prose + keywords

### Task 1.12: SVD Field Reset Values

**New helper function:**

```python
def _compute_field_reset(register_reset: int, bit_offset: int, bit_width: int) -> str:
    """Compute and format a field's reset value from the register reset value."""
    mask = (1 << bit_width) - 1
    value = (register_reset >> bit_offset) & mask
    hex_width = max(1, (bit_width + 3) // 4)
    return f"0x{value:0{hex_width}X}"
```

**Modified `_render_field_table()` signature:**

```python
def _render_field_table(
    self,
    register_name: str,
    fields: Sequence[SvdFieldItem],
    register_reset_value: int | None = None,
) -> list[str]:
```

**Modified field reset line:**

```python
# Before:
reset = "—"

# After:
if register_reset_value is not None:
    reset = _compute_field_reset(register_reset_value, bit_offset, bit_width)
else:
    reset = "—"
```

**Modified call site in `_render_peripheral()`:**

```python
# Before:
lines.extend(self._render_field_table(reg.name or "?", reg.fields))

# After:
lines.extend(self._render_field_table(reg.name or "?", reg.fields, reg.reset_value))
```

---

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Add hardware-domain regex patterns | `chunk/markdown.py` | 6 new compiled regex patterns at module level |
| 2 | Rewrite `_detect_content_type()` | `chunk/markdown.py` | Priority-ordered detection with table subtype refinement |
| 3 | Add content type tests | `tests/test_chunk.py` | Tests for all 12 types (existing `TestContentType` expanded) |
| 4 | Add `_compute_field_reset()` helper | `ingest/svd.py` | Pure function: register_reset × bit_offset × bit_width → hex string |
| 5 | Update `_render_field_table()` | `ingest/svd.py` | Add `register_reset_value` param, compute per-field resets |
| 6 | Update call site | `ingest/svd.py` | Pass `reg.reset_value` to `_render_field_table()` |
| 7 | Update SVD tests | `tests/test_ingest_svd.py` | Test computed field resets (CR fields=0x0, SR.BUSY=0x1, SR.OVF=0x0) |
| 8 | Run full test suite | — | `pytest tests/` — verify no regressions |

---

## Test Plan

### Unit Tests — Task 1.11

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `test_register_table_type` — table with register keywords → `register_table` | `tests/test_chunk.py` | unit |
| 2 | `test_register_description_type` — prose with register keywords → `register_description` | `tests/test_chunk.py` | unit |
| 3 | `test_timing_spec_type` — text with timing values → `timing_spec` | `tests/test_chunk.py` | unit |
| 4 | `test_config_procedure_type` — text with init steps → `config_procedure` | `tests/test_chunk.py` | unit |
| 5 | `test_errata_type` — text with errata keywords → `errata` | `tests/test_chunk.py` | unit |
| 6 | `test_pin_mapping_type` — table with GPIO/AF keywords → `pin_mapping` | `tests/test_chunk.py` | unit |
| 7 | `test_electrical_spec_type` — text with voltage/current → `electrical_spec` | `tests/test_chunk.py` | unit |
| 8 | `test_timing_spec_table_type` — table with timing values → `timing_spec` | `tests/test_chunk.py` | unit |
| 9 | `test_code_type_unchanged` — existing code detection preserved | `tests/test_chunk.py` | unit |
| 10 | `test_plain_table_type` — table without domain keywords → `table` | `tests/test_chunk.py` | unit |
| 11 | `test_section_type_unchanged` — heading-only chunk → `section` | `tests/test_chunk.py` | unit |
| 12 | `test_prose_type_unchanged` — plain text → `prose` | `tests/test_chunk.py` | unit |
| 13 | `test_errata_over_register` — errata mentioning registers → `errata` (priority test) | `tests/test_chunk.py` | unit |

### Unit Tests — Task 1.12

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 14 | `test_compute_field_reset_single_bit` — 1-bit field from known reset | `tests/test_ingest_svd.py` | unit |
| 15 | `test_compute_field_reset_multi_bit` — multi-bit field extraction | `tests/test_ingest_svd.py` | unit |
| 16 | `test_compute_field_reset_nonzero` — SR.BUSY from reset=0x1 → `0x1` | `tests/test_ingest_svd.py` | unit |
| 17 | `test_field_reset_none_register` — register with no reset → `—` preserved | `tests/test_ingest_svd.py` | unit |
| 18 | `test_field_table_shows_computed_resets` — integration: parsed SVD shows hex resets | `tests/test_ingest_svd.py` | integration |

### Acceptance Criteria (Testable)

| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Chunk a register table from SVD output | `content_type == "register_table"` | automated |
| 2 | Chunk errata text | `content_type == "errata"` | automated |
| 3 | Parse sample.svd, check SR.BUSY reset | Field shows `0x1` not `—` | automated |
| 4 | Parse SVD with register reset=0x00000000 | All fields show `0x0` | automated |
| 5 | All existing tests pass | No regressions | automated |

---

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/chunk/markdown.py` | modify | Add 6 regex patterns, rewrite `_detect_content_type()` |
| `src/hwcc/ingest/svd.py` | modify | Add `_compute_field_reset()`, update `_render_field_table()` signature + logic |
| `tests/test_chunk.py` | modify | Expand `TestContentType` with 11 new test methods |
| `tests/test_ingest_svd.py` | modify | Add `TestFieldResetComputation` class, update existing assertions |

---

## Exit Criteria

```
□ _detect_content_type() returns 12 distinct content types
□ All 6 regex patterns compile without error
□ SVD field tables show computed hex reset values
□ SR.BUSY field in sample.svd shows 0x1 (not —)
□ All existing tests pass (no regressions)
□ New tests cover all 12 content types
□ New tests cover field reset computation edge cases
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched
```

## Verification Strategy

- [ ] Tests pass: `pytest tests/test_chunk.py tests/test_ingest_svd.py -v`
- [ ] Full suite: `pytest tests/`
- [ ] Lint: `ruff check src/hwcc/chunk/markdown.py src/hwcc/ingest/svd.py`
- [ ] Types: `mypy src/hwcc/chunk/markdown.py src/hwcc/ingest/svd.py`

## Document Updates Needed

- [ ] **TECH_SPEC.md:** None — §5.4 and §5.5 already describe the target state
- [ ] **PLAN.md:** Mark tasks 1.11 and 1.12 as complete after implementation

---

> **Last Updated:** 2026-03-01

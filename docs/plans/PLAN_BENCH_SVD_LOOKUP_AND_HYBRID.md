# PLAN: Bench Mode C (SVD Lookup) & Mode D (Hybrid Router)

**Project:** hwcc
**Task:** Add `svd_lookup` and `hybrid` bench conditions
**Priority:** Medium
**Created:** 2026-03-14

---

## Executive Summary

> **TL;DR:** Add two new bench conditions: `svd_lookup` (LLM-free direct SVD answer) and `hybrid` (per-question routing to the best condition).

### What We're Doing

Adding two bench conditions from the blog post analysis:

- **Mode C (`svd_lookup`):** For SVD-category questions (base_address, register_offset, bit_field, reset_value, access_type), answer directly from parsed SVD data. No LLM call. Zero hallucination, sub-millisecond. For non-SVD questions, returns "unanswerable."
- **Mode D (`hybrid`):** Per-question rule-based router that dispatches each question to the best condition. SVD questions go to `svd_lookup`. Datasheet/procedural questions go to `hwcc_rag` or `hwcc_full`. Achieves high accuracy at low cost.

### Why It Matters

The blog shows Mode C gets 12/12 on register facts at $0.009/query, and Mode D gets 73% accuracy at 2.5% the cost of full context. These conditions validate hwcc's core value proposition: structured SVD lookup beats LLMs for register questions.

### Key Decisions

- **SVD lookup bypasses LLM entirely** — New code path in runner, not a special provider. The runner already has per-condition branching for `hwcc_rag`; this extends the same pattern.
- **SVD lookup uses the dataset's source_svd** — Parses the same SVD file that generated the questions for a fair apples-to-apples test.
- **Hybrid router is rule-based** — No LLM classification call for routing. Question `category` field is sufficient for the benchmark (we generated the questions, so we know the category). For real-world use, regex patterns on the question text would be the fallback.
- **Both conditions reuse existing scoring** — Answers from SVD lookup flow through the same `score_answer()` pipeline.

### Estimated Impact

- **Complexity:** Medium
- **Risk Level:** Low
- **Files Changed:** ~5 files
- **Single Concern:** Bench conditions only. No changes to pipeline, parsers, or store.

---

## REVIEW CHECKLIST - Action Required

### Critical Decisions to Verify

- [ ] **Architecture:** SVD lookup bypasses `_ask_question()` in the runner loop — is this acceptable, or should we create a special `BaseBenchProvider` subclass?
- [ ] **API Changes:** `run_benchmark()` gets new optional `svd_path` param — backward compatible?
- [ ] **Scoring:** SVD lookup answers should go through same `score_answer()` / `score_answer_partial()` pipeline — correct?
- [ ] **Hybrid sub-conditions:** Hybrid needs access to SearchEngine (for RAG fallback) AND svd_path (for SVD lookup) — should both be optional?

### Code Impact to Review

- [ ] **`src/hwcc/bench/runner.py`** — Two new code paths in the question loop (svd_lookup, hybrid)
- [ ] **`src/hwcc/bench/svd_lookup.py`** — New file: direct SVD answer extraction
- [ ] **`src/hwcc/cli.py`** — New `--svd-path` CLI option for bench run

### Testing Coverage

- [ ] SVD lookup accuracy on all 5 SVD categories (base_address, register_offset, bit_field, reset_value, access_type)
- [ ] SVD lookup returns "unanswerable" for non-SVD categories
- [ ] Hybrid routing dispatches correctly per category
- [ ] Hybrid falls back gracefully when sub-conditions are unavailable

### Validator Critiques (Review Before /execute)

- [ ] **[3/3] Hybrid fallback condition selection** (Technical Design §4) — Verify the defined fallback chain (hwcc_full > hwcc_hot > no_context) covers all edge cases, especially when conditions list is filtered
- [ ] **[3/3] BenchResponse schema for svd_lookup** (Technical Design) — Verify the specified field values for answerable/unanswerable paths produce correct scoring and report output

---

## Problem Analysis

### What

Add two new bench conditions that complete the blog's 4-mode evaluation framework:

| Condition | How it answers | LLM? | Best for |
|-----------|---------------|-------|----------|
| `no_context` | LLM with no docs | Yes | Baseline |
| `hwcc_hot` | LLM + hot.md | Yes | Quick context |
| `hwcc_full` | LLM + all peripherals | Yes | Full context (Mode B) |
| `raw_pdf` | LLM + raw PDF text | Yes | Unprocessed docs |
| `hwcc_rag` | LLM + per-Q vector search | Yes | Mode A |
| **`svd_lookup`** | **Direct SVD parse** | **No** | **Mode C — register facts** |
| **`hybrid`** | **Route per-Q to best** | **Mixed** | **Mode D — cost-optimized** |

### Why

Without these, the bench only measures LLM accuracy under different context strategies. Mode C proves that structured data beats LLMs for register lookups. Mode D shows the optimal cost/accuracy tradeoff.

### Success Criteria

- [ ] `svd_lookup` gets 100% on SVD-generated questions (it reads the same source)
- [ ] `svd_lookup` returns score 0.0 for non-SVD categories (doesn't guess)
- [ ] `hybrid` routes SVD categories to svd_lookup, others to hwcc_rag/hwcc_full
- [ ] Both conditions appear in bench reports with correct metrics
- [ ] All existing tests still pass (backward compatible)

---

## Code Review

### Current State

The runner loop has a clean per-condition / per-question structure:

```
for condition in conditions:
    for question in dataset.questions:
        effective_condition = condition
        if condition.name == "hwcc_rag":
            effective_condition = _build_rag_condition_from_engine(...)
        response, tokens = _ask_question(question, effective_condition, provider)
```

This pattern already supports per-question condition modification. Extending it for `svd_lookup` and `hybrid` follows the same model.

### Affected Components

| File | Change |
|------|--------|
| `src/hwcc/bench/svd_lookup.py` | **NEW** — SVD answer extraction |
| `src/hwcc/bench/runner.py` | Add svd_lookup + hybrid code paths |
| `src/hwcc/cli.py` | Add `--svd-path` option |
| `tests/test_bench_svd_lookup.py` | **NEW** — Unit tests |
| `tests/test_bench_runner.py` | Integration tests for new conditions |

### Dependencies

- `cmsis-svd` library (already a dependency for `hwcc bench generate`)
- Existing `SearchEngine` for hybrid's RAG fallback (already wired)

---

## Technical Design

### Architecture

```
┌─────────────────────────────────────────────────────┐
│ run_benchmark() loop                                │
│                                                     │
│  for each question:                                 │
│    ├─ condition == "svd_lookup"                      │
│    │   └─ svd_answer = lookup_svd_answer(q, device) │
│    │   └─ BenchResponse(extracted=svd_answer, ...)   │
│    │                                                │
│    ├─ condition == "hybrid"                          │
│    │   └─ route = _route_question(q)                │
│    │   └─ if route == "svd_lookup":                 │
│    │   │     svd_answer = lookup_svd_answer(...)    │
│    │   └─ elif route == "hwcc_rag":                 │
│    │   │     effective = _build_rag_condition(...)   │
│    │   │     _ask_question(q, effective, provider)  │
│    │   └─ else: (hwcc_full fallback)                │
│    │         _ask_question(q, full_cond, provider)  │
│    │                                                │
│    └─ else (all other conditions)                   │
│        └─ _ask_question(q, condition, provider)     │
└─────────────────────────────────────────────────────┘
```

### `svd_lookup.py` — Direct SVD Answer Extraction

```python
@dataclass(frozen=True)
class SvdLookupResult:
    answer: str          # extracted answer string (e.g. "0x40013000")
    answerable: bool     # True if question category is SVD-answerable
    peripheral: str      # peripheral name matched (empty if not found)
    latency_ms: float    # parse + lookup time

def lookup_svd_answer(
    question: BenchQuestion,
    device: SVDDevice,
) -> SvdLookupResult:
    """Look up the answer to a bench question directly from SVD data."""
```

#### Input Fields from BenchQuestion

The `BenchQuestion` dataclass already has the structured metadata fields needed for SVD lookup — no text parsing required:

| Field | Type | Example | Used by |
|-------|------|---------|---------|
| `question.category` | `str` | `"base_address"` | Category routing |
| `question.peripheral` | `str` | `"SPI1"` | Peripheral lookup |
| `question.register` | `str` | `"CR1"` | Register lookup (empty for base_address) |
| `question.field_name` | `str` | `"BR"` | Field lookup (empty for register-level) |

#### Peripheral/Register/Field Name Matching Algorithm

SVD peripheral names may differ from question metadata (e.g., SVD has `"SPI1_I2S1ext"`, question has `"SPI1"`). The matching algorithm handles all 3 hierarchy levels:

```python
def _find_peripheral(device: SVDDevice, name: str) -> SVDPeripheral | None:
    """Find peripheral by case-insensitive exact match, then prefix match."""
    name_upper = name.upper()
    # 1. Exact match (case-insensitive)
    for p in device.peripherals:
        if p.name.upper() == name_upper:
            return p
    # 2. Prefix match: question "SPI1" matches SVD "SPI1_I2S1ext"
    for p in device.peripherals:
        if p.name.upper().startswith(name_upper):
            return p
    return None  # → answerable=False

def _find_register(peripheral: SVDPeripheral, name: str) -> SVDRegister | None:
    """Find register by case-insensitive exact match."""
    name_upper = name.upper()
    for r in peripheral.registers:
        if r.name.upper() == name_upper:
            return r
    return None  # → answerable=False

def _find_field(register: SVDRegister, name: str) -> SVDField | None:
    """Find field by case-insensitive exact match."""
    name_upper = name.upper()
    for f in register.fields:
        if f.name.upper() == name_upper:
            return f
    return None  # → answerable=False
```

**Key design:** Only peripheral uses prefix matching (SVD often has suffixed names). Register and field names use exact match only — they are precise identifiers that should match 1:1 since questions are generated from the same SVD source.

#### Category Handlers

The function handles 5 categories:

| Category | Lookup method |
|----------|--------------|
| `base_address` | `_find_peripheral(device, q.peripheral).base_address` → `f"0x{addr:08X}"` |
| `register_offset` | `_find_register(periph, q.register).address_offset` → `f"0x{offset:04X}"` |
| `reset_value` | `_find_register(periph, q.register).reset_value` → `f"0x{val:08X}"` |
| `access_type` | `_find_register(periph, q.register).access` → access code mapping |
| `bit_field` | `_find_field(reg, q.field_name)` → `[msb:lsb]` or `[bit]` from `bit_offset + bit_width` |

For any other category (datasheet-only questions like `clock_config`, `electrical_specs`, `memory_specs`, etc.), returns `answerable=False`. If any lookup in the hierarchy fails (`_find_peripheral`, `_find_register`, or `_find_field` returns `None`), also returns `answerable=False`.

#### BenchResponse Construction for SVD Lookup (LLM-free path)

When `svd_lookup` answers a question, the runner builds a `BenchResponse` without LLM interaction:

```python
# For answerable questions:
BenchResponse(
    question_id=question.id,
    raw_response=result.answer,       # the SVD answer IS the raw response
    extracted_answer=result.answer,    # same — no extraction needed
    correct=(score == 1.0),
    score=score,                       # from score_answer(result.answer, ...)
    latency_ms=result.latency_ms,
    partial_score=partial,             # from score_answer_partial(result.answer, ...)
    confidence=1.0,                    # SVD lookup is deterministic
)
# tokens_used = 0 (no LLM call)

# For unanswerable questions:
BenchResponse(
    question_id=question.id,
    raw_response="[SVD_UNANSWERABLE]",
    extracted_answer="",
    correct=False,
    score=0.0,
    latency_ms=result.latency_ms,
    partial_score=0.0,
    confidence=None,                   # no answer attempted
)
# tokens_used = 0
```

### `_route_question()` — Hybrid Router

```python
_SVD_CATEGORIES = {"base_address", "register_offset", "bit_field", "reset_value", "access_type"}

def _route_question(question: BenchQuestion) -> str:
    """Route a question to the best condition name."""
    if question.category in _SVD_CATEGORIES:
        return "svd_lookup"
    # Datasheet questions with specific peripheral → RAG can find it
    if question.peripheral:
        return "hwcc_rag"
    # Cross-peripheral or general → full context
    return "hwcc_full"
```

For the benchmark, routing by `question.category` is deterministic and fair. The blog's regex-based routing is for production use where categories aren't known in advance.

### Design Decisions

1. **SVD lookup in runner, not as a Provider**
   - *Rationale:* `BaseBenchProvider.query(system_prompt, user_prompt)` assumes LLM interaction. SVD lookup doesn't use prompts — it needs `BenchQuestion` metadata (peripheral, register, field_name, category). Forcing it into a Provider would require an awkward adapter.
   - *Alternative:* `SvdLookupProvider` that parses the question text with regex. Rejected because fragile and unnecessary — we have structured metadata.

2. **Parse SVD once, reuse per question**
   - The runner parses the SVD file once when `svd_lookup` or `hybrid` is in the conditions list. The parsed `SVDDevice` is passed to `lookup_svd_answer()` per question.
   - *Rationale:* SVD parsing takes ~100ms. Parsing per question would waste time.

3. **Hybrid uses category field, not regex**
   - *Rationale:* For benchmark evaluation, the category is ground truth. Using regex on question text would introduce routing errors that contaminate the benchmark results.
   - *Future:* A production router would use regex + optional LLM classification.

4. **Hybrid requires at least one LLM sub-condition**
   - Hybrid dispatches SVD questions to svd_lookup, but needs an LLM condition for non-SVD questions.
   - **Fallback chain** (evaluated in order, first available wins):
     1. `_route_question()` returns `"hwcc_rag"` AND `search_engine` is not None → build RAG condition via `_build_rag_condition_from_engine()`
     2. `_route_question()` returns `"hwcc_rag"` but `search_engine` is None → fall through to step 3
     3. `_route_question()` returns `"hwcc_full"` OR fell through from step 2 → use `hwcc_full` condition from the conditions list
     4. If `hwcc_full` not in conditions list → use `hwcc_hot` condition
     5. If `hwcc_hot` not in conditions list → use `no_context` condition (always available)
   - The runner resolves the LLM fallback condition **once** at hybrid setup time (before the question loop) by scanning the conditions list in priority order: `hwcc_full` > `hwcc_hot` > `no_context`. This `_llm_fallback` condition is used whenever RAG is unavailable or question routes to full context.
   - If no SVD device is available (no `svd_path`), hybrid skips with a warning — same pattern as `hwcc_rag` without SearchEngine.

---

## Implementation Plan

### Phase 1: SVD Lookup Module

- [ ] **`src/hwcc/bench/svd_lookup.py`** — Create module
  - `SvdLookupResult` frozen dataclass
  - `parse_svd_device(svd_path: Path) -> SVDDevice` — cached SVD parser
  - `lookup_svd_answer(question: BenchQuestion, device: SVDDevice) -> SvdLookupResult`
  - Handle all 5 SVD categories
  - Return `answerable=False` for unknown categories
- [ ] **`tests/test_bench_svd_lookup.py`** — Unit tests
  - Test each of the 5 categories against mock SVD data
  - Test non-SVD category returns unanswerable
  - Test peripheral/register not found returns unanswerable
  - Test answer format matches expected scoring format

### Phase 2: Runner Integration

- [ ] **`src/hwcc/bench/runner.py`** — Add svd_lookup code path
  - Add `svd_path: Path | None = None` param to `run_benchmark()`
  - Parse SVD once at start if svd_lookup or hybrid in conditions
  - In question loop: if `svd_lookup`, call `lookup_svd_answer()` and build `BenchResponse` directly (skip `_ask_question()`)
  - Score the SVD answer through existing `score_answer()` pipeline
  - Track latency from `SvdLookupResult.latency_ms`
  - `total_tokens = 0` for svd_lookup (no LLM)
- [ ] **`tests/test_bench_runner.py`** — Integration tests
  - `TestRunBenchmarkSvdLookup` class
  - Test svd_lookup condition produces responses without calling provider
  - Test svd_lookup skipped when no svd_path provided

### Phase 3: Hybrid Router

- [ ] **`src/hwcc/bench/runner.py`** — Add hybrid routing
  - `_route_question()` function
  - In question loop: if `hybrid`, route each question to svd_lookup / hwcc_rag / hwcc_full
  - Hybrid needs: SVDDevice (for svd_lookup), SearchEngine (for rag), a full-context BenchCondition (for fallback)
  - Build `_HybridContext` helper to hold these dependencies
- [ ] **`tests/test_bench_runner.py`** — Hybrid tests
  - `TestRunBenchmarkHybrid` class
  - Test SVD-category questions routed to svd_lookup (no LLM call)
  - Test datasheet-category questions routed to RAG or full context
  - Test hybrid with only SVD (no search engine) falls back to available LLM condition

### Phase 4: CLI Wiring

- [ ] **`src/hwcc/cli.py`** — Add options
  - `--svd-path` option on `bench_run` (auto-detect from dataset's `source_svd` field if empty)
  - Add `svd_lookup` and `hybrid` to available conditions list
  - Pass `svd_path` to `run_benchmark()`
- [ ] Auto-detect SVD path from `dataset.source_svd` field when available

### Phase 5: Verification

- [ ] All existing tests pass (1302+)
- [ ] `ruff check` clean
- [ ] `mypy` clean
- [ ] Manual test with real SVD file in `~/hwcc-demo`

---

## Testing Strategy

### Unit Tests (`test_bench_svd_lookup.py`)

```
test_lookup_base_address_returns_hex
test_lookup_register_offset_returns_hex
test_lookup_reset_value_returns_hex
test_lookup_access_type_returns_code
test_lookup_bit_field_single_bit
test_lookup_bit_field_multi_bit
test_lookup_unknown_category_unanswerable
test_lookup_missing_peripheral_unanswerable
test_lookup_missing_register_unanswerable
test_parse_svd_device_caches (optional)
```

### Integration Tests (in `test_bench_runner.py`)

```
test_svd_lookup_condition_produces_responses
test_svd_lookup_skipped_without_svd_path
test_svd_lookup_does_not_call_provider
test_hybrid_routes_svd_to_lookup
test_hybrid_routes_datasheet_to_rag
test_hybrid_fallback_without_search_engine
test_hybrid_skipped_without_svd_path
```

### Manual Testing

1. `hwcc bench run ~/hwcc-demo/.rag/bench.json --conditions svd_lookup --svd-path ~/hwcc-demo/.rag/docs/STM32F407.svd`
   - Expect 100% on SVD questions, 0% on datasheet questions
2. `hwcc bench run ~/hwcc-demo/.rag/bench_datasheet.json --conditions svd_lookup`
   - Expect 0% (all datasheet questions are unanswerable by SVD)
3. `hwcc bench run ~/hwcc-demo/.rag/bench.json --conditions hybrid --provider claude_code`
   - Expect SVD questions answered instantly, datasheet questions via LLM

---

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| SVD peripheral naming mismatch (question says "SPI1", SVD says "SPI1_I2S1ext") | SVD lookup fails to find peripheral | Case-insensitive prefix matching, same as `_select_peripherals()` |
| `cmsis-svd` import fails at runtime | svd_lookup condition errors | Guard with try/except, skip condition with warning (same pattern as dataset generation) |
| Hybrid routing too simplistic for mixed datasets | Wrong mode chosen | Category-based routing is deterministic for benchmark; note in report |
| SVD file path doesn't exist | Runtime error | Validate at CLI level, skip condition with warning |

---

## NON-GOALS

- **No LLM-based routing** — Hybrid uses category metadata, not Claude Haiku classification
- **No cost tracking** — Blog compares $/query but that's a reporting feature, not a condition
- **No production router** — This is bench-only; a real query router is a separate feature
- **No multi-hop RAG** — Blog mentions as unsolved; out of scope
- **No changes to scoring engine** — SVD lookup answers go through existing `score_answer()`
- **No changes to report format** — Both new conditions appear naturally in existing report tables

---

## Estimated Effort

- **Complexity:** Medium
- **Files Changed:** ~5 files (1 new module, 1 new test file, 3 modified)
- **Lines of Code:** ~250 new, ~80 modified

---

## Plan Validation (3-Agent Consensus)

**Method:** 2/3 consensus with reasoning verification
**Date:** 2026-03-14
**Overall:** NEEDS_REVISION (revised from MAJOR_REVISION after addressing critical critiques)
**Consensus Critiques:** 4 of 9 raw findings across 3 validators
**Noise Filtered:** 5 single-validator findings removed
**Validator Assessments (informational):** 3× NEEDS_REVISION

### Consensus Critiques

#### [3/3] Peripheral name matching algorithm underspecified
**Category:** Completeness | **Severity:** critical → addressed | **Section:** Technical Design
**Validators:** Validator 1, 2, 3

**Reasoning:**
1. OBSERVE: Plan said "case-insensitive prefix matching" in Risks table but gave no algorithm
2. INFER: Without exact matching rules for all 3 hierarchy levels (peripheral, register, field), implementation is ambiguous
3. CONCLUDE: Could lead to wrong matches or missed matches

**Resolution:** Added full `_find_peripheral()`, `_find_register()`, `_find_field()` algorithm specification with exact match first, prefix match only for peripherals.

---

#### [2/3] BenchQuestion structured fields not documented
**Category:** Completeness | **Severity:** critical → addressed | **Section:** Technical Design
**Validators:** Validator 1, 3

**Reasoning:**
1. OBSERVE: Plan references `question.peripheral`, `question.register`, `question.field_name` but never shows these fields exist
2. INFER: Reader cannot verify the SVD lookup approach is feasible without knowing BenchQuestion's schema
3. CONCLUDE: Plan documentation gap (code already has these fields)

**Resolution:** Added "Input Fields from BenchQuestion" table showing all 4 fields used by SVD lookup with types and examples.

---

#### [3/3] Hybrid fallback condition selection undefined
**Category:** Feasibility | **Severity:** warning | **Section:** Technical Design §4
**Validators:** Validator 1, 2, 3

**Reasoning:**
1. OBSERVE: Plan says "falls back to whatever LLM condition is available" without defining resolution order
2. INFER: Ambiguous fallback could cause different behavior depending on conditions list order
3. CONCLUDE: Need explicit priority chain

**Resolution:** Added to Review Checklist. Defined explicit fallback chain: hwcc_full > hwcc_hot > no_context, resolved once at hybrid setup time.

---

#### [3/3] BenchResponse schema for svd_lookup not defined
**Category:** Completeness | **Severity:** warning | **Section:** Technical Design
**Validators:** Validator 1, 2, 3

**Reasoning:**
1. OBSERVE: Architecture diagram shows `BenchResponse(extracted=svd_answer, ...)` with ellipsis
2. INFER: Undefined fields (raw_response, confidence, tokens) could cause scoring or reporting errors
3. CONCLUDE: Need explicit field specification for both answerable and unanswerable paths

**Resolution:** Added to Review Checklist. Added full BenchResponse construction examples for both answerable and unanswerable paths.

---

### Verified Clean Categories
- **Security:** Confirmed by 3/3 validators — no external input, no injection risk
- **Performance:** Confirmed by 3/3 validators — SVD parsed once, sub-ms per lookup
- **Backward Compatibility:** Confirmed by 3/3 validators — all new params optional

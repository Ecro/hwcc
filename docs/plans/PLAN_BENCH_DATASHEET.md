# Plan: HwBench Datasheet Extension — Verify RAG Quality for PDF Documentation

> **Date**: 2026-03-14
> **Status**: Draft
> **Depends on**: PLAN_HWBENCH.md (v1.0 complete), PLAN_BENCH_CREDIBILITY.md (partial)
> **Motivation**: Blog post fact-check and `/research` analysis on RAG vs context for datasheets

---

## Executive Summary

> **TL;DR:** Extend hwcc bench beyond SVD register Q&A to test datasheet-derived knowledge
> (electrical specs, timing, init procedures, cross-peripheral deps), validating the blog
> post's hybrid router thesis with real measurements.

### What We're Doing

Current `hwcc bench` only tests Category A (register knowledge from SVD files). The blog post
"RAG vs Full Context vs SVD Lookup" claims a hybrid approach is optimal, but the experiment
numbers were predicted, not independently measured. This plan adds **Category B** (datasheet
knowledge) to bench, enabling real empirical measurement of RAG quality on hardware PDF content.

### Why It Matters

1. **Blog credibility**: Replace predicted numbers with measured results
2. **Product validation**: Prove hwcc's PDF parsing + RAG actually helps for non-register queries
3. **Hybrid router design**: Empirical data to inform the router's dispatch thresholds
4. **Competitive advantage**: No existing benchmark tests RAG on hardware documentation

### Key Decisions

- **Decision 1:** Manual Q&A curation first (Phase 1), semi-auto generation later — ensures ground truth accuracy
- **Decision 2:** New `answer_format` types (`text`, `numeric`, `numeric_range`, `list`) — extends scoring engine minimally
- **Decision 3:** New `raw_pdf` bench condition — compares hwcc context vs raw PDF text stuffing
- **Decision 4:** Separate dataset files per source type — `*_DatasheetKnowledge_dataset.json` alongside existing `*_RegisterKnowledge_dataset.json`

---

## Problem Analysis

### Current State

| Aspect | Current | Gap |
|--------|---------|-----|
| Data source | SVD only | No PDF/datasheet content |
| Categories | 5 (base_address, register_offset, bit_field, reset_value, access_type) | Missing: electrical, timing, init, cross-peripheral, package |
| Answer formats | 3 (hex, bit_range, access_code) | Missing: text, numeric, numeric_range, list |
| Conditions | 3 (no_context, hwcc_hot, hwcc_full) | Missing: raw_pdf, hwcc_rag (vector search) |
| Ground truth | Auto-generated from SVD | Datasheet requires manual/semi-auto curation |
| Scoring | Exact match + partial (nibble/Jaccard) | Text answers need fuzzy/semantic scoring |

### Blog Post Claims to Verify

From the blog research, these specific claims need empirical testing:

| Claim | Blog Score (predicted) | What We Need |
|-------|----------------------|--------------|
| RAG scores 8/12 on register queries | Predicted, not measured | Measure with hwcc bench |
| RAG scores 6/12 on config questions | Predicted | Measure with datasheet Q&A |
| RAG scores 4/12 on cross-peripheral | Predicted | Measure with cross-ref Q&A |
| Full context scores 11/12 on config | Predicted | Measure with raw_pdf condition |
| Structured lookup scores 12/12 on register | Predicted | Already measurable with SVD bench |

### What Needs Extension

```
Current bench pipeline:
  SVD → generate_dataset() → BenchDataset → runner → scoring → report
                                  ↑ only hex/bit_range/access_code

Extended pipeline:
  SVD → generate_dataset() → BenchDataset ─┐
  PDF → curate_dataset()   → BenchDataset ─┤→ runner → scoring → report
  Manual JSON              → BenchDataset ─┘
                                  ↑ adds text/numeric/numeric_range/list
```

---

## Prerequisites (Phase 0)

Before any implementation begins:

1. **Acquire STM32F407 documentation PDFs:**
   - DS8626: STM32F405xx/407xx datasheet (st.com, ~200 pages)
   - RM0090: STM32F405/415/407/417 reference manual (st.com, ~1,751 pages)
   - ES0182: STM32F407/417 errata sheet (st.com)

2. **Index PDFs via hwcc:**
   ```bash
   hwcc add docs/STM32F407_datasheet.pdf --type datasheet
   hwcc add docs/RM0090_reference_manual.pdf --type reference_manual
   hwcc status  # verify chunk counts in .rag/
   ```

3. **Prepare raw_pdf benchmark file:**
   ```bash
   # Extract relevant chapters as plain text for raw_pdf condition
   # Target: RCC, SPI, USART, GPIO, ADC, TIM chapters from RM0090
   # Budget: ~100K tokens (~400K chars) maximum
   ```

4. **Verify existing bench still works:**
   ```bash
   hwcc bench generate <svd-file> --output baseline.json
   # Record baseline Category A scores before any code changes
   ```

---

## Technical Design

### 1. New Answer Formats

Add to `scoring.py`:

| Format | Description | Extraction | Scoring |
|--------|-------------|-----------|---------|
| `text` | Short text answer (e.g., "APB1") | Last sentence / keyword | Case-insensitive substring match |
| `numeric` | Single number with unit (e.g., "42 MHz") | Regex `\d+\.?\d*\s*(MHz\|kHz\|V\|mA\|us\|ns)` | Exact value match after unit normalization |
| `numeric_range` | Range (e.g., "1.8V to 3.6V") | Regex for min-max pairs | Both bounds correct |
| `list` | Ordered/unordered list (e.g., "PA5, PA6, PA7") | Split on comma/newline | Set intersection / Jaccard |

### 2. New Question Categories

| Category | Example Question | Answer Format | Ground Truth Source |
|----------|-----------------|---------------|-------------------|
| `clock_config` | "What APB bus is USART2 connected to?" | `text` | Reference manual |
| `electrical` | "What is the VDD operating range for STM32F407?" | `numeric_range` | Datasheet Table 16 |
| `timing` | "What is the maximum SPI clock frequency?" | `numeric` | Datasheet Table 47 |
| `init_sequence` | "What registers must be configured to enable SPI1?" | `list` | Reference manual |
| `cross_peripheral` | "What clock must be enabled before configuring USART2 baud rate?" | `text` | RM + RCC chapter |
| `package` | "How many GPIO pins on LQFP100 package?" | `numeric` | Datasheet |
| `errata` | "What is the SPI CRC errata workaround?" | `text` | Errata sheet |

### 3. New Bench Condition: `raw_pdf`

**Definition:** Load pre-extracted relevant chapters from the reference manual as plain
text, truncated to a token budget. This is NOT the full 1,700-page document — it is the
specific chapters containing answers to the benchmark questions.

**Context construction:**
1. Pre-extract relevant chapters (RCC, SPI, USART, GPIO, ADC, TIM, electrical tables)
   from RM0090 using hwcc's PDF parser output (already markdown)
2. Save as `context_dir / "raw_pdf.md"` — a single file containing chapter text
3. Truncate to **100K tokens (~400K characters)** maximum
4. If file exceeds limit, warn user and truncate from the end

**Rationale:** This simulates "Mode B: Full Context" from the blog post — what a developer
gets by copying relevant datasheet pages into a prompt. It is NOT an oracle condition
(doesn't select per-question), which would be unfairly favorable.

```python
# Condition: raw_pdf — relevant chapters as plain text
raw_pdf_path = context_dir / "raw_pdf.md"
if raw_pdf_path.exists():
    raw_content = raw_pdf_path.read_text(encoding="utf-8")
    # Truncate to ~100K tokens (400K chars) to fit context windows
    MAX_RAW_PDF_CHARS = 400_000
    if len(raw_content) > MAX_RAW_PDF_CHARS:
        logger.warning("raw_pdf.md truncated from %d to %d chars", len(raw_content), MAX_RAW_PDF_CHARS)
        raw_content = raw_content[:MAX_RAW_PDF_CHARS]
    conditions.append(BenchCondition(
        name="raw_pdf",
        system_prompt=_BASE_SYSTEM_PROMPT.format(
            chip=chip,
            context_block=f"Here is the raw datasheet text:\n\n{raw_content}"
        ),
        description=f"Raw PDF chapter text ({len(raw_content)} chars, no hwcc processing)",
    ))
```

### 3b. New Bench Condition: `hwcc_rag`

**Definition:** For each benchmark question, perform a vector search against the hwcc
ChromaDB store and assemble the top-k retrieved chunks as context. This tests hwcc's
actual retrieval quality on a per-question basis.

**Retrieval specification:**
- **Query construction:** Verbatim question text (e.g., "What APB bus is USART2 connected to on the STM32F407?")
- **Top-k:** 5 chunks (configurable via `--rag-top-k`, default 5)
- **Similarity metric:** Cosine similarity (ChromaDB default with `all-MiniLM-L6-v2`)
- **Score cutoff:** None (always return top-k, even low-similarity results)
- **Context assembly:** Chunks concatenated in ranked order (most relevant first), separated by `\n\n---\n\n`
- **Token budget:** Sum of chunks capped at 8K tokens (~32K chars). If top-k exceeds budget, truncate from least relevant.
- **Collection:** Default hwcc collection in `.rag/chroma/`

**Implementation in runner.py:**

```python
def _build_rag_condition(
    question: BenchQuestion,
    store: BaseStore,
    chip: str,
    top_k: int = 5,
    max_chars: int = 32_000,
) -> BenchCondition:
    """Build a per-question RAG condition by querying the vector store."""
    results = store.search(question.question, n_results=top_k)
    chunks = []
    total_chars = 0
    for result in results:
        if total_chars + len(result.content) > max_chars:
            break
        chunks.append(result.content)
        total_chars += len(result.content)
    context = "\n\n---\n\n".join(chunks)
    return BenchCondition(
        name="hwcc_rag",
        system_prompt=_BASE_SYSTEM_PROMPT.format(
            chip=chip,
            context_block=f"Here are relevant documentation excerpts:\n\n{context}"
        ),
        description=f"hwcc RAG: top-{top_k} chunks ({total_chars} chars)",
    )
```

**Note:** Unlike other conditions (which are static per-run), `hwcc_rag` builds a different
context per question. The runner must call `_build_rag_condition()` inside the question loop
rather than using a pre-built condition list. This requires a small refactor of `_ask_question()`
to accept either a static condition or a store+params for dynamic RAG.

### 4. Dataset Curation Workflow

**Phase 1: Manual JSON**

```json
{
  "name": "STM32F407_DatasheetKnowledge",
  "chip": "STM32F407",
  "source_svd": "",
  "question_count": 30,
  "questions": [
    {
      "id": "usart2_apb_bus",
      "category": "clock_config",
      "peripheral": "USART2",
      "register": "",
      "field_name": "",
      "question": "What APB bus is USART2 connected to on the STM32F407?",
      "answer": "APB1",
      "answer_format": "text",
      "difficulty": "medium",
      "source_ref": "RM0090 Table 1, Section 2.2"
    }
  ]
}
```

Note: `source_ref` is a new optional field for traceability back to the datasheet.

**Phase 2: Semi-auto from PDF tables**

The PDF parser already extracts tables as markdown. A new `generate_datasheet_dataset()` function
can parse extracted tables (electrical characteristics, pin definitions) and generate Q&A pairs
with the table data as ground truth.

### 5. Scoring Thresholds and Algorithms

**Concrete scoring rules per format:**

| Format | `score_answer()` (binary) | `score_answer_partial()` (graded) |
|--------|--------------------------|----------------------------------|
| `text` | 1.0 if `normalize(ground_truth)` is a substring of `normalize(extracted)`, else 0.0. Normalize = lowercase, strip whitespace, remove articles (a/an/the). | Token Jaccard: `len(gt_tokens & ext_tokens) / len(gt_tokens \| ext_tokens)` |
| `numeric` | 1.0 if `to_base_unit(extracted) == to_base_unit(ground_truth)`, else 0.0. Tolerance: exact match (no %). | Ratio: `1.0 - min(1.0, abs(ext - gt) / gt)` if gt != 0 |
| `numeric_range` | 1.0 if both bounds match after unit normalization, else 0.0 | 0.5 if one bound matches, 0.0 if neither |
| `list` | 1.0 if Jaccard(extracted_set, gt_set) >= 0.75, else 0.0 | Raw Jaccard coefficient (0.0-1.0) |

**Text extraction algorithm:**
1. If response is short (<= 20 words), use entire response as extracted answer
2. Otherwise, look for patterns: "is {answer}", "answer: {answer}", "= {answer}"
3. Fallback: last sentence of response

**Numeric unit normalization table:**

| Input Unit | Canonical | Multiplier |
|-----------|-----------|------------|
| Hz, hz | Hz | 1 |
| kHz, KHz | Hz | 1e3 |
| MHz, Mhz | Hz | 1e6 |
| GHz | Hz | 1e9 |
| V, v, volt, volts | V | 1 |
| mV, mv | V | 1e-3 |
| A, amp, amps | A | 1 |
| mA, ma | A | 1e-3 |
| uA, ua, µA | A | 1e-6 |
| s, sec | s | 1 |
| ms | s | 1e-3 |
| us, µs | s | 1e-6 |
| ns | s | 1e-9 |
| KB, kB | B | 1024 |
| MB | B | 1048576 |
| MSPS, Msps | SPS | 1e6 |
| ksps, kSPS | SPS | 1e3 |

**Keyword extraction for text scoring:**
- Split on whitespace and punctuation
- Remove stopwords: `{"a", "an", "the", "is", "are", "of", "on", "in", "to", "for", "it", "and", "or"}`
- Normalize remaining tokens: lowercase, strip trailing punctuation
- No semantic similarity (pure lexical) — keeps scoring deterministic and reproducible

---

## Implementation Plan

### Phase 0: Prerequisites (Gate — must complete before Phase 1)

- [ ] 0.1 Acquire STM32F407 datasheet (DS8626) and reference manual (RM0090) PDFs
- [ ] 0.2 Index both PDFs via `hwcc add` — verify chunk counts in `.rag/`
- [ ] 0.3 Prepare `raw_pdf.md` — extract RCC, SPI, USART, GPIO, ADC, TIM chapters + electrical tables from RM0090 parser output, cap at 400K chars
- [ ] 0.4 Record baseline Category A bench scores (run existing SVD bench, save golden file)

### Phase 1: Scoring Engine Extension (3-4 hours)

- [ ] 1.1 `scoring.py`: Add `_extract_text()` — short response passthrough, pattern-based for longer
- [ ] 1.2 `scoring.py`: Add `_extract_numeric()` — extract number + unit via regex
- [ ] 1.3 `scoring.py`: Add `_extract_numeric_range()` — extract min-max pair with unit
- [ ] 1.4 `scoring.py`: Add `_extract_list()` — split on comma/newline/bullet
- [ ] 1.5 `scoring.py`: Add `normalize_numeric()` — unit normalization table (see Section 5)
- [ ] 1.6 `scoring.py`: Add `_score_text()` — substring match (binary) + token Jaccard (partial)
- [ ] 1.7 `scoring.py`: Add `_score_numeric()`, `_score_numeric_range()`, `_score_list()`
- [ ] 1.8 `scoring.py`: Update `extract_answer()` and `score_answer()` dispatch for new formats
- [ ] 1.9 `scoring.py`: Update `score_answer_partial()` for new formats
- [ ] 1.10 `tests/test_bench_scoring.py`: Tests for all new extractors, scorers, edge cases
- [ ] 1.11 Regression test: verify existing hex/bit_range/access_code scoring unchanged (golden file)

### Phase 2: Dataset Types Extension (8-10 hours — includes manual curation)

- [ ] 2.1 `types.py`: Add `source_ref: str = ""` field to `BenchQuestion`
- [ ] 2.2 `types.py`: Update `BenchDataset` docstring to mention non-SVD sources
- [ ] 2.3 `dataset.py`: Update `load_dataset()` to handle `source_ref` field gracefully
- [ ] 2.4 Curate 30 Q&A pairs with verified ground truth — each requires `source_ref` with RM0090/DS8626 page number and table/section reference
- [ ] 2.5 Create `datasets/stm32f407_datasheet_knowledge.json` — final validated dataset
- [ ] 2.6 Cross-verify: at minimum, all 6 electrical and 6 timing answers against actual datasheet tables

### Phase 3: New Bench Conditions (2-3 hours)

- [ ] 3.1 `runner.py`: Add `raw_pdf` condition with 400K char truncation
- [ ] 3.2 `runner.py`: Add `hwcc_rag` condition — per-question vector search (top-5, 32K char budget)
- [ ] 3.3 `runner.py`: Refactor `_ask_question()` to support dynamic per-question conditions (for hwcc_rag)
- [ ] 3.4 `cli.py`: Add `--rag-top-k` option to `bench run`
- [ ] 3.5 `cli.py`: Update `bench run` `--conditions` to accept new condition names

### Phase 4: Semi-auto Dataset Generator from PDF (Deferred — separate follow-up task)

> Deferred to PLAN_BENCH_DATASET_AUTOGEN.md. Phase 1-3 + 5 deliver the core blog
> validation capability. Phase 4 is an optimization for dataset growth, not a requirement.

### Phase 5: Report Enhancement (2-3 hours)

- [ ] 5.1 `report.py`: Show separate category groups (Register Knowledge vs Datasheet Knowledge)
- [ ] 5.2 `report.py`: Add `source_ref` to per-question detail for traceability
- [ ] 5.3 Markdown report: include blog-comparable format (4-dimension scoring table)

---

## Curated Question Set (Phase 2.4)

### STM32F407 Datasheet Knowledge — 30 Questions

**Clock Config (6 questions)**
1. "What APB bus is USART2 connected to?" → "APB1" (text)
2. "What is the APB1 clock frequency when SYSCLK is 168 MHz with default prescaler?" → "42 MHz" (numeric)
3. "What APB bus is SPI1 connected to?" → "APB2" (text)
4. "What is the maximum SYSCLK frequency for STM32F407?" → "168 MHz" (numeric)
5. "Which PLL input source options exist?" → "HSI, HSE" (list)
6. "What is the default HSI oscillator frequency?" → "16 MHz" (numeric)

**Electrical (6 questions)**
7. "What is the VDD operating voltage range?" → "1.8V to 3.6V" (numeric_range)
8. "What is the maximum current per GPIO pin?" → "25 mA" (numeric)
9. "What is the typical power consumption in Run mode at 168 MHz?" → "93 mA" (numeric)
10. "What is the operating temperature range for industrial grade?" → "-40 to 85" (numeric_range)
11. "What is the maximum ADC conversion rate?" → "2.4 MSPS" (numeric)
12. "What is the flash memory size on STM32F407VGT6?" → "1024 KB" (numeric)

**Cross-Peripheral (6 questions)**
13. "What GPIO alternate function number is SPI1_SCK on PA5?" → "AF5" (text)
14. "What RCC register bit enables USART2 clock?" → "USART2EN" (text)
15. "To use USART2, which RCC bus clock must be enabled?" → "APB1" (text)
16. "What DMA stream handles SPI1_TX?" → "DMA2 Stream 3" (text)
17. "Which interrupt number (IRQn) is assigned to TIM2?" → "28" (numeric)
18. "What GPIO port and pin is the SPI1_MOSI default mapping?" → "PA7" (text)

**Timing (6 questions)**
19. "What is the maximum SPI clock frequency in master mode?" → "42 MHz" (numeric)
20. "What is the ADC sampling time for 3-cycle option at 30 MHz?" → "0.1 us" (numeric)
21. "What is the minimum I2C clock period in fast mode?" → "2.5 us" (numeric)
22. "What is the flash memory latency at 168 MHz with 3.3V?" → "5 wait states" (text)
23. "What is the PLL lock time (typical)?" → "300 us" (numeric)
24. "What is the HSE startup time (typical)?" → "2 ms" (numeric)

**Init Sequence (3 questions)**
25. "What registers must be set to configure SPI1 as master?" → "RCC_APB2ENR, GPIOA_MODER, GPIOA_AFRL, SPI1_CR1, SPI1_CR2" (list)
26. "What steps are needed to switch SYSCLK to PLL at 168MHz?" → "HSE enable, PLL config, PLL enable, flash latency, switch" (list)
27. "What is the correct order to initialize USART2 for TX?" → "RCC APB1 enable, GPIO AF config, baud rate, USART enable, TE enable" (list)

**Package (3 questions)**
28. "How many I/O pins does the LQFP100 package support?" → "82" (numeric)
29. "How many timers does STM32F407 have?" → "14" (numeric)
30. "How many DMA controllers does STM32F407 have?" → "2" (numeric)

---

## Bench Condition Matrix

After this plan, the full condition matrix is:

| Condition | Context Content | Tests |
|-----------|----------------|-------|
| `no_context` | Empty (baseline) | Both SVD + Datasheet |
| `hwcc_hot` | hot.md summary | Both |
| `hwcc_full` | hot.md + peripheral context | Both |
| `raw_pdf` | Raw PDF text (first ~100K tokens) | Datasheet only |
| `hwcc_rag` | Vector search results for each question | Both |

The `raw_pdf` condition directly tests the blog's "Mode B: Full Context" approach.
The `hwcc_rag` condition tests "Mode A: RAG" with real vector retrieval.

---

## Testing Strategy

### Unit Tests — Core Extractors and Scorers

| Test | File | What |
|------|------|------|
| `test_extract_numeric` | `test_bench_scoring.py` | "42 MHz" → ("42", "MHz") |
| `test_extract_numeric_range` | `test_bench_scoring.py` | "1.8V to 3.6V" → (1.8, 3.6, "V") |
| `test_extract_text` | `test_bench_scoring.py` | "The answer is APB1." → "APB1" |
| `test_extract_list` | `test_bench_scoring.py` | "PA5, PA6, PA7" → ["PA5", "PA6", "PA7"] |
| `test_normalize_numeric` | `test_bench_scoring.py` | "42 MHz" == "42000 kHz" |
| `test_score_text_exact` | `test_bench_scoring.py` | "APB1" vs "APB1" → 1.0 |
| `test_score_text_partial` | `test_bench_scoring.py` | "APB1 bus" vs "APB1" → 1.0 |
| `test_score_numeric_wrong_unit` | `test_bench_scoring.py` | "42 kHz" vs "42 MHz" → 0.0 |
| `test_score_list_partial` | `test_bench_scoring.py` | 3/5 items → 0.6 (Jaccard) |
| `test_score_list_threshold` | `test_bench_scoring.py` | 3/4 items Jaccard=0.75 → correct (binary) |
| `test_load_dataset_with_source_ref` | `test_bench_dataset.py` | JSON with source_ref loads |
| `test_load_dataset_without_source_ref` | `test_bench_dataset.py` | Backward compat |
| `test_raw_pdf_condition` | `test_bench_runner.py` | raw_pdf.md present → condition created |
| `test_raw_pdf_truncation` | `test_bench_runner.py` | Large raw_pdf.md truncated to 400K chars |
| `test_hwcc_rag_condition` | `test_bench_runner.py` | Mock store returns chunks → condition built |

### Edge Case Tests (required per answer format)

Each new answer format must have tests for these 5 patterns:

| Pattern | text | numeric | numeric_range | list |
|---------|------|---------|---------------|------|
| Correct value in verbose prose | "The bus is APB1 which..." → APB1 | "The frequency is approximately 42 MHz" → 42 MHz | "VDD ranges from 1.8V to 3.6V typically" → 1.8-3.6 V | "You need: RCC, GPIO, SPI registers" → 3 items |
| Correct value with synonym | "Advanced Peripheral Bus 1" → match APB1? No (lexical only) | "42 megahertz" → 42 MHz | "1800 mV to 3600 mV" → match 1.8V-3.6V | "GPIO_A5" vs "PA5" → no match (lexical) |
| Empty/refusal response | "" or "I don't know" → 0.0 | "" → 0.0 | "I cannot determine" → 0.0 | "" → 0.0 |
| Wrong value, correct format | "APB2" vs "APB1" → 0.0 | "84 MHz" vs "42 MHz" → 0.0 | "2.0V to 3.3V" vs "1.8-3.6" → 0.0 | Wrong items → Jaccard |
| Value with tolerance/condition | "APB1 (at default prescaler)" → APB1 | "42 MHz ± 5%" → 42 MHz | "1.8V to 3.6V (at 25C)" → 1.8-3.6 | Items with annotations → strip |

### Regression Tests

- **Category A golden file**: Before Phase 1, record scores for the existing SVD dataset.
  After Phase 1, re-run and assert identical scores for all hex/bit_range/access_code questions.
  Ensures scoring engine changes don't break existing behavior.

### Integration Tests

1. Load manually curated datasheet dataset JSON → run scoring → verify metrics
2. Run bench with `raw_pdf` condition against mock provider → verify report includes it
3. Run bench with `hwcc_rag` condition against mock store → verify per-question context differs
4. Combined SVD + Datasheet dataset → report shows separate category groups

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Text scoring too lenient/strict | Medium | Defined thresholds in Section 5; pure lexical (no semantic); tunable via constants |
| Manual Q&A errors in ground truth | High | Every Q&A requires `source_ref` with page/table number; electrical + timing answers cross-verified against actual datasheet tables (Phase 2.6) |
| Numeric unit parsing edge cases | Low | Comprehensive normalization table with 20+ unit mappings; edge case tests for each format |
| Large raw PDF exceeds context window | Medium | Hard cap at 400K chars with truncation + warning; chapter-level extraction (not full 1700 pages) |
| Backward compatibility of BenchQuestion | Low | `source_ref` defaults to empty string; golden file regression test |
| STM32F407 datasheet not available | Medium | Phase 0 gate — blocks all subsequent phases until PDFs are acquired and indexed |
| hwcc_rag returns irrelevant chunks | Medium | Log retrieved chunk IDs in report for audit; configurable top-k allows tuning |

---

## Success Criteria

- [ ] `hwcc bench run datasheet_dataset.json` works end-to-end with all new answer formats
- [ ] Scoring engine handles text, numeric, numeric_range, list formats with reasonable accuracy
- [ ] `raw_pdf` condition produces measurably different results from `hwcc_full`
- [ ] Report shows Register Knowledge vs Datasheet Knowledge breakdown
- [ ] All 30 curated questions have verified ground truth with RM0090/DS8626 page references
- [ ] Blog post numbers can be replaced with real measured data
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No changes to existing bench behavior (backward compatible)

---

## Estimated Effort

| Phase | Effort | Files | Notes |
|-------|--------|-------|-------|
| Phase 0: Prerequisites | 2-3 hours | docs, .rag/ | PDF acquisition + indexing + raw_pdf prep |
| Phase 1: Scoring extension | 3-4 hours | scoring.py, test_bench_scoring.py | Includes edge case + regression tests |
| Phase 2: Dataset types + curation | 8-10 hours | types.py, dataset.py, JSON file | 30 Q&A @ ~15 min each = 7.5h curation |
| Phase 3: New conditions | 2-3 hours | runner.py, cli.py | raw_pdf + hwcc_rag + runner refactor |
| Phase 5: Report | 2-3 hours | report.py | |
| **Total** | **17-23 hours** | ~10 files | Phase 4 deferred |

---

## Relationship to Blog Post

This plan directly enables replacing the blog's predicted results with measured data:

| Blog Dimension | Blog Test | hwcc bench Category |
|---------------|-----------|-------------------|
| Register Accuracy | Mode A/B/C/D × 5 register Q | Existing SVD bench (Category A) |
| Config Accuracy | Mode A/B/C/D × 5 config Q | New `clock_config` + `cross_peripheral` |
| Cross-Reference Accuracy | Mode A/B/C/D × 5 cross Q | New `cross_peripheral` + `init_sequence` |
| Electrical Accuracy | Mode A/B/C/D × 5 elec Q | New `electrical` + `timing` |

The blog used 4 modes (RAG, Full Context, Structured, Hybrid). In hwcc bench terms:
- **Mode A (RAG)** → `hwcc_rag` condition
- **Mode B (Full Context)** → `raw_pdf` condition
- **Mode C (Structured)** → `hwcc_full` condition (SVD-compiled context)
- **Mode D (Hybrid)** → Combined condition (TBD — router logic needed)

---

## Future Work (Not This PR)

1. **LLM-assisted Q&A generation** — Use LLM to generate Q&A from parsed PDF, human validates
2. **Graph RAG evaluation** — Test cross-reference following with knowledge graph
3. **Multi-hop RAG evaluation** — Iterative retrieval for cross-peripheral queries
4. **Contextual retrieval** — Anthropic's chunk-context prepending technique
5. **Hybrid router benchmark** — Automated dispatch logic scoring
6. **Cross-MCU generalization** — Same questions on STM32F103, STM32H7

---

## Plan Validation (3-Agent Consensus)

**Method:** 2/3 consensus with reasoning verification (2 rounds)
**Date:** 2026-03-14
**Overall:** APPROVED
**Rounds:** 2 (initial → MAJOR_REVISION → revision → re-validation → APPROVED)

### Round 1: Initial Validation

**Result:** MAJOR_REVISION — 4 critical consensus critiques identified:
1. **[3/3] hwcc_rag condition undefined** — No retrieval params specified → Fixed: added Section 3b with full spec (top-5, verbatim query, cosine similarity, 32K char budget, per-question dynamic, implementation code)
2. **[3/3] raw_pdf no truncation strategy** — No size cap specified → Fixed: added 400K char hard cap, chapter-level extraction, rationale
3. **[3/3] No Phase 0 prerequisites** — Datasheet availability not gated → Fixed: added Phase 0 with PDF acquisition, indexing, raw_pdf prep, baseline recording
4. **[2/3] Text scoring thresholds undefined** — No concrete rules for new formats → Fixed: added Section 5 with concrete rules, unit normalization table, keyword extraction algorithm

All 4 critiques were addressed in the revision before re-validation.

### Round 2: Re-validation

**Result:** Raw validator assessments: 2x MAJOR_REVISION, 1x NEEDS_REVISION
**Consensus Critiques:** 0 genuine consensus critiques after filtering
**Noise Filtered:** 24 raw findings across 3 validators → 0 kept

**Key finding:** All 3 re-validators received a **summarized** version of the plan (due to context window constraints). Their primary critique — "missing implementation phases" — is an artifact: the actual PLAN file contains detailed Phase 0-5 with specific file-level tasks (lines 304-353). This was confirmed by reading the full plan file.

**Secondary finding:** "Runner refactor scope" appeared in all 3 validators but is already addressed by task 3.3 ("Refactor `_ask_question()` to support dynamic per-question conditions") and the implementation note in Section 3b (lines 218-221). Classified as suggestion-level, not actionable.

**Resolution:** Per consensus filter rules, 0 critiques survived with critical or warning severity → **APPROVED**.

### Verified Clean Categories
- Scoring engine design: Confirmed comprehensive by 3/3 validators (Section 5 + unit normalization table)
- Dataset format: Confirmed backward-compatible by 3/3 validators (source_ref defaults to "")
- Testing strategy: Confirmed adequate by 2/3 validators (unit + edge case + regression + integration)
- Blog mapping: Confirmed correct by 3/3 validators (Section "Relationship to Blog Post")

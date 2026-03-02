# Plan: HwBench Credibility — Make Benchmark Results Trustworthy

> **Date**: 2026-03-02
> **Status**: Draft — pending review
> **Depends on**: PLAN_HWBENCH.md (v1.0 complete), PLAN_BENCH_TEST_HARDENING.md (complete)

---

## Scope Declaration

- **Type:** feature
- **Single Concern:** Improve HwBench so its published results are statistically rigorous, cover wide question scope, and are credible to external audiences (blog readers, conference attendees, potential users)
- **Phase:** New — benchmark credibility enhancement (not in existing PLAN.md milestones)
- **Complexity:** High (statistical framework, dataset expansion, new output formats, new data types)
- **Risk:** Medium (additive changes to bench module, no core pipeline impact)

### Concern Separation Rule

This change is ONLY about: making HwBench results trustworthy and publishable
This change is NOT about:
- Core pipeline improvements (ingest/chunk/embed/store/compile)
- New parsers or embedding providers
- MCP server or v0.3 features
- Multi-turn agentic evaluation (Category B/C tasks)
- Web leaderboard or CI automation (future work)

---

## Problem Statement

**What:** HwBench currently runs single-pass benchmarks with modest question counts (~57 per chip), no confidence intervals, no difficulty stratification, and no publication-ready output. A reader seeing "95% accuracy" has no reason to trust it — there's no sample size context, no statistical intervals, no error bars, and no per-question audit trail.

**Why:** For hwcc to use HwBench results in README, blog posts, and conference talks, the numbers need to be **defensible**. Credible benchmarks require:
1. Statistical rigor (confidence intervals, significance tests)
2. Sufficient sample size (200+ questions recommended)
3. Difficulty stratification (easy/medium/hard — not all lookup)
4. Per-question detail for auditability
5. Publication-ready output (markdown tables, not just Rich terminal)

**Success:** Running `hwcc bench run --runs 3 dataset.json` produces a report where:
- Every accuracy number has a 95% CI (e.g., "93.2% ± 3.1%")
- Questions are tagged easy/medium/hard with per-difficulty breakdowns
- Markdown output is copy-pasteable into a blog post or README
- Per-question detail table shows every Q&A for audit
- Condition comparison includes McNemar's significance test (p-value)

---

## Impact Analysis

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/bench/types.py` | modify | Add `difficulty` field to `BenchQuestion`, add `StatisticalSummary` dataclass, add `cost_usd` to `BenchRun` |
| `src/hwcc/bench/dataset.py` | modify | Expand question generation (raise caps, add difficulty tagging, add inter-register/cross-peripheral questions) |
| `src/hwcc/bench/runner.py` | modify | Add `--runs N` support (multiple iterations), aggregate across runs |
| `src/hwcc/bench/scoring.py` | modify | Add Wilson CI computation, McNemar's test, per-difficulty metrics |
| `src/hwcc/bench/report.py` | modify | Add markdown output, per-question detail table, CI display, significance |
| `src/hwcc/bench/types.py` | modify | Expand `BenchMetrics` with CI fields, `BenchReport` with statistical comparison |
| `src/hwcc/cli.py` | modify | Add `--runs`, `--output-format markdown` to bench commands |
| `tests/test_bench_dataset.py` | modify | Tests for expanded dataset, difficulty tagging |
| `tests/test_bench_scoring.py` | modify | Tests for Wilson CI, McNemar's, statistical functions |
| `tests/test_bench_runner.py` | modify | Tests for multi-run aggregation |
| `tests/test_bench_report.py` | modify | Tests for markdown output, per-question detail |

### Dependency Chain

| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `types.py` (new fields) | All bench modules, all bench tests | None |
| `dataset.py` (expanded) | CLI `bench generate`, tests | cmsis_svd |
| `runner.py` (multi-run) | CLI `bench run`, tests | providers, scoring |
| `scoring.py` (statistics) | runner, report, tests | Pure math (stdlib) |
| `report.py` (markdown) | CLI `bench run/report`, tests | types, scoring |

### NON-GOALS (Explicitly Out of Scope)

- [ ] Core pipeline (ingest/chunk/embed/store/compile) — not touched
- [ ] Web leaderboard / static site — separate future project
- [ ] CI/CD automation — separate concern
- [ ] Multi-turn agentic evaluation (Category B tasks) — very high effort, deferred
- [ ] Matplotlib/plotly charts — markdown tables are sufficient for now
- [ ] Anti-memorization / data contamination tests — low ROI for v1 credibility
- [ ] Temperature variation experiments — keep T=0 for reproducibility
- [ ] Raw PDF baseline condition — requires manual PDF prep, deferred

---

## Technical Approach

### Overview

Seven focused improvements, each independently valuable:

```
Step 1: Expand dataset (57 → 200+ questions)
Step 2: Add difficulty tiers (easy/medium/hard)
Step 3: Multi-run support (--runs N, aggregate)
Step 4: Statistical framework (Wilson CI, McNemar's)
Step 5: Per-question detail in report
Step 6: Markdown output format
Step 7: Cost tracking in report
```

### Step 1: Expand Dataset — Raise Question Caps

**Current state:** `_MAX_REGISTERS_PER_PERIPHERAL = 3`, `_MAX_FIELDS_PER_REGISTER = 3`, `num_peripherals = 10` → ~57 questions for STM32F407.

**Change:** Raise defaults to produce 200+ questions:
- `_MAX_REGISTERS_PER_PERIPHERAL`: 3 → 8
- `_MAX_FIELDS_PER_REGISTER`: 3 → 5
- `num_peripherals` default: 10 → 20
- Add `--thorough` flag for even larger datasets (all peripherals, all registers)

**Expected yield:** ~200-250 questions for STM32F407 with raised caps.

**Why 200+:** Statistical rule of thumb — Wilson CI at 95% with n=200 gives ±6.9% width for p=0.5. For p=0.95 (our expected hwcc_full accuracy), CI width is ±3.0%. This is tight enough to be meaningful.

### Step 2: Difficulty Tiers

Tag each question with a difficulty level based on objective criteria:

| Difficulty | Criteria | Examples |
|-----------|----------|---------|
| **easy** | Common peripheral + frequently memorized value | SPI1 base address, GPIOA base address |
| **medium** | Less common peripheral OR register-level detail | ADC1_CR1 offset, IWDG access type |
| **hard** | Obscure peripheral, specific field bits, non-zero reset values | FLASH_CR bit [31], CAN_FMR reset value |

**Implementation:** Score each question on 3 dimensions:
1. **Peripheral commonality**: Priority rank from `_PRIORITY_PERIPHERALS` (top 5 = easy, 6-10 = medium, rest = hard)
2. **Category difficulty**: base_address = easy, register_offset/access_type = medium, bit_field/reset_value = hard
3. **Specificity**: 1-bit fields = harder, non-zero reset values = harder

Combined score maps to easy/medium/hard. Add `difficulty: str` field to `BenchQuestion`.

### Step 3: Multi-Run Aggregation

**Current:** Single run per condition, temperature hardcoded to 0.0.

**Change:** Add `--runs N` (default 1) to `bench run`. Each run repeats all questions. Results are aggregated:
- Per-question: majority vote correctness + agreement rate
- Per-condition: mean accuracy ± std across runs
- Total: statistical tests use aggregated data

Even at temperature=0, multi-run captures provider non-determinism (API routing, load balancing, model updates).

**Data model change:**
```python
@dataclass(frozen=True)
class BenchRunGroup:
    """Aggregated results from multiple runs of same condition."""
    condition: str
    runs: tuple[BenchRun, ...]
    mean_accuracy: float
    std_accuracy: float
    ci_lower: float  # 95% Wilson CI
    ci_upper: float
```

### Step 4: Statistical Framework

Add to `scoring.py`:

1. **Wilson score interval** for accuracy confidence intervals:
   ```
   CI = (p + z²/2n ± z√(p(1-p)/n + z²/4n²)) / (1 + z²/n)
   ```
   Used for each condition's accuracy. No external dependencies (pure math).

2. **McNemar's test** for paired binary outcomes:
   Tests whether the accuracy difference between no_context and hwcc_full is statistically significant, not just random.
   ```
   χ² = (b - c)² / (b + c)
   ```
   Where b = questions correct in hwcc_full but wrong in no_context, c = vice versa. p-value from chi-squared distribution (scipy.stats if available, else lookup table).

3. **Per-difficulty accuracy breakdown** in BenchMetrics.

### Step 5: Per-Question Detail Table

Add to report output: a full table showing every question, expected answer, model answer, correct/wrong, confidence, latency. This enables:
- **Auditability**: Anyone can verify scoring is correct
- **Failure analysis**: See exactly what the model gets wrong
- **Cherry-pick examples**: Find the most dramatic correct/wrong examples for blog posts

### Step 6: Markdown Output

Add `--output-format markdown` (or `--markdown`) to `bench run` and `bench report`. Produces a `.md` file with:
- Summary table (condition × accuracy with CI)
- Per-category breakdown table
- Per-difficulty breakdown table
- Significance test results (if multi-condition)
- Per-question detail table (collapsible `<details>` block)
- Metadata footer (model, date, dataset, chip)

The markdown is designed to be copy-pasted into README.md or a blog post.

### Step 7: Cost Tracking

Track estimated USD cost per run:
- Claude API: input_tokens × rate + output_tokens × rate
- OpenAI: same
- Ollama: $0.00 (local)
- Claude Code CLI: "included in subscription"

Add `cost_usd: float` to `BenchRun`. Display in report as "Estimated cost: $X.XX". This matters because it shows hwcc context is cost-effective: the token cost increase is tiny compared to the accuracy gain.

---

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Expand dataset caps | `dataset.py` | Raise `_MAX_REGISTERS_PER_PERIPHERAL` to 8, `_MAX_FIELDS_PER_REGISTER` to 5, default peripherals to 20 |
| 2 | Add difficulty field | `types.py`, `dataset.py` | Add `difficulty: str` to `BenchQuestion`, implement scoring heuristic |
| 3 | Add difficulty tests | `test_bench_dataset.py` | Verify difficulty distribution, all questions tagged |
| 4 | Add `StatisticalSummary` | `types.py` | New dataclass with CI, p-value fields |
| 5 | Wilson CI function | `scoring.py` | `wilson_ci(successes, trials, z=1.96) -> tuple[float, float]` |
| 6 | McNemar's test function | `scoring.py` | `mcnemar_test(a_results, b_results) -> tuple[float, float]` (statistic, p-value) |
| 7 | Statistical tests | `test_bench_scoring.py` | Test Wilson CI against known values, McNemar's edge cases |
| 8 | Multi-run support | `runner.py`, `types.py` | `--runs N` in runner, aggregate across runs |
| 9 | Multi-run tests | `test_bench_runner.py` | Test N=1 and N=3 aggregation |
| 10 | Expand `BenchMetrics` | `types.py`, `scoring.py` | Add CI fields, per-difficulty dict, update `compute_metrics` |
| 11 | Per-question detail | `report.py` | Add detail table to `print_report`, include in JSON |
| 12 | Markdown output | `report.py` | `print_report_markdown(report, path)` function |
| 13 | Markdown tests | `test_bench_report.py` | Verify markdown contains tables, CI, metadata |
| 14 | Cost tracking | `types.py`, `runner.py`, `report.py` | Add `cost_usd` to `BenchRun`, estimate in runner, display in report |
| 15 | CLI flags | `cli.py` | Add `--runs`, `--output-format` to bench commands |
| 16 | Expand metrics with difficulty | `scoring.py`, `report.py` | Per-difficulty accuracy in metrics and display |

---

## Test Plan

### Unit Tests

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Expanded dataset produces 200+ questions from STM32-like SVD | `test_bench_dataset.py` | unit |
| 2 | Every question has a valid difficulty tag (easy/medium/hard) | `test_bench_dataset.py` | unit |
| 3 | Difficulty distribution is reasonable (not all one tier) | `test_bench_dataset.py` | unit |
| 4 | `wilson_ci(50, 100)` returns correct bounds (~0.40, 0.60) | `test_bench_scoring.py` | unit |
| 5 | `wilson_ci(95, 100)` returns tight bounds (~0.89, 0.98) | `test_bench_scoring.py` | unit |
| 6 | `wilson_ci(0, 0)` handles edge case (0 trials) | `test_bench_scoring.py` | unit |
| 7 | `mcnemar_test` with identical results returns p≈1.0 | `test_bench_scoring.py` | unit |
| 8 | `mcnemar_test` with very different results returns p<0.05 | `test_bench_scoring.py` | unit |
| 9 | Multi-run aggregation computes mean/std correctly | `test_bench_runner.py` | unit |
| 10 | Multi-run with N=1 degrades gracefully (no std) | `test_bench_runner.py` | unit |
| 11 | Markdown output contains summary table | `test_bench_report.py` | unit |
| 12 | Markdown output contains CI values | `test_bench_report.py` | unit |
| 13 | Markdown output contains per-question detail | `test_bench_report.py` | unit |
| 14 | Per-question detail table in JSON round-trips | `test_bench_report.py` | unit |
| 15 | Cost tracking: Anthropic provider estimates cost | `test_bench_runner.py` | unit |
| 16 | Cost tracking: Ollama reports $0.00 | `test_bench_runner.py` | unit |
| 17 | Per-difficulty metrics in compute_metrics | `test_bench_scoring.py` | unit |

### Acceptance Criteria (Testable)

| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | `hwcc bench generate large.svd` | 200+ questions with difficulty tags | automated |
| 2 | `hwcc bench run --runs 3 dataset.json` | Report with CI, mean ± std | automated (mock) |
| 3 | Report shows "93.2% (95% CI: 89.1%–96.1%)" format | CI in both Rich and markdown | automated |
| 4 | Markdown output pasteable into README | Valid markdown, renders in GitHub | manual |
| 5 | Per-question table shows every Q&A pair | All questions visible with scores | automated |
| 6 | McNemar's p-value reported for condition comparison | "p < 0.001" or similar | automated |

---

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/bench/types.py` | modify | Add `difficulty` to `BenchQuestion`, `StatisticalSummary`, CI fields to `BenchMetrics`, `cost_usd` to `BenchRun` |
| `src/hwcc/bench/dataset.py` | modify | Raise caps, add difficulty scoring heuristic |
| `src/hwcc/bench/runner.py` | modify | Multi-run loop, cost estimation |
| `src/hwcc/bench/scoring.py` | modify | Wilson CI, McNemar's test, per-difficulty metrics |
| `src/hwcc/bench/report.py` | modify | Markdown output, per-question detail, CI display, cost display |
| `src/hwcc/cli.py` | modify | `--runs`, `--output-format` flags |
| `tests/test_bench_dataset.py` | modify | Expanded dataset tests, difficulty tests |
| `tests/test_bench_scoring.py` | modify | Statistical function tests |
| `tests/test_bench_runner.py` | modify | Multi-run tests, cost tracking tests |
| `tests/test_bench_report.py` | modify | Markdown output tests, per-question detail tests |

## Files to Create

| File | Purpose |
|------|---------|
| None | All changes are additions to existing files |

---

## Exit Criteria

```
□ Dataset generates 200+ questions for STM32F407 SVD (up from ~57)
□ Every question has difficulty: easy | medium | hard
□ Wilson CI computed for every accuracy value
□ McNemar's test computed for no_context vs hwcc comparison
□ --runs N works and aggregates correctly
□ Markdown output is valid, pasteable, contains CI and tables
□ Per-question detail table included in both JSON and markdown
□ Cost tracking works for all providers
□ All existing tests still pass (no regressions)
□ All new tests pass
□ No ruff violations
□ No mypy errors
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched
```

## Verification Strategy

- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] Manual test: `hwcc bench generate .rag/hardware/STM32F407.svd` produces 200+ questions
- [ ] Manual test: `hwcc bench run --runs 1 dataset.json --provider claude_code` works
- [ ] Manual test: Markdown output renders in GitHub preview
- [ ] No unintended side effects in: core pipeline, existing CLI, existing tests

## Document Updates Needed

- [ ] **TECH_SPEC.md:** None (benchmark is separate from core pipeline)
- [ ] **PLAN.md:** Note benchmark credibility as complete when done
- [ ] **README.md:** Update benchmark section with CI-annotated results after first real run

---

## Execution Order Recommendation

The steps have natural dependencies:

```
Step 1 (expand dataset) ─── independent, do first
Step 2 (difficulty)     ─── depends on Step 1 (needs more questions to stratify)
Step 3 (difficulty tests) ─ depends on Step 2

Step 4 (StatisticalSummary type) ── foundation for 5, 6, 8, 10
Step 5 (Wilson CI)      ─── depends on Step 4
Step 6 (McNemar's)      ─── depends on Step 4
Step 7 (stat tests)     ─── depends on Steps 5, 6

Step 8 (multi-run)      ─── depends on Steps 4, 5
Step 9 (multi-run tests) ── depends on Step 8

Step 10 (expand metrics) ── depends on Steps 2, 5, 6
Step 11 (per-question)  ─── independent
Step 12 (markdown)      ─── depends on Steps 5, 10, 11
Step 13 (markdown tests) ── depends on Step 12
Step 14 (cost tracking) ─── independent
Step 15 (CLI flags)     ─── depends on Steps 8, 12
Step 16 (difficulty metrics) ── depends on Steps 2, 10
```

Suggested execution phases:
1. **Phase A** (foundation): Steps 1, 2, 3, 4, 11, 14
2. **Phase B** (statistics): Steps 5, 6, 7, 8, 9, 10, 16
3. **Phase C** (output): Steps 12, 13, 15

---

> **Last Updated:** 2026-03-02

# Plan: HwBench — Hardware Context Benchmark Suite

> **Date**: 2026-03-02
> **Status**: Draft — pending review
> **Research**: `/research` session on hwcc benchmarking strategies

---

## Scope Declaration

- **Type:** feature
- **Single Concern:** Create a benchmark suite that quantitatively proves hwcc's value by measuring LLM accuracy on hardware register questions with and without hwcc context
- **Phase:** New (not in existing PLAN.md phases — this is a validation/marketing tool)
- **Complexity:** High (new module with dataset generation, LLM API integration, scoring, reporting)
- **Risk:** Medium (new external API dependencies, but isolated from core pipeline)

### Concern Separation Rule

This change is ONLY about: building the benchmark infrastructure and dataset generation
This change is NOT about:
- Improving hwcc's core pipeline (ingest/chunk/embed/store/compile)
- Adding new parsers or embedding providers
- Changing existing CLI commands or data contracts
- Implementing the MCP server or search features

---

## Problem Statement

**What:** hwcc claims AI coding tools hallucinate register addresses without proper hardware context. We need to PROVE this quantitatively with reproducible benchmarks.

**Why:** Without numbers, hwcc is just a claim. With numbers like "accuracy improves from 35% to 97%", it becomes undeniable value. This is critical for:
- README/landing page credibility
- Blog posts and conference talks
- Comparison with competitors (Embedder, EmbedGenius)
- User confidence in adopting hwcc

**Success:** Running `hwcc bench run` produces a JSON report showing per-model, per-condition accuracy metrics. The delta between "no context" and "hwcc context" conditions proves hwcc's value.

### Unique Advantage

Hardware register data has **binary ground truth** — `0x40013000` is either correct or wrong. No subjective judgment needed. hwcc's SVD parser already extracts this data, so we can auto-generate unlimited Q&A pairs from any MCU's SVD file. No other benchmark tests register-level code generation accuracy.

---

## Impact Analysis

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/bench/__init__.py` | create | Module init with `__all__` |
| `src/hwcc/bench/types.py` | create | Frozen dataclass contracts |
| `src/hwcc/bench/dataset.py` | create | SVD → Q&A generator |
| `src/hwcc/bench/runner.py` | create | LLM API benchmark executor |
| `src/hwcc/bench/scoring.py` | create | Response scoring engine |
| `src/hwcc/bench/report.py` | create | Report generation (JSON + Rich) |
| `src/hwcc/bench/providers.py` | create | LLM provider abstraction (Anthropic, OpenAI, Ollama) |
| `src/hwcc/cli.py` | modify | Add `hwcc bench` command group |
| `src/hwcc/exceptions.py` | modify | Add `BenchmarkError` |
| `pyproject.toml` | modify | Add `[project.optional-dependencies] bench = [...]` |
| `tests/test_bench_dataset.py` | create | Dataset generation tests |
| `tests/test_bench_scoring.py` | create | Scoring engine tests |
| `tests/test_bench_report.py` | create | Report generation tests |

### Dependency Chain

| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `bench/dataset.py` | CLI `hwcc bench generate`, tests | `hwcc.ingest.svd.SvdParser`, `cmsis_svd` |
| `bench/runner.py` | CLI `hwcc bench run` | `bench/providers.py`, `bench/scoring.py` |
| `bench/scoring.py` | `bench/runner.py`, tests | Pure logic (no deps) |
| `bench/report.py` | CLI `hwcc bench run` | `rich`, JSON stdlib |
| `bench/providers.py` | `bench/runner.py` | `anthropic`, `openai`, `httpx` (optional deps) |

### Pipeline Impact

| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| None | Benchmark is read-only — uses SVD parser and compiled context but doesn't modify pipeline | Benchmark results inform development priorities |

### NON-GOALS (Explicitly Out of Scope)

- [ ] Modifying the core pipeline (ingest/chunk/embed/store/compile) — benchmark is read-only
- [ ] Adding new parsers or embedding providers
- [ ] End-to-end hardware testing (compile + flash + run) — requires physical hardware
- [ ] Multi-LLM comparison as the primary goal — primary comparison is with/without context
- [ ] GUI or web dashboard — console + JSON only
- [ ] Raw PDF context condition — requires manual PDF excerpt preparation (deferred)
- [ ] Category C-E tasks (driver code, errata, pin knowledge) — manual creation, deferred
- [ ] Matplotlib/plotly visualization — deferred to a future enhancement

---

## Technical Approach

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                    hwcc bench                        │
│                                                     │
│  ┌──────────┐   ┌──────────┐   ┌────────────────┐ │
│  │ Dataset  │──▶│  Runner  │──▶│    Report       │ │
│  │ Generator│   │          │   │  (JSON + Rich)  │ │
│  └──────────┘   └──────────┘   └────────────────┘ │
│       │              │                              │
│       │              ▼                              │
│       │         ┌──────────┐                        │
│       │         │ Scoring  │                        │
│       │         │ Engine   │                        │
│       │         └──────────┘                        │
│       │              │                              │
│       ▼              ▼                              │
│  ┌──────────┐   ┌──────────┐                        │
│  │ SVD      │   │ LLM      │                        │
│  │ Parser   │   │ Providers│                        │
│  │ (reused) │   │ (new)    │                        │
│  └──────────┘   └──────────┘                        │
└─────────────────────────────────────────────────────┘
```

### Data Contracts (`bench/types.py`)

```python
@dataclass(frozen=True)
class BenchQuestion:
    """A single benchmark question with ground truth answer."""
    id: str                    # "spi1_base_address"
    category: str              # "base_address" | "register_offset" | "bit_field" | "reset_value" | "access_type"
    peripheral: str            # "SPI1"
    register: str              # "CR1" (empty for base_address questions)
    field: str                 # "BR" (empty for register-level questions)
    question: str              # Human-readable question text
    answer: str                # Ground truth: "0x40013000"
    answer_format: str         # "hex" | "bit_range" | "access_code"

@dataclass(frozen=True)
class BenchDataset:
    """Collection of benchmark questions from a single SVD source."""
    name: str                  # "STM32F407_RegisterKnowledge"
    chip: str                  # "STM32F407"
    source_svd: str            # Path to SVD file used
    question_count: int
    questions: tuple[BenchQuestion, ...]
    created: str               # ISO timestamp
    categories: tuple[str, ...] # Unique categories present

@dataclass(frozen=True)
class BenchResponse:
    """Result of asking one question to one LLM."""
    question_id: str
    raw_response: str          # Full LLM response
    extracted_answer: str      # Parsed answer extracted from response
    correct: bool
    score: float               # 0.0 or 1.0 (exact match)
    latency_ms: float          # API response time

@dataclass(frozen=True)
class BenchCondition:
    """A test condition (context variation)."""
    name: str                  # "no_context" | "hwcc_hot" | "hwcc_peripheral" | "hwcc_full"
    system_prompt: str         # System prompt including any context
    description: str           # Human-readable description

@dataclass(frozen=True)
class BenchRun:
    """Complete benchmark run results."""
    dataset_name: str
    condition: str             # Condition name
    model: str                 # "claude-sonnet-4-6"
    provider: str              # "anthropic" | "openai" | "ollama"
    temperature: float
    responses: tuple[BenchResponse, ...]
    started: str               # ISO timestamp
    completed: str
    total_tokens: int          # Total tokens consumed

@dataclass(frozen=True)
class BenchMetrics:
    """Aggregated metrics for a benchmark run."""
    total: int
    correct: int
    accuracy: float            # correct / total
    hallucination_rate: float  # (total - correct) / total
    by_category: dict[str, float]  # category → accuracy
    avg_latency_ms: float
    total_tokens: int

@dataclass(frozen=True)
class BenchReport:
    """Complete benchmark report across all conditions."""
    chip: str
    dataset_name: str
    runs: tuple[BenchRun, ...]
    metrics: dict[str, BenchMetrics]  # condition_name → metrics
    comparison: dict[str, float]      # "accuracy_delta", "hallucination_reduction"
```

### Question Categories (Category A — Register Knowledge)

Generated automatically from SVD data. 5 question types per peripheral/register/field:

| Category | Question Template | Answer Format | Example |
|----------|------------------|---------------|---------|
| `base_address` | "What is the base address of {peripheral} on the {chip}?" | `0xNNNNNNNN` | `0x40013000` |
| `register_offset` | "What is the address offset of the {register} register in {peripheral}?" | `0xNNNN` | `0x0000` |
| `bit_field` | "What bit position(s) does the {field} field occupy in {peripheral}_{register}?" | `[N:M]` or `[N]` | `[5:3]` |
| `reset_value` | "What is the reset value of {peripheral}_{register}?" | `0xNNNNNNNN` | `0x00000002` |
| `access_type` | "What is the access type of {peripheral}_{register}?" | `RO`/`RW`/`WO` | `RO` |

**Sampling strategy**: Not all registers/fields make good questions. Selection criteria:
- Only peripherals with `base_address is not None`
- Only registers with `address_offset is not None`
- Only fields with `bit_offset is not None and bit_width is not None`
- Sample: all 5 question types for a configurable number of peripherals (default: 10)
- Per peripheral: 1 base_address + up to 3 register questions + up to 3 field questions

**Expected yield**: ~50-70 questions from STM32F407 SVD (68 peripherals, thousands of registers — sample the most common ones: SPI, USART, TIM, GPIO, RCC, DMA, ADC, I2C, CAN, DAC).

### Benchmark Conditions

| Condition | System Prompt Content | Token Cost |
|-----------|----------------------|------------|
| `no_context` | Generic HW engineer prompt, no docs | ~50 tokens |
| `hwcc_hot` | hwcc `hot.md` only (~120 lines) | ~500 tokens |
| `hwcc_peripheral` | hwcc peripheral context for the specific peripheral | ~200-2000 tokens |
| `hwcc_full` | `hot.md` + all relevant peripheral context | ~1000-5000 tokens |

**Prompt template:**

```
System: You are a hardware engineer working with the {chip} microcontroller.
{context_block}

Answer the following question about {chip} hardware.
Reply with ONLY the exact value. No explanation, no units, no surrounding text.

Question: {question}
```

The `{context_block}` varies by condition:
- `no_context`: empty
- `hwcc_hot`: contents of `hot.md`
- `hwcc_peripheral`: contents of the relevant peripheral file from `.rag/context/peripherals/`
- `hwcc_full`: `hot.md` + relevant peripheral file

### LLM Provider Abstraction (`bench/providers.py`)

```python
class BaseBenchProvider(ABC):
    """Abstract LLM provider for benchmarking."""

    @abstractmethod
    def query(self, system_prompt: str, user_prompt: str) -> ProviderResponse: ...

    @abstractmethod
    def name(self) -> str: ...

@dataclass(frozen=True)
class ProviderResponse:
    text: str
    tokens_used: int
    latency_ms: float

class AnthropicProvider(BaseBenchProvider): ...  # Uses anthropic SDK
class OpenAIProvider(BaseBenchProvider): ...     # Uses openai SDK
class OllamaProvider(BaseBenchProvider): ...     # Uses httpx to local Ollama
```

Providers are configured via environment variables:
- `ANTHROPIC_API_KEY` for Anthropic
- `OPENAI_API_KEY` for OpenAI
- `OLLAMA_HOST` for Ollama (default: `http://localhost:11434`)

### Scoring Engine (`bench/scoring.py`)

Answer extraction and comparison logic:

```python
def extract_answer(raw_response: str, answer_format: str) -> str:
    """Extract the answer value from an LLM response.

    Handles common response patterns:
    - "The base address is 0x40013000" → "0x40013000"
    - "0x40013000" → "0x40013000"
    - "[5:3]" → "[5:3]"
    - "RO (read-only)" → "RO"
    """

def normalize_hex(value: str) -> str:
    """Normalize hex values: strip leading zeros, uppercase, ensure 0x prefix."""

def normalize_bit_range(value: str) -> str:
    """Normalize bit ranges: [5:3], bits 5-3, bit 5 to bit 3 → [5:3]."""

def normalize_access(value: str) -> str:
    """Normalize access types: read-only → RO, read/write → RW, etc."""

def score_answer(extracted: str, ground_truth: str, answer_format: str) -> float:
    """Score 0.0 or 1.0 based on exact normalized match."""
```

### CLI Commands

```
hwcc bench generate <svd-file> [--output bench_dataset.json] [--peripherals 10]
    → Generate dataset from SVD file

hwcc bench run <dataset.json> [--model claude-sonnet-4-6] [--provider anthropic]
    [--conditions no_context,hwcc_full] [--context-dir .rag/context/]
    [--output results.json] [--temperature 0]
    → Run benchmark

hwcc bench report <results.json> [--format table|json]
    → Display results
```

### CLI Integration Pattern

Following the existing pattern in `cli.py`, add a Typer sub-app:

```python
bench_app = typer.Typer(name="bench", help="Hardware context benchmark suite.")
app.add_typer(bench_app)

@bench_app.command(name="generate")
def bench_generate(...) -> None: ...

@bench_app.command(name="run")
def bench_run(...) -> None: ...

@bench_app.command(name="report")
def bench_report(...) -> None: ...
```

---

## Implementation Steps

### Step 1: Data Contracts and Exception

| Task | File(s) | Description |
|------|---------|-------------|
| 1.1 | `src/hwcc/bench/__init__.py` | Create module with `__all__` |
| 1.2 | `src/hwcc/bench/types.py` | All frozen dataclass contracts (BenchQuestion, BenchDataset, BenchResponse, BenchCondition, BenchRun, BenchMetrics, BenchReport) |
| 1.3 | `src/hwcc/exceptions.py` | Add `BenchmarkError(HwccError)` |

### Step 2: Dataset Generator

| Task | File(s) | Description |
|------|---------|-------------|
| 2.1 | `src/hwcc/bench/dataset.py` | `generate_dataset(svd_path, num_peripherals, chip)` — parse SVD, select peripherals, generate Q&A pairs |
| 2.2 | `src/hwcc/bench/dataset.py` | `save_dataset(dataset, path)` / `load_dataset(path)` — JSON serialization |
| 2.3 | `src/hwcc/bench/dataset.py` | Question templates for 5 categories with chip/peripheral/register/field interpolation |
| 2.4 | `src/hwcc/bench/dataset.py` | Peripheral selection heuristic: prioritize common peripherals (SPI, USART, TIM, GPIO, RCC, DMA, ADC, I2C, CAN, DAC) by matching names |
| 2.5 | `tests/test_bench_dataset.py` | Test dataset generation from SVD fixture, verify question count, category distribution, answer formats |

### Step 3: Scoring Engine

| Task | File(s) | Description |
|------|---------|-------------|
| 3.1 | `src/hwcc/bench/scoring.py` | `extract_answer()` — regex-based extraction from LLM responses |
| 3.2 | `src/hwcc/bench/scoring.py` | Normalization functions: `normalize_hex()`, `normalize_bit_range()`, `normalize_access()` |
| 3.3 | `src/hwcc/bench/scoring.py` | `score_answer()` — normalized exact match scoring |
| 3.4 | `src/hwcc/bench/scoring.py` | `compute_metrics()` — aggregate BenchResponse list into BenchMetrics |
| 3.5 | `tests/test_bench_scoring.py` | Test all normalizers, extractors, and scoring with edge cases |

### Step 4: LLM Provider Abstraction

| Task | File(s) | Description |
|------|---------|-------------|
| 4.1 | `src/hwcc/bench/providers.py` | `BaseBenchProvider` ABC with `query()` and `name` |
| 4.2 | `src/hwcc/bench/providers.py` | `AnthropicProvider` using `anthropic` SDK |
| 4.3 | `src/hwcc/bench/providers.py` | `OpenAIProvider` using `openai` SDK |
| 4.4 | `src/hwcc/bench/providers.py` | `OllamaProvider` using `httpx` to local API |
| 4.5 | `src/hwcc/bench/providers.py` | `create_provider(name, model, **kwargs)` factory function |
| 4.6 | `pyproject.toml` | Add `bench = ["anthropic>=0.40", "openai>=1.50", "httpx>=0.27"]` optional dep group |

### Step 5: Benchmark Runner

| Task | File(s) | Description |
|------|---------|-------------|
| 5.1 | `src/hwcc/bench/runner.py` | `prepare_conditions(context_dir, chip)` — build BenchCondition list from available context files |
| 5.2 | `src/hwcc/bench/runner.py` | `run_benchmark(dataset, provider, conditions, temperature)` — execute all questions under each condition, return list of BenchRun |
| 5.3 | `src/hwcc/bench/runner.py` | Progress display with Rich progress bar |
| 5.4 | `src/hwcc/bench/runner.py` | Rate limiting and retry logic (configurable delay between calls) |

### Step 6: Report Generator

| Task | File(s) | Description |
|------|---------|-------------|
| 6.1 | `src/hwcc/bench/report.py` | `generate_report(runs)` — compute BenchReport with cross-condition comparison |
| 6.2 | `src/hwcc/bench/report.py` | `print_report(report)` — Rich table output with color-coded accuracy |
| 6.3 | `src/hwcc/bench/report.py` | `save_report(report, path)` — JSON serialization |
| 6.4 | `tests/test_bench_report.py` | Test metric computation and JSON round-trip |

### Step 7: CLI Integration

| Task | File(s) | Description |
|------|---------|-------------|
| 7.1 | `src/hwcc/cli.py` | Add `bench_app` Typer sub-app with `generate`, `run`, `report` commands |
| 7.2 | `src/hwcc/cli.py` | `bench generate` — parse SVD, save dataset JSON |
| 7.3 | `src/hwcc/cli.py` | `bench run` — load dataset, create provider, execute, save results |
| 7.4 | `src/hwcc/cli.py` | `bench report` — load results, compute metrics, display |

### Step 8: Integration Testing

| Task | File(s) | Description |
|------|---------|-------------|
| 8.1 | `tests/test_bench_dataset.py` | End-to-end: SVD file → dataset → JSON → reload |
| 8.2 | `tests/test_bench_scoring.py` | End-to-end: mock responses → scoring → metrics |
| 8.3 | Create SVD test fixture | Small SVD with 2-3 peripherals for testing |

---

## Test Plan

### Unit Tests

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Dataset generation from SVD produces correct question count | `tests/test_bench_dataset.py` | unit |
| 2 | Each question category has correct answer format | `tests/test_bench_dataset.py` | unit |
| 3 | Base address questions have correct hex answers from SVD | `tests/test_bench_dataset.py` | unit |
| 4 | Bit field questions have correct [MSB:LSB] format | `tests/test_bench_dataset.py` | unit |
| 5 | Dataset JSON round-trip preserves all fields | `tests/test_bench_dataset.py` | unit |
| 6 | Peripheral selection prioritizes common peripherals | `tests/test_bench_dataset.py` | unit |
| 7 | `normalize_hex("40013000")` → `"0x40013000"` | `tests/test_bench_scoring.py` | unit |
| 8 | `normalize_hex("0x0040013000")` → `"0x40013000"` | `tests/test_bench_scoring.py` | unit |
| 9 | `normalize_bit_range("bits 5-3")` → `"[5:3]"` | `tests/test_bench_scoring.py` | unit |
| 10 | `normalize_bit_range("[5]")` → `"[5]"` | `tests/test_bench_scoring.py` | unit |
| 11 | `normalize_access("read-only")` → `"RO"` | `tests/test_bench_scoring.py` | unit |
| 12 | `extract_answer("The base address is 0x40013000", "hex")` extracts correctly | `tests/test_bench_scoring.py` | unit |
| 13 | `extract_answer("0x40013000", "hex")` extracts bare value | `tests/test_bench_scoring.py` | unit |
| 14 | `score_answer("0x40013000", "0x40013000", "hex")` → 1.0 | `tests/test_bench_scoring.py` | unit |
| 15 | `score_answer("0x40013001", "0x40013000", "hex")` → 0.0 | `tests/test_bench_scoring.py` | unit |
| 16 | `compute_metrics(responses)` produces correct accuracy | `tests/test_bench_scoring.py` | unit |
| 17 | `compute_metrics` computes per-category accuracy | `tests/test_bench_scoring.py` | unit |
| 18 | Report JSON serialization round-trip | `tests/test_bench_report.py` | unit |
| 19 | Report Rich table renders without error | `tests/test_bench_report.py` | unit |
| 20 | BenchmarkError is in exception hierarchy | `tests/test_bench_scoring.py` | unit |

### Acceptance Criteria (Testable)

| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | `hwcc bench generate tests/fixtures/mini.svd` | JSON file with 10+ questions | automated |
| 2 | Dataset from STM32F407.svd | 50+ questions across 5 categories | automated |
| 3 | Scoring engine: 100 mock responses | Correct accuracy calculation | automated |
| 4 | `hwcc bench run` with mock provider | Produces BenchRun with all responses | automated |
| 5 | `hwcc bench report` displays Rich table | No errors, readable output | manual |
| 6 | Full pipeline: generate → run → report | End-to-end success | manual (needs API key) |

---

## Files to Create

| File | Purpose |
|------|---------|
| `src/hwcc/bench/__init__.py` | Module init, public API |
| `src/hwcc/bench/types.py` | Frozen dataclass contracts |
| `src/hwcc/bench/dataset.py` | SVD → Q&A dataset generator |
| `src/hwcc/bench/scoring.py` | Answer extraction and scoring |
| `src/hwcc/bench/providers.py` | LLM provider abstraction |
| `src/hwcc/bench/runner.py` | Benchmark execution engine |
| `src/hwcc/bench/report.py` | Report generation (JSON + Rich) |
| `tests/test_bench_dataset.py` | Dataset generation tests |
| `tests/test_bench_scoring.py` | Scoring engine tests |
| `tests/test_bench_report.py` | Report generation tests |

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/cli.py` | modify | Add `bench` sub-app with generate/run/report commands |
| `src/hwcc/exceptions.py` | modify | Add `BenchmarkError(HwccError)` |
| `pyproject.toml` | modify | Add `bench` optional dependency group |

---

## Dependency Management

### New Dependencies (optional, `bench` extra only)

| Package | Version | Purpose | Used By |
|---------|---------|---------|---------|
| `anthropic` | `>=0.40` | Claude API client | `AnthropicProvider` |
| `openai` | `>=1.50` | OpenAI API client | `OpenAIProvider` |

**Note**: `httpx` is already a transitive dependency of `anthropic`/`openai`, so `OllamaProvider` needs no additional dep. If neither `anthropic` nor `openai` is installed, `httpx` can be imported from `chromadb`'s deps or installed separately.

### Installation

```bash
pip install hwcc[bench]     # Install with benchmark dependencies
pip install -e ".[dev,bench]"  # Development with benchmarks
```

### No-API Workflow

`hwcc bench generate` and `hwcc bench report` work without API keys. Only `hwcc bench run` requires a provider SDK and API key. This allows:
1. Generate dataset from SVD (no API needed)
2. Share dataset JSON for others to run
3. Review reports from shared results JSON

---

## Expected Results

Based on EmbedGenius research and hwcc's architecture:

| Metric | no_context | hwcc_full | Delta |
|--------|-----------|-----------|-------|
| **Register Address Accuracy** | ~30-40% | ~95-99% | +55-69pp |
| **Hallucination Rate** | ~40-50% | ~1-5% | -35-49pp |
| **Bit Field Accuracy** | ~15-25% | ~90-97% | +65-82pp |
| **Reset Value Accuracy** | ~5-15% | ~85-95% | +70-90pp |
| **Access Type Accuracy** | ~40-60% | ~95-99% | +35-59pp |
| **Token Cost per Question** | ~50 tokens | ~500-2000 tokens | 10-40x more |

**Key insight**: The token cost increase (10-40x) is tiny compared to the accuracy improvement (2-6x). Cost per CORRECT answer is much lower with hwcc context.

---

## Estimated API Cost

For a full benchmark run (STM32F407, 60 questions, 4 conditions, 1 model):

| Component | Tokens | Cost (Claude Sonnet) |
|-----------|--------|---------------------|
| 60 questions × no_context | ~6K input + ~3K output | ~$0.02 |
| 60 questions × hwcc_hot | ~36K input + ~3K output | ~$0.12 |
| 60 questions × hwcc_peripheral | ~120K input + ~3K output | ~$0.40 |
| 60 questions × hwcc_full | ~180K input + ~3K output | ~$0.60 |
| **Total per model** | | **~$1.14** |
| **3 repetitions** | | **~$3.42** |
| **5 models × 3 reps** | | **~$17.10** |

Very affordable for the value of the data produced.

---

## Exit Criteria

```
□ `hwcc bench generate <svd>` produces valid dataset JSON from any SVD file
□ Dataset has 50+ questions across 5 categories for STM32F407
□ Scoring engine correctly normalizes and scores hex, bit range, and access type answers
□ `hwcc bench run` executes against at least one LLM provider (Anthropic)
□ `hwcc bench report` displays Rich table with per-condition accuracy
□ JSON report includes all metrics for programmatic consumption
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched (core pipeline unmodified)
□ All new code has type annotations (mypy strict)
□ Tests pass: pytest tests/
□ Lint passes: ruff check src/ tests/
□ Types pass: mypy src/hwcc/
```

## Verification Strategy

- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] Manual test: `hwcc bench generate examples/stm32f407-motor/docs/STM32F407.svd`
- [ ] Manual test: `hwcc bench run dataset.json --model claude-sonnet-4-6` (needs API key)
- [ ] No unintended side effects in: core pipeline, existing CLI commands, data contracts

## Document Updates Needed

- [ ] **TECH_SPEC.md:** None (benchmark is a separate tool, not part of the pipeline)
- [ ] **PLAN.md:** Add benchmark as a validation milestone
- [ ] **README.md:** Add benchmark section after first results are published

---

## Future Enhancements (Not This PR)

1. **Category B: Init Sequence Tasks** — manually authored, semi-automatic scoring via AST analysis
2. **Category C-E: Driver/Errata/Pin Tasks** — manual authoring
3. **Raw PDF Condition** — compare hwcc vs stuffing raw PDF text
4. **Compaction Resistance Test** — inject 50K tokens of conversation, then ask register questions
5. **Cross-MCU Generalization** — train on STM32F407, test on STM32F103
6. **Visualization** — matplotlib/plotly charts for blog posts
7. **CI Integration** — run benchmark on every hwcc release to track accuracy over time
8. **Leaderboard** — public results comparing LLMs on HwBench

---

## Gap Analysis vs. Latest Research (2025–2026 arXiv Review)

> Reviewed 2026-03-02 against 20+ recent arXiv papers. Conclusion: **v1 design is
> sound and validated by recent research. Gaps are enhancement opportunities, not
> fundamental flaws.**

### What the Plan Gets Right

- **SVD-as-ground-truth is validated** — [KGHaluBench](https://arxiv.org/abs/2602.07842)
  (Feb 2026) uses knowledge graphs as deterministic ground truth, same principle as our
  SVD approach.
- **Domain-specific RAG benchmarks are the trend** —
  [ChemRAG-Bench](https://arxiv.org/abs/2505.07671) (May 2025) is a domain-specific RAG
  benchmark for chemistry showing +17.4% accuracy from RAG. Validates our A/B methodology.
- **Expected accuracy delta is realistic** —
  [Fact Grounded Attention](https://arxiv.org/abs/2509.25252) (Oct 2025) tested Llama 3.2
  3B on 1,107 technical specs: vanilla=6.3%, with grounding=99.7%. Our expected 30–40% →
  95–99% is conservative.
- **EmbedAgent confirms the problem space** —
  [EmbedAgent](https://arxiv.org/abs/2506.11003) accepted at ICSE 2026. DeepSeek-R1
  achieves only 55.6% pass@1 even with schematics.

### Identified Gaps

| # | Gap | Current Plan | State of the Art | Severity | Priority |
|---|-----|-------------|-----------------|----------|----------|
| 1 | **Binary scoring only** | 0/1 exact match | [SemScore](https://arxiv.org/abs/2401.17072), [CodeBLEU](https://arxiv.org/abs/2503.01245), [RAGBench TRACe](https://arxiv.org/abs/2407.11005) use graded/partial-credit scoring | Medium | P2 |
| 2 | **No confidence calibration** | Not measured | [MACE/SCA](https://arxiv.org/abs/2602.07842) (Feb 2026) shows LLMs are systematically miscalibrated; verbalized confidence is now standard | Low | P3 |
| 3 | **Single-turn Q&A only** | Factual recall | [SWE-Compass](https://arxiv.org/abs/2511.05459), [AGENCYBENCH](https://arxiv.org/abs/2601.11044), [SWE-Bench Pro](https://arxiv.org/abs/2509.16941) evaluate multi-turn agentic tool-use | Low (v1) | P4 |
| 4 | **No security-aware questions** | 5 factual categories | [HardSecBench](https://arxiv.org/abs/2601.13864) (924 tasks, 76 CWEs) tests register security (write-once locks, privilege levels) | Low | P4 |
| 5 | **No RAG-specific quality metrics** | End-to-end accuracy only | [RAGBench TRACe](https://arxiv.org/abs/2407.11005) evaluates retrieval quality separately (context relevance, answer faithfulness, context utilization); [A-RAG](https://arxiv.org/abs/2602.03442) measures retrieval efficiency (tokens vs accuracy) | Medium | P3 |

### Recommended Roadmap

| Version | Enhancement | Effort | Value |
|---------|------------|--------|-------|
| **v1.0** | Ship as-is (binary scoring, 5 categories, A/B conditions) | Done | High |
| **v1.1** | Add partial credit scoring (hex distance, close-but-wrong detection) | Low | Medium |
| **v1.1** | Add confidence calibration ("how sure are you?" appended to prompt) | Low | Medium |
| **v1.2** | Add context utilization metric (what % of provided context was needed?) | Medium | High |
| **v2.0** | Multi-turn agentic evaluation (Category B: write init code, validate via AST) | Very High | Very High |
| **v2.0** | Security-aware register questions (Category C: write-once, privilege, lock bits) | High | Medium |

### Key References Added

| Paper | Year | Relevance |
|-------|------|-----------|
| [ChemRAG-Bench](https://arxiv.org/abs/2505.07671) | 2025 | Closest analog — domain-specific RAG benchmark |
| [KGHaluBench](https://arxiv.org/abs/2602.07842) | 2026 | Validates SVD-as-knowledge-graph ground truth |
| [Fact Grounded Attention](https://arxiv.org/abs/2509.25252) | 2025 | 6.3% → 99.7% on technical specs — validates expected delta |
| [RAGBench TRACe](https://arxiv.org/abs/2407.11005) | 2025 | Evaluation framework for retrieval quality |
| [RealBench](https://arxiv.org/abs/2507.16200) | 2025 | Real-world IP-level hardware specs as benchmark |
| [MACE/SCA](https://arxiv.org/abs/2602.07842) | 2026 | Confidence calibration for multi-answer questions |
| [SWE-Compass](https://arxiv.org/abs/2511.05459) | 2025 | Unified agentic coding benchmark (2000 instances) |
| [AGENCYBENCH](https://arxiv.org/abs/2601.11044) | 2026 | Long-horizon agentic benchmark (138 tasks, 1M tokens avg) |
| [HardSecBench](https://arxiv.org/abs/2601.13864) | 2026 | Security-aware hardware code generation (924 tasks) |

---

> **Last Updated:** 2026-03-02

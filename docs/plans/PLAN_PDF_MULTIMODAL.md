# Plan: PDF Multimodal — Timing Diagrams, Block Diagrams, Figures

## Scope Declaration
- **Type:** feature
- **Single Concern:** Add multimodal PDF parsing to hwcc so timing diagrams, block diagrams, pinouts, and other visual content in hardware datasheets are extracted and represented as searchable text
- **Phase:** v1.0 / Future (new feature, builds on Phase 1 ingest infrastructure)
- **Complexity:** High
- **Risk:** Medium (optional deps, graceful degradation required)

## Problem Statement
**What:** hwcc's PDF parser is text-only (`_TEXT_FLAGS = 11`, "suppress images"). All visual content in datasheets — timing diagrams, peripheral block diagrams, pinouts, waveforms — is silently dropped. Hardware datasheets are up to 50% visual content by page area.

**Why:** Timing diagrams contain information that does NOT exist in text form anywhere in the PDF. An AI coding tool that gets a timing spec chunk saying "SPI CLK setup time: 10ns, MOSI hold time: 5ns, CPOL=0, CPHA=0" writes correct HAL init code. Without it, the AI hallucinates timing parameters. This is the core value proposition of hwcc — giving AI the vendor knowledge it doesn't have.

**Success:**
1. `hwcc add rm0090.pdf` with `[ingest] pdf_backend = "docling"` extracts figure regions and inserts markdown placeholders at correct positions
2. `hwcc search "SPI timing"` can find chunks describing timing diagrams
3. With `[vision] provider = "claude_cli"`, figure placeholders include full Claude-quality captions — using existing subscription, no extra cost
4. `claude_cli` provider detects `CLAUDECODE` env var and falls back gracefully with a clear message when run inside Claude Code terminal
5. Without docling installed, parser gracefully falls back to existing text-only `PdfParser`
6. No changes to chunker, embedder, store, compile, or serve stages

---

## Research Findings (from /research + validation)

### Vision Provider Strategy (Validated 2026-03-03)

**`claude_cli` provider confirmed working:**
```bash
# Tested from standalone terminal:
claude -p "Read /tmp/test.png and describe what you see" --allowedTools Read
# → Correctly identified SPI timing diagram, described 4 signal traces,
#    noted square wave patterns and grid. Full Claude quality.
```

**Key constraint discovered:** `claude -p` is blocked inside Claude Code sessions
(`CLAUDECODE` env var prevents nested sessions). Falls back gracefully.

### Provider Priority (Final)

| Priority | Provider | Cost | Quality | Setup |
|---|---|---|---|---|
| 1st | `claude_cli` | Free (subscription) | Full Claude | Zero — already installed |
| 2nd | `ollama` | Free | Good (llama3.2-vision) | Install Ollama + model |
| 3rd | `anthropic` | ~$0.05/doc | Full Claude | API key required |
| 4th | `none` | Free | N/A (placeholders only) | Zero |

**SmolVLM dropped** — not competitive for technical timing diagrams. Local model
path covered by Ollama (better models, simpler interface, user already has it).

**Philosophy**: hwcc already says "LLM is optional". This extends: **VLM is optional
too. But if you have a Claude subscription, you already have everything you need.**

### Sources
- [SmolDocling (arXiv:2503.11576)](https://arxiv.org/abs/2503.11576) — 256M VLM for document conversion
- [Docling GitHub](https://github.com/docling-project/docling) — IBM MIT-licensed toolkit
- [TD-Interpreter (arXiv:2507.16844)](https://arxiv.org/abs/2507.16844) — timing diagram VQA (future: too specialized now)
- [SmolVLM (arXiv:2504.05299)](https://arxiv.org/abs/2504.05299) — evaluated, dropped (not competitive for technical diagrams)

---

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/config.py` | modify | Add `IngestConfig` and `VisionConfig` sections to `HwccConfig` |
| `src/hwcc/ingest/__init__.py` | modify | Add `DoclingPdfParser` to `_PARSER_MAP` under key `"pdf_docling"` |
| `src/hwcc/cli.py` | modify | Config-driven PDF parser selection: check `config.ingest.pdf_backend` |
| `pyproject.toml` | modify | Add optional deps: `docling` and `vision` extras |
| `src/hwcc/vision/__init__.py` | create | New module for vision providers |
| `src/hwcc/vision/base.py` | create | `BaseVisionProvider` ABC |
| `src/hwcc/vision/none.py` | create | `NullVisionProvider` (default, no-op) |
| `src/hwcc/vision/smolvlm.py` | create | `SmolVlmProvider` (SmolVLM-256M via transformers) |
| `src/hwcc/ingest/pdf_docling.py` | create | `DoclingPdfParser` — layout detection + figure extraction |
| `tests/test_ingest_pdf_docling.py` | create | Unit tests for DoclingPdfParser |
| `tests/test_vision_providers.py` | create | Unit tests for vision providers |
| `tests/test_config_ingest_vision.py` | create | Config load/save tests for new sections |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `HwccConfig` | `cli.py`, all pipeline code | `IngestConfig`, `VisionConfig` |
| `get_parser()` in `ingest/__init__.py` | `cli.py` | `_PARSER_MAP` |
| `cli.py` parser selection | user CLI commands | `get_parser()`, `Pipeline` |
| `DoclingPdfParser.parse()` | `Pipeline.process()` | `docling`, `BaseVisionProvider` |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| **Parse** (this change) | Reads config `ingest.pdf_backend` | `ParseResult.content` enriched with figure placeholders |
| **Chunk** | None — receives same `ParseResult` type | Handles figure placeholder markdown naturally (it's text) |
| **Embed** | None | None |
| **Store** | None | `content_type="diagram"` enables filter queries |
| **Compile** | None | None |
| **Serve (MCP)** | None | `hw_search` can match `content_type=timing_diagram` |

---

## NON-GOALS (Explicitly Out of Scope)

- [ ] **ColPali / visual retrieval** — fundamentally different architecture (visual page embeddings), future feature
- [ ] **TD-Interpreter fine-tuned model** — weights not yet public, too specialized for general use
- [ ] **Marker/Surya** — GPL license concerns, redundant with Docling
- [ ] **OCR for scanned PDFs** — different use case (Docling has OCR but it's heavy); existing text PDFs are the target
- [ ] **Changes to chunker, embedder, store, compiler, or serve** — pure parse stage change
- [ ] **Automatic figure type classification via VLM** — out of scope (VLM just does caption, classification is keyword-based heuristic)
- [ ] **Watch mode / auto-reindex** — separate future feature
- [ ] **Streaming / incremental figure processing** — not needed

---

## Technical Design

### New Config Sections

```toml
# .rag/config.toml

[ingest]
pdf_backend = "pymupdf"   # "pymupdf" (default, current behavior) | "docling"

[vision]
provider = "none"          # "none" (default) | "claude_cli" | "ollama" | "anthropic"
model = ""                 # ollama: "llama3.2-vision"; anthropic: "claude-haiku-4-5-20251001"
api_key_env = ""           # anthropic only: env var name for API key
```

**Recommended for Claude subscription users (zero extra setup):**
```toml
[ingest]
pdf_backend = "docling"

[vision]
provider = "claude_cli"   # uses your existing Claude subscription
```

### `BaseVisionProvider` ABC

```python
class BaseVisionProvider(ABC):
    @abstractmethod
    def caption_image(self, image_bytes: bytes, context: str = "") -> str:
        """Caption an image. Returns empty string if captioning fails."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if required deps are installed."""
```

### `DoclingPdfParser` Design

Three-pass architecture:
1. **Layout pass** — Docling `DocumentConverter.convert()` detects all elements: `Text`, `SectionHeader`, `Table`, `Figure`, `Caption`, `Formula`
2. **Figure extraction pass** — For each `Figure` element: extract image bytes + bbox + page number + nearby caption text
3. **Markdown assembly pass** — Merge text/table/figure elements in Y-position order:
   - Text → paragraph markdown
   - SectionHeader → `# heading` markdown
   - Table → existing `_render_table()` logic (reused from `PdfParser`)
   - Figure → captioned markdown block (see format below)

**Figure markdown format** (no VLM):
```markdown
<!-- FIGURE: page 12, type: figure, bbox: (120,340,480,620) -->
> **[Visual: Figure 8 — SPI timing diagram]**
> *Caption: Figure 8. SPI bus timing diagram showing signal relationships for full-duplex master mode.*
```

**Figure markdown format** (with VLM caption):
```markdown
<!-- FIGURE: page 12, type: timing_diagram, bbox: (120,340,480,620) -->
> **[Visual: Figure 8 — SPI timing diagram]**
> *Caption: Figure 8. SPI bus timing diagram showing signal relationships for full-duplex master mode.*
> *AI Description: Timing diagram with 5 signal traces: CLK (idle low, CPOL=0), NSS (active low chip select), MOSI (master-to-slave data), MISO (slave-to-master data), and SCK. Setup time labeled as tSU = 10ns. Hold time tHD = 5ns. Data transitions on falling CLK edge (CPHA=0). Full-duplex, 8-bit frame shown.*
```

### Figure Type Classification (keyword heuristic)

When no VLM, classify figure type from caption text using keywords:

| Keywords | `content_type` value |
|----------|---------------------|
| "timing", "waveform", "tsetup", "thold", "clock", "clk" | `"timing_diagram"` |
| "block diagram", "architecture", "peripheral", "bus", "ahb", "apb" | `"block_diagram"` |
| "pin", "pinout", "package", "qfp", "lqfp", "bga" | `"pinout"` |
| "schematic", "circuit", "transistor", "mosfet" | `"schematic_figure"` |
| any other figure | `"figure"` |

### Graceful Degradation Chain

```
config.ingest.pdf_backend == "docling"
    │
    ├── docling installed? ──No──> WARNING log + fall back to PdfParser
    │
    └── Yes
        │
        ├── config.vision.provider == "claude_cli"
        │       │
        │       ├── CLAUDECODE env var set? ──Yes──> WARNING:
        │       │       "Run hwcc add from a standalone terminal for captioning"
        │       │       → fall back to NullVisionProvider (placeholders only)
        │       │
        │       └── No ──> ClaudeCliVisionProvider
        │               subprocess: claude -p "Read {tmp_img} and describe..."
        │                           --allowedTools Read
        │
        ├── config.vision.provider == "ollama"
        │       └── OllamaVisionProvider (model from config.vision.model)
        │
        ├── config.vision.provider == "anthropic"
        │       └── AnthropicVisionProvider (API key from env var)
        │
        └── config.vision.provider == "none" ──> NullVisionProvider (no-op)
```

---

## Implementation Steps

### Phase A: Config + Foundation (no behavior change)

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| A1 | Add `IngestConfig` dataclass | `config.py` | `pdf_backend: str = "pymupdf"` |
| A2 | Add `VisionConfig` dataclass | `config.py` | `provider`, `model`, `api_key_env`, `base_url` |
| A3 | Register in `HwccConfig` | `config.py` | Add `ingest` and `vision` fields |
| A4 | Update `_config_to_dict` and `load_config` | `config.py` | Serialize/deserialize new sections |
| A5 | Write config tests | `tests/test_config_ingest_vision.py` | Load/save round-trip, defaults |

### Phase B: Vision Provider ABC + Null Implementation

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| B1 | Create `src/hwcc/vision/base.py` | new | `BaseVisionProvider` ABC with `caption_image()` and `is_available()` |
| B2 | Create `src/hwcc/vision/none.py` | new | `NullVisionProvider` — always returns `""`, `is_available()` → `True` |
| B3 | Create `src/hwcc/vision/__init__.py` | new | Export `BaseVisionProvider`, `NullVisionProvider`, `get_vision_provider()` factory |
| B4 | Write vision provider tests | `tests/test_vision_providers.py` | NullVisionProvider behavior |

### Phase C: DoclingPdfParser

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| C1 | Create `src/hwcc/ingest/pdf_docling.py` | new | `DoclingPdfParser(BaseParser)` skeleton with dependency check |
| C2 | Implement layout detection | `pdf_docling.py` | Docling `DocumentConverter.convert()`, iterate elements |
| C3 | Implement figure extraction | `pdf_docling.py` | Extract image bytes + bbox + nearby caption text |
| C4 | Implement figure type classification | `pdf_docling.py` | `_classify_figure_type(caption)` keyword heuristic |
| C5 | Implement markdown assembly | `pdf_docling.py` | Merge all elements in Y-order, generate figure blocks |
| C6 | Implement vision captioning integration | `pdf_docling.py` | `DoclingPdfParser.__init__(vision_provider)`, call `caption_image()` |
| C7 | Implement graceful fallback | `pdf_docling.py` | `ImportError` → log warning → return `PdfParser().parse(path, config)` |
| C8 | Register in `_PARSER_MAP` | `ingest/__init__.py` | Add `"pdf_docling": DoclingPdfParser` |
| C9 | Write DoclingPdfParser tests | `tests/test_ingest_pdf_docling.py` | Mock docling, verify markdown output, test fallback |

### Phase D: CLI Wiring

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| D1 | Config-driven parser selection | `cli.py` | After `detect_file_type`, if `info.parser_name == "pdf"` and `config.ingest.pdf_backend == "docling"`: use `"pdf_docling"` |
| D2 | Vision provider factory wiring | `cli.py` | Create vision provider from `config.vision.provider`, pass to `DoclingPdfParser` constructor |
| D3 | Write CLI integration test | `tests/test_cli_pdf_parser_selection.py` | Verify config routes to correct parser |

### Phase E: Vision Providers (claude_cli + ollama + anthropic)

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| E1 | Create `src/hwcc/vision/claude_cli.py` | new | `ClaudeCliVisionProvider` — subprocess `claude -p "Read {path}..." --allowedTools Read` |
| E2 | Detect `CLAUDECODE` env var | `claude_cli.py` | If set, `is_available()` returns False with logged warning message |
| E3 | Temp file management | `claude_cli.py` | Write image bytes to `tempfile.NamedTemporaryFile`, clean up after subprocess |
| E4 | Create `src/hwcc/vision/ollama.py` | new | `OllamaVisionProvider` — POST to `http://localhost:11434/api/generate` with base64 image |
| E5 | Create `src/hwcc/vision/anthropic.py` | new | `AnthropicVisionProvider` — uses `anthropic` SDK, base64 image content block |
| E6 | Register all 3 in factory | `vision/__init__.py` | `"claude_cli"`, `"ollama"`, `"anthropic"` → respective providers |
| E7 | Hardware-context prompt (shared) | `vision/base.py` | Class constant: "Describe this hardware diagram for an embedded engineer. Focus on: signal names, timing parameters, register addresses, pin numbers, and bus topology." |
| E8 | Write provider tests | `tests/test_vision_providers.py` | ClaudeCliVisionProvider: mock subprocess; OllamaVisionProvider: mock httpx; AnthropicVisionProvider: mock anthropic SDK |
| E9 | Add optional deps | `pyproject.toml` | `[ollama-vision]` extra: httpx (already likely present); `[anthropic-vision]` extra: `anthropic>=0.40` |

### Phase F: Packaging + Docs

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| F1 | Add optional extras | `pyproject.toml` | `[docling]` extra: `docling>=2.0`, `[vision]` extra: `transformers>=4.40`, `torch`, `Pillow` |
| F2 | Update `TECH_SPEC.md` | `TECH_SPEC.md` | Document vision module, new content types, Docling parser |
| F3 | Update `PLAN.md` | `PLAN.md` | Add PDF multimodal as Future feature, mark plan created |

---

## New Content Types

Add to content type taxonomy (used in `ChunkMetadata.content_type`):

| Value | Meaning | Detection |
|-------|---------|-----------|
| `"figure"` | Generic unclassified figure | Default for any Docling Figure element |
| `"timing_diagram"` | Signal timing waveforms | Keywords: timing, waveform, tsetup, thold, clock |
| `"block_diagram"` | Architecture/peripheral blocks | Keywords: block diagram, architecture, peripheral |
| `"pinout"` | Pin assignment diagram | Keywords: pin, pinout, package, qfp, lqfp, bga |
| `"schematic_figure"` | Circuit/schematic | Keywords: schematic, circuit, transistor |

These extend the existing 12 content types without breaking existing ones.

---

## Test Plan

### Unit Tests

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `IngestConfig` loads from TOML with `pdf_backend = "docling"` | `test_config_ingest_vision.py` | unit |
| 2 | `VisionConfig` loads with all fields, defaults to `provider = "none"` | `test_config_ingest_vision.py` | unit |
| 3 | Config round-trip: save and reload preserves `ingest` and `vision` sections | `test_config_ingest_vision.py` | unit |
| 4 | `NullVisionProvider.caption_image()` returns empty string | `test_vision_providers.py` | unit |
| 5 | `NullVisionProvider.is_available()` returns True | `test_vision_providers.py` | unit |
| 6 | `DoclingPdfParser` raises `ParseError` if file not found | `test_ingest_pdf_docling.py` | unit |
| 7 | `DoclingPdfParser` raises informative `ParseError` if docling not installed | `test_ingest_pdf_docling.py` | unit |
| 8 | `DoclingPdfParser` falls back to `PdfParser` when docling not available and fallback=True | `test_ingest_pdf_docling.py` | unit |
| 9 | `DoclingPdfParser` inserts figure placeholder at correct Y-position in markdown | `test_ingest_pdf_docling.py` | unit (mocked docling) |
| 10 | `DoclingPdfParser` classifies timing keywords → `content_type = "timing_diagram"` | `test_ingest_pdf_docling.py` | unit |
| 11 | `DoclingPdfParser` passes nearby caption as context to `VisionProvider.caption_image()` | `test_ingest_pdf_docling.py` | unit (mocked) |
| 12 | `DoclingPdfParser.supported_extensions()` returns `frozenset({".pdf"})` | `test_ingest_pdf_docling.py` | unit |
| 13 | `_classify_figure_type()` correctly classifies all content type keywords | `test_ingest_pdf_docling.py` | unit |
| 14 | `SmolVlmProvider.is_available()` returns False when transformers not installed | `test_vision_providers.py` | unit |
| 15 | `SmolVlmProvider` loads model lazily on first `caption_image()` call | `test_vision_providers.py` | unit (mocked) |
| 16 | CLI selects `DoclingPdfParser` when `config.ingest.pdf_backend == "docling"` | `test_cli_pdf_parser_selection.py` | integration |
| 17 | CLI uses `PdfParser` (default) when `pdf_backend` not set | `test_cli_pdf_parser_selection.py` | integration |

### Acceptance Criteria (Testable)

| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | `hwcc add datasheet.pdf` with default config | Uses existing PdfParser, no behavior change | automated |
| 2 | `hwcc add datasheet.pdf` with `pdf_backend = "docling"` (docling installed) | ParseResult contains `<!-- FIGURE: page N -->` placeholders | automated |
| 3 | `hwcc add datasheet.pdf` with `pdf_backend = "docling"` (docling NOT installed) | Warning logged, falls back to PdfParser, command succeeds | automated |
| 4 | `hwcc search "SPI timing"` after ingesting docling-parsed PDF | Returns chunks containing timing diagram metadata | manual |
| 5 | Figure placeholder contains caption text from nearby text in PDF | Placeholder `> *Caption: ...*` matches original PDF caption | manual |
| 6 | `hwcc add` with `pdf_backend = "docling"` + `vision.provider = "smolvlm"` | Figure placeholders include AI description of diagram content | manual |
| 7 | No docling, no vision, default config | All 1106 existing tests continue to pass | automated |

---

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/config.py` | modify | Add `IngestConfig`, `VisionConfig`, register in `HwccConfig`, update serialize/load |
| `src/hwcc/ingest/__init__.py` | modify | Add `DoclingPdfParser` to `_PARSER_MAP` and `__all__` |
| `src/hwcc/cli.py` | modify | Config-driven PDF parser selection; vision provider factory |
| `pyproject.toml` | modify | Add `[docling]` and `[vision]` optional dependency extras |

## Files to Create
| File | Purpose |
|------|---------|
| `src/hwcc/vision/__init__.py` | Vision module public API, `get_vision_provider()` factory |
| `src/hwcc/vision/base.py` | `BaseVisionProvider` ABC + shared hardware prompt constant |
| `src/hwcc/vision/none.py` | `NullVisionProvider` — no-op default |
| `src/hwcc/vision/claude_cli.py` | `ClaudeCliVisionProvider` — uses existing Claude subscription via subprocess |
| `src/hwcc/vision/ollama.py` | `OllamaVisionProvider` — local Ollama vision models |
| `src/hwcc/vision/anthropic.py` | `AnthropicVisionProvider` — Anthropic API (requires key) |
| `src/hwcc/ingest/pdf_docling.py` | `DoclingPdfParser` — layout detection + figure extraction |
| `tests/test_config_ingest_vision.py` | Config load/save tests for new sections |
| `tests/test_vision_providers.py` | NullVisionProvider + SmolVlmProvider unit tests |
| `tests/test_ingest_pdf_docling.py` | DoclingPdfParser unit tests |
| `tests/test_cli_pdf_parser_selection.py` | CLI routing tests |

---

## Exit Criteria
```
□ All 1106 existing tests continue to pass (no regressions)
□ New tests added: ≥17 across 4 test files
□ `DoclingPdfParser` handles missing docling gracefully (falls back, logs warning)
□ `NullVisionProvider` is the default — no VLM downloaded without user config
□ `config.ingest.pdf_backend = "pymupdf"` is the default — no behavior change for existing users
□ `SmolVlmProvider` loads model lazily — no startup overhead
□ Figure placeholders are valid markdown (render cleanly in GitHub, CLAUDE.md)
□ All changes within declared scope (no scope creep into chunker/embedder/compiler)
□ NON-GOALS remain untouched
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] Manual test: `hwcc add` with a real STM32 datasheet and `pdf_backend = "docling"` → verify figure placeholders in `.rag/context/`
- [ ] No unintended side effects in: chunker, embedder, store, compiler, serve modules

## Document Updates Needed
- [ ] **TECH_SPEC.md:** Add `vision/` module to architecture section, add new content types to taxonomy table
- [ ] **PLAN.md:** Add PDF multimodal as v1.0+ feature, reference this plan

---

> **Last Updated:** 2026-03-03
> **Research:** `/research` — Docling, SmolVLM, TD-Interpreter, Surya, Marker, ColPali

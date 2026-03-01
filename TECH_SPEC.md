# hwcc — Technical Specification

> **Version**: 0.2.0-draft
> **Date**: 2026-03-01
> **Status**: Draft — updated with EmbedGenius + Embedder research findings

---

## 1. What This Is

**hwcc** (Hardware Context Compiler) is a **Context Compiler** for embedded engineering projects.

It transforms raw hardware documentation (datasheets, reference manuals, SVD files, schematics, errata, device trees) into AI-optimized context that any coding tool can consume — Claude Code, Codex, Cursor, Gemini CLI, Ollama, or plain clipboard paste.

### What It Is NOT

- NOT a chatbot or Q&A system
- NOT a standalone IDE (like Embedder)
- NOT a RAG retrieval engine with its own UI
- NOT a replacement for existing coding tools

### Core Value Proposition

```
WITHOUT hwcc:
  Engineer pastes 127-page PDF into Claude → AI hallucinates register addresses

WITH hwcc:
  Engineer runs `rag add datasheet.pdf` → AI gets clean register maps,
  timing specs, errata workarounds → writes correct driver code
```

### Why This Won't Become Obsolete

Even as context windows grow to 1M+ tokens (Claude Opus 4.6, Gemini 2M planned), preprocessing has permanent value:
- Structured data (SVD → register maps) is always more reliable than LLM-parsed PDFs
- Cost: RAG is 1,250x cheaper per query than stuffing full context
- "Lost in middle" / "context rot": accuracy degrades 30%+ at full context window load — confirmed in 2026 benchmarks across all major models
- Clean markdown tables > raw PDF text extraction
- Compaction-proof: Claude and GPT-5.1 now offer "compaction" (context summarization for infinite conversations), but compaction *loses register-level precision*. Pre-compiled SVD context is immune to compaction loss.

---

## 2. Competitive Landscape & Strategic Gaps

### 2.1 Market Positioning

```
                        Hardware-Specific Knowledge
                        Low ◄──────────────────► High
                        │                         │
  Full IDE/Platform  ── │  Cursor / Codex         │  Embedder (YC S25)
                        │  (generic AI IDEs)      │  (closed, enterprise $$$)
                        │                         │
  Preprocessing /    ── │  Skill Seekers          │  ★ HWCC ★
  Context Compiler      │  CTX, RAG-CLI           │  (open source, tool-agnostic)
                        │  (no HW knowledge)      │
  Validation /       ── │                         │  RespCode
  Post-Processing       │                         │  (closed, post-gen fix)
                        │                         │
  Vendor Data        ── │                         │  Microchip MCP
  Server                │                         │  (free, single vendor)
```

### 2.2 Direct Competitors

| Competitor | Type | Differentiator from Us |
|-----------|------|----------------------|
| **Embedder** (YC S25) | Closed IDE, enterprise + free maker tier | v0.2.0 shipped with unlimited maker plan, TUI, LSP integration. Nominated for embedded award 2026. We are open-source and tool-agnostic — they still lock you into their IDE, but the free tier lowers their barrier for hobbyists. |
| **RespCode** | Closed SaaS | They fix wrong code *after* generation. We prevent it *before* by providing correct context. |
| **Skill Seekers** | Open-source preprocessor | General-purpose (React docs, Django). Zero hardware domain knowledge — no SVD, no register maps, no errata. |
| **CTX / RAG-CLI** | Open-source tools | Codebase context only. No PDF parsing, no hardware doc understanding. |
| **Microchip MCP** | Free vendor server | Single vendor, product selection data only. No register-level programming context. |

### 2.3 MUST FOCUS: Strategic Gaps (No Competition)

These are gaps where **no existing tool (open or closed) addresses the need**. They define our development priorities.

| ID | Gap | Why It Matters | Priority |
|----|-----|---------------|----------|
| **G1** | **Open-source hardware context compiler** | Nobody does this. Embedder is closed/enterprise. Skill Seekers is generic. Zero open-source tools parse hardware docs into AI-ready context. | **P0** |
| **G2** | **SVD-first register context** | RespCode proved LLMs get register addresses wrong. They fix *after* generation (validation). We fix *before* (context injection). Pre-generation is fundamentally better — correct on first try. | **P0** |
| **G3** | **Tool-agnostic multi-format output** | Embedder locks you into their IDE. Every other tool is vendor-locked or single-format. Nobody outputs to ALL coding tools simultaneously (CLAUDE.md + .cursorrules + MCP + clipboard). | **P1** |
| **G4** | **Errata cross-referencing** | No tool systematically cross-references errata with register context. Engineers still manually check errata PDFs. Inline errata warnings = prevented hardware bugs. | **P2** |
| **G5** | **Multi-vendor in one project** | Real projects use STM32 + TI power IC + NXP sensor. Microchip MCP only covers Microchip. Nobody aggregates cross-vendor context in a single project. | **P1** |
| **G6** | **Hardware llms.txt standard** | The llms.txt standard exists for web docs. Nobody has defined what hardware-optimized AI context looks like. First mover defines the format. | **P2** |

### 2.4 Complementary Ecosystem (Not Competitors)

Hardware MCP servers are emerging but serve **different use cases** — interaction with hardware, not documentation preprocessing. These are potential integration partners:

| Tool | What It Does | Relationship to Us |
|------|-------------|-------------------|
| `embedded-debugger-mcp` (probe-rs) | Debug ARM/RISC-V via MCP — flash, breakpoints, memory read | Complementary. Our doc context + their debugger = full AI-assisted embedded workflow. |
| `EmbedMCP` | C library to run MCP servers ON embedded devices | Different layer. They expose device APIs; we expose device documentation. |
| `serial-mcp-server` | Serial port comms via MCP for IoT/embedded | Complementary. Hardware interaction, not documentation. |

### 2.5 Validation from Market

- **RespCode benchmarks**: 3 of 4 flagship LLMs produce firmware with wrong register addresses without proper context. Our approach prevents this at the source.
- **Academic research (2026)**: Multiple papers confirm LLMs still hallucinate register addresses and introduce security vulnerabilities in generated firmware (arXiv:2509.09970, arXiv:2601.19106). Post-generation validation is an active research area — our pre-generation context injection is the complementary approach.
- **EmbedGenius (arXiv:2412.09058v2)**: Automated embedded IoT framework achieving 95.7% coding accuracy across 355 tasks. Key findings applicable to hwcc: (1) structured pin assignments prevent the most common embedded errors, (2) relevance-scored retrieval reduces token consumption by 26.2%, (3) usage pattern tables (API call sequences) boost accuracy by +7.1% and completion by +15%, (4) content-type-aware retrieval outperforms generic search. These techniques improve our context quality without requiring code generation capabilities.
- **Microchip MCP server**: Silicon vendor validating the MCP-based approach. Their server covers product selection, not programming context — complementary, not competitive.
- **MCP ecosystem growth**: 425 servers (Aug 2025) → 1,412 (Feb 2026) — 232% growth in 6 months. Gartner projects 75% of API gateway vendors will have MCP features by 2026. Strong tailwind for our MCP server output.
- **HN discussion (Embedder launch)**: Engineers confirm SVD/structured data > PDF parsing for register accuracy. PDF-only approaches are insufficient.
- **SO Developer Survey 2025**: 84% of devs use AI tools, but only 29% trust output accuracy. Hardware context compilation directly addresses the trust gap.
- **llms.txt standard**: 844K+ websites adopted the web variant. No hardware variant exists. Gap G6 is wide open for first-mover definition.

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     HWCC                             │
│                                                              │
│  ┌──────────┐     ┌──────────────┐     ┌──────────────────┐ │
│  │          │     │              │     │                  │ │
│  │  INGEST  │────▶│  .rag/ STORE │────▶│  OUTPUT/SERVE    │ │
│  │          │     │              │     │                  │ │
│  └──────────┘     └──────────────┘     └──────────────────┘ │
│                                                              │
│  4 ways IN:        Single source        6 ways OUT:          │
│  - CLI command     of truth:            - Static files       │
│  - Drop in folder  - manifest.json      - MCP server         │
│  - Git hook        - ChromaDB index     - Slash commands     │
│  - Slash command   - Processed markdown - Clipboard          │
│                    - Pre-compiled ctx   - Pipe mode           │
│                                         - Agent skill         │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 Internal Architecture — ABC Contracts & Pipeline Composition

The pipeline is built on **Ports & Adapters** (hexagonal architecture) with ABC contracts at every stage boundary. This ensures every provider is swappable, testable with mocks, and discoverable via config.

#### Pipeline Data Flow (frozen dataclasses)

```
Path ──▶ BaseParser.parse() ──▶ ParseResult
             ──▶ BaseChunker.chunk() ──▶ list[Chunk]
             ──▶ BaseEmbedder.embed_chunks() ──▶ list[EmbeddedChunk]
             ──▶ BaseStore.add() ──▶ persisted
             ──▶ BaseCompiler.compile() ──▶ output files
```

Data contracts are **immutable** (`@dataclass(frozen=True)`) to prevent accidental mutation between stages:

| Type | Module | Fields |
|------|--------|--------|
| `ParseResult` | `hwcc.types` | doc_id, content (markdown), doc_type, title, chip, metadata |
| `Chunk` | `hwcc.types` | chunk_id, content, token_count, metadata (ChunkMetadata) |
| `ChunkMetadata` | `hwcc.types` | doc_id, doc_type, chip, section_path, page, peripheral, content_type |
| `EmbeddedChunk` | `hwcc.types` | chunk (Chunk), embedding (tuple of floats) |
| `SearchResult` | `hwcc.types` | chunk (Chunk), score, distance |

#### ABC Interfaces

Each pipeline stage has an abstract base class in `<package>/base.py`:

| ABC | Module | Key Methods |
|-----|--------|-------------|
| `BaseParser` | `hwcc.ingest.base` | `parse(path, config) → ParseResult`, `supported_extensions() → frozenset[str]`, `can_parse(path) → bool` |
| `BaseChunker` | `hwcc.chunk.base` | `chunk(result, config) → list[Chunk]` |
| `BaseEmbedder` | `hwcc.embed.base` | `embed_chunks(chunks) → list[EmbeddedChunk]`, `embed_query(text) → list[float]`, `dimension → int` |
| `BaseStore` | `hwcc.store.base` | `add(chunks, doc_id) → int`, `search(query_embedding, k, where) → list[SearchResult]`, `delete(doc_id) → int`, `get_chunk_metadata(where) → list[ChunkMetadata]`, `get_chunks(where) → list[Chunk]`, `count() → int` |
| `BaseCompiler` | `hwcc.compile.base` | `compile(store, config) → list[Path]` |

#### Provider Registry

Config-driven factory: `[embedding] provider = "ollama"` → `ProviderRegistry.create("embedding", "ollama", config)` → `OllamaEmbedder` instance.

```python
from hwcc.registry import ProviderRegistry

registry = ProviderRegistry()
registry.register("embedding", "ollama", lambda cfg: OllamaEmbedder(cfg))
registry.register("embedding", "openai", lambda cfg: OpenAIEmbedder(cfg))
embedder = registry.create("embedding", config.embedding.provider, config)
```

#### Pipeline Composition

All dependencies injected via constructor — fully testable with mocks:

```python
from hwcc.pipeline import Pipeline

pipeline = Pipeline(
    parser=svd_parser,
    chunker=recursive_chunker,
    embedder=ollama_embedder,
    store=chroma_store,
    config=config,
)
chunk_count = pipeline.process(Path("board.svd"), doc_id="board_svd")
```

#### Exception Hierarchy

```
HwccError (base)
├── ConfigError      — config.toml loading/validation
├── ManifestError    — manifest.json operations
├── ProjectError     — project init/discovery
├── ParseError       — document parsing failures
├── ChunkError       — chunking failures
├── EmbeddingError   — embedding generation failures
├── StoreError       — vector store operations
├── CompileError     — context compilation failures
├── PipelineError    — pipeline orchestration failures
└── PluginError      — plugin loading/registration
```

---

## 4. Data Store Structure

Every project gets a `.rag/` directory:

```
project/
├── .rag/
│   ├── config.toml              # Project configuration
│   ├── manifest.json            # Index of all documents (hashes, metadata)
│   │
│   ├── index/                   # ChromaDB persistent vector store
│   │   └── chroma.sqlite3       # Embeddings + metadata
│   │
│   ├── processed/               # Clean markdown per source document
│   │   ├── ds_stm32f407.md      # Processed datasheet
│   │   ├── rm_rm0090.md         # Processed reference manual
│   │   ├── errata_es0182.md     # Processed errata
│   │   └── sensor_lis3dh.md     # Processed sensor datasheet
│   │
│   └── context/                 # Pre-compiled context (auto-generated)
│       ├── hot.md               # Always-loaded summary (~100 lines)
│       ├── peripherals/         # Per-peripheral context
│       │   ├── spi.md
│       │   ├── i2c.md
│       │   ├── uart.md
│       │   └── gpio.md
│       └── registers/           # Per-peripheral register maps (from SVD)
│           ├── spi_regs.md
│           └── i2c_regs.md
│
├── CLAUDE.md                    # Auto-generated (hot context for Claude Code)
├── AGENTS.md                    # Auto-generated (hot context for Codex)
├── .gemini/GEMINI.md            # Auto-generated (hot context for Gemini CLI)
├── .cursor/rules/hardware.mdc  # Auto-generated (hot context for Cursor)
└── docs/                        # Raw source documents (user manages)
    ├── STM32F407_datasheet.pdf
    └── RM0090_reference_manual.pdf
```

### config.toml

```toml
[project]
name = "motor-controller"
description = "Brushless DC motor controller"

[hardware]
mcu = "STM32F407VGT6"
mcu_family = "STM32F4"
architecture = "Cortex-M4"
clock_mhz = 168
flash_kb = 1024
ram_kb = 192

[software]
rtos = "FreeRTOS 10.5.1"
hal = "STM32 HAL v1.27.1"
language = "C"
build_system = "CMake"

[pins]
spi1_sck = "PA5"
spi1_mosi = "PA7"
spi1_miso = "PA6"
spi1_nss = "PA4"
uart_debug_tx = "PA2"
uart_debug_rx = "PA3"
led_status = "PC13"

[conventions]
register_access = "HAL functions only, no direct register writes"
error_handling = "return HAL_StatusTypeDef"
naming = "snake_case for functions, UPPER_CASE for defines"

[embedding]
model = "nomic-embed-text"          # Default: local via Ollama
provider = "ollama"                  # ollama | openai | huggingface
# provider = "openai"               # Alternative: cloud
# api_key_env = "OPENAI_API_KEY"    # Read from env var

[llm]
# Used only for optional enrichment (schematic captioning, summaries)
provider = "ollama"                  # ollama | openrouter | gemini | openai
model = "llama3.2"                   # Default local model
# provider = "openrouter"
# model = "google/gemini-2.5-flash"
# api_key_env = "OPENROUTER_API_KEY"

[output]
targets = ["claude", "codex", "cursor", "gemini"]  # Which context files to generate
hot_context_max_lines = 120          # Max lines for CLAUDE.md hardware section
```

### manifest.json

```json
{
  "version": "0.1.0",
  "documents": [
    {
      "id": "ds_stm32f407",
      "path": "docs/STM32F407_datasheet.pdf",
      "type": "datasheet",
      "hash": "sha256:a1b2c3...",
      "added": "2026-02-27T10:30:00Z",
      "chunks": 847,
      "metadata": {
        "chip": "STM32F407",
        "doc_type": "datasheet"
      }
    }
  ],
  "last_compiled": "2026-02-27T10:31:00Z"
}
```

---

## 5. Ingestion Pipeline

### 5.1 Document Type Detection

```
Input file → detect type → route to parser

Supported types:
├── .pdf          → PDF parser (PyMuPDF + pdfplumber for tables)
├── .svd          → CMSIS-SVD parser (cmsis-svd library)
├── .dts / .dtsi  → Device tree parser
├── .h / .c       → C code parser (tree-sitter)
├── .rs           → Rust code parser (tree-sitter)
├── .md           → Markdown passthrough (normalize only)
├── .html         → HTML → Markdown converter
├── .txt          → Plain text passthrough
├── .json / .yaml → Structured data passthrough
├── .ioc          → STM32CubeMX project parser (plugin)
└── .png/.jpg     → Image captioning (requires vision LLM, optional)
```

### 5.2 Processing Pipeline

```
Raw Document
    │
    ▼
┌─────────────────────┐
│ 1. Extract          │  Text, tables, images separated
│    (deterministic)  │  Tables → markdown format
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 2. Clean            │  Remove headers/footers/page numbers
│    (deterministic)  │  Normalize whitespace, fix encoding
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 3. Structure        │  Detect sections/chapters
│    (deterministic)  │  Build hierarchy (h1 > h2 > h3)
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 4. Enrich           │  Add section summaries (LLM, optional)
│    (optional LLM)   │  Caption images/diagrams (vision LLM, optional)
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 5. Chunk            │  Recursive 512-token splitting
│    (deterministic)  │  10% overlap, table-boundary aware
│                     │  Hierarchical: summary + detail chunks
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 6. Embed + Index    │  Generate embeddings (nomic-embed-text)
│    (local or cloud) │  Store in ChromaDB with metadata
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 7. Compile Context  │  Generate hot.md (summary)
│    (deterministic)  │  Generate peripheral context files
│                     │  Update CLAUDE.md / AGENTS.md / etc.
└─────────────────────┘
```

**Key design**: Steps 1-3, 5, 7 are fully deterministic — no LLM needed. Step 4 is optional enrichment. Step 6 needs an embedding model (local by default via Ollama).

### 5.3 Chunking Strategy

| Strategy | When Used | Token Size | Overlap |
|----------|-----------|-----------|---------|
| Recursive token split | Default for prose | 512 | 10% (50 tokens) |
| Table-aware split | Tables detected | Full table as one chunk | None |
| Section-boundary split | Chapters/sections | Variable (up to 1024) | None |
| Hierarchical | Large sections | Summary (256) + details (512) | 10% |
| Code-block preserve | Code examples | Full block as one chunk | None |

### 5.4 Metadata Per Chunk

```json
{
  "doc_id": "rm_rm0090",
  "doc_type": "reference_manual",
  "chip": "STM32F407",
  "section_path": "SPI > Configuration > DMA",
  "page": 871,
  "chunk_level": "detail",
  "parent_chunk_id": "rm_rm0090_spi_summary",
  "peripheral": "SPI",
  "content_type": "register_description",
  "tokens": 487
}
```

#### Content Type Taxonomy

Hardware-domain-aware classification applied during chunking. Enables targeted retrieval and richer peripheral context organization.

| Content Type | Detection Method | Example Content |
|-------------|-----------------|----------------|
| `code` | Fenced code block (``` or ~~~) | Code examples, HAL usage snippets |
| `register_table` | Table + register keywords (offset, bit, reset value) | Register map tables from datasheets |
| `register_description` | Prose + register keywords | Text describing register fields and functions |
| `timing_spec` | Timing units (ns, us, MHz, setup/hold time) | Timing specifications, clock requirements |
| `config_procedure` | Init/configuration keywords (step N, enable, procedure) | Initialization sequences, programming guides |
| `errata` | Errata keywords (workaround, limitation, ES####) | Silicon bug descriptions and workarounds |
| `pin_mapping` | GPIO/AF keywords (alternate function, remap) | Pin assignment tables, AF mappings |
| `electrical_spec` | Voltage/current keywords (V, mA, power supply) | Electrical characteristics, power specs |
| `api_reference` | Structured function signatures from C/H headers | HAL/driver API tables (Phase 5) |
| `table` | Markdown table without domain-specific keywords | Generic tables |
| `section` | Markdown heading without other indicators | Section headers |
| `prose` | Default fallback | General descriptive text |

Detection is priority-ordered: structural types first (code > table subtypes > section), then domain-specific prose types. Inspired by EmbedGenius's content-type-aware retrieval which improved search precision.

### 5.5 SVD Field-Level Reset Values

Per-field reset values are computed deterministically from the parent register's reset value:

```python
field_reset = (register_reset_value >> bit_offset) & ((1 << bit_width) - 1)
```

This eliminates the need for field-level reset values in the SVD file (which are often missing) and provides engineers with exact reset state for each bit field — critical for understanding peripheral state after reset.

---

## 6. Output / Serving Layer

### 6.1 Static Context Files

Auto-generated after every `hwcc add` or `hwcc compile`:

| Output File | Target Tool | Max Size | Content |
|------------|-------------|----------|---------|
| `CLAUDE.md` (hardware section) | Claude Code | ~120 lines | Chip info, pins, errata, conventions, MCP tool hints |
| `AGENTS.md` | Codex CLI | ~120 lines | Same content, Codex format |
| `.gemini/GEMINI.md` | Gemini CLI | ~120 lines | Same content, Gemini format |
| `.cursor/rules/hardware.mdc` | Cursor | ~120 lines | Same content, MDC format |
| `.github/copilot-instructions.md` | GitHub Copilot | ~120 lines | Same content |

**Template-driven**: Each output uses a Jinja2 template. Users can customize templates.

**Non-destructive**: The tool appends/updates a marked section in existing files. It never overwrites user content.

```markdown
<!-- BEGIN HWCC CONTEXT (auto-generated, do not edit) -->
# Hardware Context
- MCU: STM32F407VGT6 (Cortex-M4, 168MHz, 1MB Flash)
...
<!-- END HWCC CONTEXT -->
```

#### Peripheral Context Structure (6 sections)

Each `.rag/context/peripherals/<name>.md` file contains up to 6 sections, ordered for maximum AI utility:

```
# SPI1 — STM32F407

## Pin Assignments              ← from [pins] config (optional)
## Register Map                 ← from SVD with per-field reset values
## Usage Patterns               ← initialization/config procedures from ref manual
## API Reference                ← structured function tables from C/H headers (Phase 5)
## Known Errata                 ← cross-referenced from errata docs
## Additional Details           ← relevance-scored chunks with source citations
```

> **Design note**: Hardware relationship metadata (bus, clock, DMA, IRQ) is intentionally NOT in core. Bus inference from SVD base addresses is vendor-specific (STM32 memory map ≠ ESP32 ≠ TI). Wrong bus = wrong clock speed = wrong init code, which is worse than no info. This belongs in vendor plugins (e.g., `rag-plugin-stm32`).

Every section includes **source provenance** — inline citations to the exact document, section, and page:

```markdown
*Source: RM0090 §28.3.3 "Configuration of SPI", p.868*
```

Source citations are the primary trust mechanism. The metadata (`doc_id`, `section_path`, `page`) is already stored per chunk; the compile stage renders it alongside content. This allows engineers to verify any claim against the original documentation.

#### Hot Context Structure

The always-loaded `hot.md` summary (~120 lines) includes:

```
# Hardware Context — {project_name}

## Target Hardware              ← MCU specs from [hardware] config
## Pin Assignments              ← from [pins] config (board-level wiring)
## Software Stack               ← from [software] config
## Peripherals                  ← list with register count + errata count per peripheral
## Errata Highlights            ← top-priority silicon bugs
## Coding Conventions           ← from [conventions] config (preset or custom)
## Indexed Documents            ← document inventory with types
```

### 6.2 MCP Server

Exposed tools:

| Tool | Purpose | Example Call |
|------|---------|-------------|
| `hw_search(query, peripheral?, chip?)` | Free-text search across all docs | `hw_search("SPI DMA configuration")` |
| `hw_registers(peripheral, register?)` | Get register maps from SVD/docs | `hw_registers("SPI1")` |
| `hw_errata(chip?, peripheral?)` | Get known silicon errata | `hw_errata(peripheral="SPI")` |
| `hw_pinout(chip?, pin?, function?)` | Get pin alternate functions | `hw_pinout(pin="PA5")` |
| `hw_context(peripheral)` | Get full pre-compiled context | `hw_context("SPI")` |
| `hw_doc(doc_id, section?)` | Get specific document section | `hw_doc("rm_rm0090", "§28.3.4")` |

Transport: stdio (local, default) or HTTP (for remote/team setups).

#### Query Decomposition

Complex queries spanning multiple peripherals (e.g., "Record DHT11 temperature to SD card via SPI") are automatically decomposed into per-peripheral sub-queries using keyword extraction against known peripheral names from the store. No LLM needed — simple regex matching of peripheral names + operation keywords (init, read, write, configure, interrupt, DMA). Sub-query results are merged with deduplication by chunk_id, keeping the highest-scoring instance. Inspired by EmbedGenius's task decomposition which improved retrieval relevance for multi-component tasks.

### 6.3 Slash Commands

Installed to `.claude/commands/`:

```
/hw <peripheral>        → Load peripheral context
/hw-search <query>      → Search all indexed docs
/hw-errata [peripheral] → Show relevant errata
/hw-pin <pin>           → Show pin alternate functions
/hw-regs <peripheral>   → Show register map
/hw-status              → Show indexed doc count and last update
```

For Codex: installed to `.agents/skills/hw-lookup/SKILL.md`.

### 6.4 Clipboard Mode

```bash
hwcc context SPI --copy              # Copy SPI context to clipboard
hwcc context --query "DMA" --copy    # Search and copy results
hwcc context --all --copy            # Copy full hot context
```

### 6.5 Pipe Mode

```bash
hwcc context SPI | some-llm-cli     # Pipe to any CLI tool
cat prompt.txt | hwcc augment        # Augment stdin with relevant context
hwcc context --format json           # Machine-readable output
```

### 6.6 Agent Skill (Auto-trigger)

```yaml
# .claude/skills/hw-context/SKILL.md
---
name: hw-context
description: >
  Auto-loads hardware context when working on peripheral drivers, HAL code,
  or board-specific configuration files.
globs:
  - "src/drivers/**"
  - "src/hal/**"
  - "src/bsp/**"
  - "**/stm32*.[ch]"
  - "**/*_driver.[ch]"
---
When editing files matching these patterns, use the hw_search and
hw_registers MCP tools to retrieve accurate register maps, timing
specifications, and errata workarounds BEFORE writing or modifying
hardware-related code.

Never guess register addresses. Always verify against indexed documentation.
```

---

## 7. CLI Interface

```
hwcc — Context Compiler for Embedded Projects

COMMANDS:
  hwcc init [--chip <mcu>] [--rtos <rtos>]
      Initialize .rag/ in current project. Auto-detects SVD/config files.

  hwcc add <path> [--type <type>] [--chip <chip>] [--watch]
      Add document(s) to the index. Incremental — skips unchanged files.
      --type: datasheet|reference_manual|errata|schematic|app_note|code|auto
      --watch: Watch path for changes and auto-index

  hwcc remove <doc_id|path>
      Remove a document from the index.

  hwcc status
      Show indexed documents, chunk count, last compile time.

  hwcc compile [--target <tool>]
      Regenerate all output files (CLAUDE.md, AGENTS.md, etc.)
      --target: claude|codex|cursor|gemini|all (default: all)

  hwcc context <peripheral|query> [--copy] [--format md|json|text]
      Retrieve context for a peripheral or free-text query.
      --copy: Copy to clipboard

  hwcc mcp [--port <port>]
      Start MCP server (stdio by default, HTTP with --port).

  hwcc search <query>
      Search indexed documents. Returns ranked chunks with sources.

  hwcc catalog [list|add] [--family <family>] [<chip>]
      Browse and add MCUs from built-in cmsis-svd catalog (300+ MCUs).
      hwcc catalog list                  # List available families
      hwcc catalog list --family STM32   # List STM32 chips
      hwcc catalog add STM32F407         # Add SVD from catalog (zero-config)

  hwcc config [key] [value]
      Get/set configuration values.

  hwcc install-hooks
      Install git hooks for auto-indexing and slash commands.

  hwcc version
      Show version information.
```

---

## 8. Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Language** | Python 3.11+ | Ecosystem, community, ease of contribution |
| **Package** | PyPI (`pip install hwcc`) | Standard distribution |
| **CLI framework** | Typer | Modern, type-safe, auto-generated help |
| **Vector DB** | ChromaDB (PersistentClient) | File-based, no server, portable, incremental |
| **Embeddings (default)** | nomic-embed-text via Ollama | Free, local, 768-dim, good quality |
| **Embeddings (cloud)** | OpenAI text-embedding-3-small | Optional, higher quality |
| **PDF extraction** | PyMuPDF + pdfplumber | Best table extraction for datasheets |
| **SVD parsing** | cmsis-svd (PyPI) | Official CMSIS-SVD parser, pre-indexed chips |
| **Code parsing** | tree-sitter | Multi-language AST parsing |
| **Templating** | Jinja2 | Context file generation |
| **MCP SDK** | mcp (PyPI) | Official Anthropic MCP Python SDK |
| **LLM abstraction** | litellm (optional) | 100+ providers for enrichment |
| **Config** | TOML (tomli/tomli-w) | Human-readable, standard |
| **Rich output** | Rich | Beautiful terminal output |

### Dependencies (core — minimal)

```
# Required
chromadb >= 0.5
pymupdf >= 1.24
pdfplumber >= 0.11
typer >= 0.12
rich >= 13.0
jinja2 >= 3.1
tomli >= 2.0
tomli-w >= 1.0

# Optional
mcp >= 1.0              # MCP server
ollama >= 0.3           # Local embeddings + LLM
litellm >= 1.50         # Cloud LLM providers
cmsis-svd >= 0.6        # SVD register parsing
tree-sitter >= 0.22     # Code parsing
pyperclip >= 1.8        # Clipboard support
```

---

## 9. Embedding & LLM Provider System

### Embedding Providers

```
Priority (auto-fallback):
1. Ollama nomic-embed-text     → Free, local, default
2. Ollama mxbai-embed-large    → Free, local, higher quality
3. OpenAI text-embedding-3-small → Cloud, paid
4. HuggingFace sentence-transformers → Local, no Ollama needed
```

### LLM Providers (for optional enrichment only)

```
Priority (configurable):
1. Ollama (llama3.2, qwen2.5)  → Free, local
2. Gemini Free Tier             → Free, 1M context, cloud
3. Groq Free Tier               → Free, fast, cloud
4. OpenRouter Free Models       → Free, 24+ models, cloud
5. OpenRouter Paid              → 500+ models, 5% markup
6. Direct API (Claude/OpenAI)   → For power users
```

**90% of the tool works with zero LLM calls.** LLM is only needed for:
- Image/schematic captioning (vision LLM)
- Section summary enrichment (optional quality boost)
- Free-text query answering via MCP (if engineer asks directly)

---

## 10. Plugin System

### Plugin Interface

```python
from hwcc.plugin import Plugin, DocumentParser, KnowledgeProvider

class MyPlugin(Plugin):
    name = "stm32"
    version = "0.1.0"
    description = "STM32 support: SVD, CubeMX, errata database"

    def parsers(self) -> list[DocumentParser]:
        return [SVDParser(), IOCParser()]

    def knowledge(self) -> list[KnowledgeProvider]:
        return [STM32ErrataDB(), STM32PinoutDB()]
```

### Plugin Discovery

Uses Python entry_points (standard, zero-config):

```toml
# pyproject.toml of a plugin package
[project.entry-points."hwcc.plugins"]
stm32 = "rag_plugin_stm32:STM32Plugin"
```

### Planned Official Plugins

| Plugin | Provides |
|--------|----------|
| `rag-plugin-stm32` | SVD parser, CubeMX .ioc parser, errata DB, pinout DB |
| `rag-plugin-esp32` | ESP-IDF config parser, ESP32 register maps |
| `rag-plugin-nrf` | nRF Connect SDK support, nRF SVD files |
| `rag-plugin-yocto` | BitBake recipe parser, device tree parser |
| `rag-plugin-zephyr` | Zephyr DTS parser, Kconfig parser |
| `rag-plugin-freertos` | FreeRTOS config parser, API reference |

---

## 11. Integration Compatibility

| Feature | Claude Code | Codex CLI | Cursor | Gemini CLI | ChatGPT Web | Ollama | Aider |
|---------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Static context files | CLAUDE.md | AGENTS.md | .mdc | GEMINI.md | — | — | conv. file |
| MCP server | yes | yes | yes | planned | — | — | — |
| Slash commands | /hw | skill | — | — | — | — | — |
| Agent skill (auto) | yes | yes | — | — | — | — | — |
| Clipboard mode | yes | yes | yes | yes | **yes** | **yes** | yes |
| Pipe mode | yes | yes | — | yes | — | **yes** | yes |

**Clipboard + Pipe = universal fallback** that works with ANY tool.

---

## 12. Incremental Indexing

Documents are indexed incrementally using content hashing:

```
hwcc add docs/

For each file in docs/:
  1. Compute SHA-256 hash
  2. Check manifest.json
     - Hash unchanged → skip (already indexed)
     - Hash changed → re-process, update index
     - New file → process, add to index
  3. Update manifest.json
  4. Re-compile context files (only if anything changed)
```

ChromaDB supports incremental insertion natively — new embeddings are added to the existing collection without rebuilding the HNSW index.

Document removal: `hwcc remove <doc_id>` deletes chunks from ChromaDB and removes from manifest.

---

## 13. Security & Privacy

- **100% local by default**: All processing runs on the user's machine
- **No telemetry**: No data collection, no phone-home
- **Cloud is opt-in**: User explicitly configures cloud LLM/embedding providers
- **API keys via env vars**: Never stored in config files
- **Git-friendly**: `.rag/index/` can be gitignored (regenerable from source docs)
- **No file uploads**: The tool never sends documents to any server unless the user explicitly configures a cloud LLM provider for enrichment

---

## 14. License

MIT License — free forever, no restrictions.

---

## 15. Open Questions

- [ ] Should `.rag/` be gitignored or committed? (index is regenerable, but slow)
- [x] ~~How to handle multi-chip projects?~~ → **YES, v1 scope.** Gap G5: real projects use multi-vendor chips. Support `--chip` tag per document. Single `.rag/` store, chip metadata on chunks.
- [ ] Should the MCP server cache results for performance?
- [x] ~~How to handle document versioning?~~ → Add `document_version` and `silicon_revision` fields to manifest `DocumentEntry`. Metadata stored passively (no interactive prompts — preserves scripting/CI compatibility). Enables revision-aware context rendering: "STM32F407 Rev Z (latest)".
- [x] ~~Naming~~ → **hwcc** (Hardware Context Compiler). Short, unix-style (like gcc), self-documenting. PyPI: `pip install hwcc`. CLI: `hwcc`.
- [ ] Should we publish a formal "hardware llms.txt" spec proposal? (Gap G6)

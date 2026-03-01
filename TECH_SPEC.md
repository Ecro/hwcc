# hwcc — Technical Specification

> **Version**: 0.1.0-dev
> **Date**: 2026-03-01
> **Status**: Master blueprint — full vision, implementation detail in `docs/plans/`
> **Strategy**: See `docs/STRATEGY.md` for competitive landscape and market analysis

---

## 1. What This Is

**hwcc** (Hardware Context Compiler) transforms raw hardware documentation (datasheets, reference manuals, SVD files, errata, device trees) into AI-optimized context that any coding tool can consume — Claude Code, Codex, Cursor, Gemini CLI, Ollama, or plain clipboard paste.

### What It Is NOT

- NOT a chatbot or Q&A system
- NOT a standalone IDE
- NOT a RAG retrieval engine with its own UI
- NOT a replacement for existing coding tools

### Core Value

AI coding tools (Claude Code, Codex, Cursor) already read everything in your repo — source code, Yocto recipes, kernel configs, device trees, Makefiles. hwcc provides what ISN'T there: vendor documentation that lives in PDFs and structured data files. Without it, AI hallucinates register addresses, init sequences, and pin assignments. With it, AI writes correct embedded code on the first try.

**Preprocessing has permanent value** even as context windows grow: structured SVD data is always more reliable than LLM-parsed PDFs, RAG is 1,250x cheaper than full-context stuffing, and pre-compiled context is immune to compaction loss.

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                        HWCC                              │
│                                                          │
│  ┌──────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │          │     │              │     │              │ │
│  │  INGEST  │────▶│  .rag/ STORE │────▶│    OUTPUT    │ │
│  │          │     │              │     │              │ │
│  └──────────┘     └──────────────┘     └──────────────┘ │
│                                                          │
│  IN:                Single source       OUT:             │
│  - CLI (hwcc add)   of truth:           - CLAUDE.md      │
│  - SVD catalog      - manifest.json     - AGENTS.md      │
│                     - ChromaDB index    - .cursor rules   │
│                     - context files     - GEMINI.md       │
│                                         - copilot.md      │
│                                         - MCP server      │
│                                         - clipboard/pipe  │
└──────────────────────────────────────────────────────────┘
```

### Pipeline Data Flow

Built on **Ports & Adapters** with ABC contracts at every stage boundary. All dependencies injected via constructor — fully testable with mocks.

```
Path ──▶ BaseParser.parse() ──▶ ParseResult
     ──▶ BaseChunker.chunk() ──▶ list[Chunk]
     ──▶ BaseEmbedder.embed_chunks() ──▶ list[EmbeddedChunk]
     ──▶ BaseStore.add() ──▶ persisted
     ──▶ BaseCompiler.compile() ──▶ output files
```

### ABC Interfaces

| ABC | Module | Key Methods | Status |
|-----|--------|-------------|--------|
| `BaseParser` | `hwcc.ingest.base` | `parse(path, config) → ParseResult` | [DONE] |
| `BaseChunker` | `hwcc.chunk.base` | `chunk(result, config) → list[Chunk]` | [DONE] |
| `BaseEmbedder` | `hwcc.embed.base` | `embed_chunks(chunks) → list[EmbeddedChunk]` | [DONE] |
| `BaseStore` | `hwcc.store.base` | `add(chunks, doc_id) → int`, `search(...)`, `delete(...)` | [DONE] |
| `BaseCompiler` | `hwcc.compile.base` | `compile(store, config) → list[Path]` | [DONE] (classes; CLI wiring pending task 2.9) |

### Data Contracts (frozen dataclasses)

| Type | Key Fields |
|------|------------|
| `ParseResult` | doc_id, content (markdown), doc_type, title, chip, metadata |
| `Chunk` | chunk_id, content, token_count, metadata (ChunkMetadata) |
| `ChunkMetadata` | doc_id, doc_type, chip, section_path, page, peripheral, content_type |
| `EmbeddedChunk` | chunk (Chunk), embedding (tuple of floats) |
| `SearchResult` | chunk (Chunk), score, distance |

### Provider Registry

Config-driven factory: `[embedding] provider = "chromadb"` → `ProviderRegistry.create(...)` → provider instance. New providers are added by implementing the ABC and registering with the registry.

### Exception Hierarchy

```
HwccError (base)
├── ConfigError      ├── ParseError       ├── CompileError
├── ManifestError    ├── ChunkError        ├── PipelineError
├── ProjectError     ├── EmbeddingError    └── PluginError
                     └── StoreError
```

---

## 3. Data Store Structure

All project data lives in `.rag/`:

```
project/
├── .rag/
│   ├── config.toml              # Project configuration
│   ├── manifest.json            # Document index (SHA-256 hashes, metadata)
│   ├── index/                   # ChromaDB persistent vector store
│   ├── processed/               # Clean markdown per source document
│   └── context/                 # Pre-compiled context (auto-generated)
│       ├── hot.md               # Always-loaded summary (~120 lines)
│       ├── peripherals/         # Per-peripheral context files
│       └── registers/           # Per-peripheral register maps (from SVD)
│
├── CLAUDE.md                    # ← hwcc injects hardware section here
├── AGENTS.md                    # ← for Codex
├── .gemini/GEMINI.md            # ← for Gemini CLI
├── .cursor/rules/hardware.mdc   # ← for Cursor
└── docs/                        # Raw source documents (user manages)
```

### config.toml

```toml
[project]
name = "motor-controller"
description = "Brushless DC motor controller"

[hardware]
mcu = "STM32F407VGT6"           # MCU projects
mcu_family = "STM32F4"
architecture = "Cortex-M4"
clock_mhz = 168
# BSP projects use soc/board instead of (or alongside) mcu:
# soc = "i.MX8M Plus"
# soc_family = "i.MX8"
# board = "Custom Board"

[software]
rtos = "FreeRTOS 10.5.1"
hal = "STM32 HAL v1.27.1"
build_system = "CMake"
# BSP: kernel = "linux-6.6", bootloader = "U-Boot 2024.01", distro = "Yocto kirkstone"

# [pins] — v0.2 (task 2.6, not yet parsed by config system)
# spi1_sck = "PA5"
# spi1_mosi = "PA7"
# led_status = "PC13"

[conventions]
register_access = "HAL functions only, no direct register writes"
naming = "snake_case for functions, UPPER_CASE for defines"

[embedding]
provider = "chromadb"              # Default: built-in ONNX (all-MiniLM-L6-v2)
# provider = "ollama"             # Alternative: Ollama nomic-embed-text
# provider = "openai_compat"      # Cloud: any OpenAI-compatible endpoint

[output]
targets = ["claude", "codex", "cursor", "gemini"]
hot_context_max_lines = 120
```

---

## 4. Ingestion Pipeline

### Document Type Detection [DONE]

| Extension | Parser | Status |
|-----------|--------|--------|
| `.svd` | CMSIS-SVD parser (cmsis-svd library) | [DONE] |
| `.pdf` | PDF parser (PyMuPDF + pdfplumber) | [DONE] |
| `.md` | Markdown normalizer | [DONE] |
| `.txt` | Plain text passthrough | [DONE] |
| `.dts` / `.dtsi` | Device tree parser | [DONE] |
| `.h` / `.c` | C code parser (tree-sitter) | [FUTURE] |
| `.ioc` | STM32CubeMX parser | [FUTURE] — vendor plugin |

### Processing Pipeline

```
Raw Document → Extract → Clean → Structure → Chunk → Embed + Index → Compile
               (deterministic)              (deterministic)  (local)  (deterministic)
```

Steps 1-3 and 5 are fully deterministic — no LLM needed. Step 4 (embed) uses a local model by default. Optional LLM enrichment (image captioning, summaries) is not required.

### Chunking Strategy [DONE]

| Strategy | When Used | Token Size |
|----------|-----------|-----------|
| Recursive token split | Default for prose | 512, 10% overlap |
| Table-aware | Tables detected | Full table, no split |
| Section-boundary | Chapters/sections | Variable (up to 1024) |
| Code-block preserve | Code examples | Full block, no split |

### Content Type Taxonomy [DONE]

12 hardware-domain-aware types applied during chunking. Enables targeted retrieval:

`code` · `register_table` · `register_description` · `timing_spec` · `config_procedure` · `errata` · `pin_mapping` · `electrical_spec` · `api_reference` · `table` · `section` · `prose`

BSP extensions: `device_tree_node` · `dt_binding` · `kernel_config` · `boot_config`

### SVD Per-Field Reset Values [DONE]

Per-field reset values computed deterministically: `(register_reset >> bit_offset) & mask`. Eliminates reliance on field-level reset values in SVD files (often missing).

---

## 5. Output & Serving Layer

### 5.1 Static Context Files [DONE]

Auto-generated after `hwcc compile`:

| Output File | Target Tool |
|------------|-------------|
| `CLAUDE.md` (hardware section) | Claude Code |
| `AGENTS.md` | Codex CLI |
| `.gemini/GEMINI.md` | Gemini CLI |
| `.cursor/rules/hardware.mdc` | Cursor |
| `.github/copilot-instructions.md` | GitHub Copilot |

**Template-driven** (Jinja2). User-customizable: copy template to `.rag/templates/` to override. **Non-destructive**: only updates between `<!-- BEGIN/END HWCC CONTEXT -->` markers.

#### Hot Context (~120 lines, always loaded)

Target Hardware · Pin Assignments · Software Stack · Target SoC (BSP) · Linux Stack (BSP) · Device Tree Topology (BSP) · Peripherals · Errata Highlights · Coding Conventions · Indexed Documents

#### Peripheral Context (6 sections per peripheral)

Pin Assignments · Register Map (SVD with per-field reset values) · Usage Patterns · API Reference · Known Errata · Additional Details (with source citations)

Every section includes **source provenance** — inline citations to exact document, section, and page.

### 5.2 MCP Server [PLANNED — v0.3]

Expose hardware context via MCP protocol (stdio transport, official `mcp` Python SDK):

| Tool | Purpose |
|------|---------|
| `hw_search(query, peripheral?, chip?)` | Free-text search across all indexed docs |
| `hw_registers(peripheral, register?)` | Get register maps from SVD/docs |
| `hw_context(peripheral)` | Get full pre-compiled peripheral context |

Resources: `hw://peripherals`, `hw://documents`

→ Detailed design: `docs/plans/PLAN_MCP_SERVER.md` (to be created)

### 5.3 CLI Search [PLANNED — v0.2]

`hwcc search <query>` — hybrid vector + keyword search with ranked results.

### 5.4 Clipboard & Pipe [FUTURE]

`hwcc context SPI --copy` (clipboard) · `hwcc context SPI | tool` (pipe) · `hwcc context --format json` (machine-readable)

→ See `docs/FUTURE.md`

### 5.5 Agent Skills & Slash Commands [FUTURE]

Auto-generated slash commands for Claude Code and agent skills for Codex.

→ See `docs/FUTURE.md`

---

## 6. CLI Interface

```
hwcc — Hardware Context Compiler

COMMANDS:
  hwcc init [--chip <mcu>] [--soc <soc>]          Initialize project     [DONE]
  hwcc add <path> [--type <type>] [--chip <chip>]  Add documents          [DONE]
  hwcc remove <doc_id|path>                        Remove document        [DONE]
  hwcc status                                      Show project status    [DONE]
  hwcc compile [--target <tool>]                   Generate context files [ACTIVE]
  hwcc search <query> [--top-k N]                  Search indexed docs    [PLANNED]
  hwcc context <peripheral|query> [--copy]         Retrieve context       [PLANNED]
  hwcc catalog [list|add] [--family <fam>] [chip]  Browse SVD catalog     [PLANNED]
  hwcc mcp [--port <port>]                         Start MCP server       [PLANNED]
  hwcc config [key] [value]                        Get/set config         [PLANNED]
  hwcc version                                     Show version           [DONE]
```

---

## 7. Technology Stack

| Component | Choice | Status |
|-----------|--------|--------|
| **Language** | Python 3.11+ | [DONE] |
| **CLI** | Typer + Rich | [DONE] |
| **Vector DB** | ChromaDB (PersistentClient, file-based) | [DONE] |
| **Embeddings** | ChromaDB built-in ONNX (all-MiniLM-L6-v2) | [DONE] default |
| **Embeddings** | Ollama (nomic-embed-text) | [DONE] alternative |
| **Embeddings** | OpenAI-compatible endpoint | [DONE] cloud option |
| **PDF** | PyMuPDF + pdfplumber | [DONE] |
| **SVD** | cmsis-svd (PyPI) | [DONE] |
| **Templating** | Jinja2 | [DONE] |
| **Config** | TOML (tomli/tomli-w) | [DONE] |
| **MCP SDK** | mcp (PyPI) | [PLANNED] |

### Core Dependencies

```
chromadb >= 0.5        pymupdf >= 1.24       pdfplumber >= 0.11
typer >= 0.12          rich >= 13.0          jinja2 >= 3.1
cmsis-svd >= 0.6       tiktoken >= 0.7       tomli-w >= 1.0
```

---

## 8. Provider System

### Embedding Providers [DONE]

| Provider | Model | Type |
|----------|-------|------|
| `chromadb` (default) | all-MiniLM-L6-v2 | Built-in ONNX, zero-config |
| `ollama` | nomic-embed-text | Local, requires Ollama |
| `openai_compat` | configurable | Cloud, any OpenAI-compatible API |

### LLM Providers (optional enrichment only)

LLM is only needed for image captioning and section summaries. **90% of hwcc works with zero LLM calls.** Core parsing, chunking, embedding, and compilation are deterministic or use local embedding models.

| Provider | Type |
|----------|------|
| Ollama (default) | Local, free |
| Any OpenAI-compatible endpoint | Cloud, configurable |

---

## 9. Extension Points [FUTURE]

hwcc is designed for extensibility via its ABC contracts and provider registry. Future plugin system will allow:

- **Document parsers**: new file formats (e.g., CubeMX .ioc, Kconfig)
- **Knowledge providers**: vendor-specific databases (errata, pinout, clock tree)
- **Discovery**: Python entry_points (`hwcc.plugins` group)

Current built-in providers (5 parsers, 3 embedders, 1 store) are registered via `ProviderRegistry` and `_PARSER_MAP`. This pattern scales without a formal plugin framework.

→ See `docs/FUTURE.md` for planned vendor plugins

---

## 10. Incremental Indexing [DONE]

Documents are indexed incrementally using SHA-256 content hashing:

1. Compute hash → check manifest → skip if unchanged
2. Changed/new files: process → chunk → embed → store
3. Update manifest → re-compile context (only if anything changed)

ChromaDB supports incremental insertion natively. Removal: `hwcc remove <doc_id>` deletes chunks and manifest entry.

---

## 11. Security & Privacy

- **100% local by default**: all processing on user's machine
- **No telemetry**: no data collection, no phone-home
- **Cloud is opt-in**: user explicitly configures cloud providers
- **API keys via env vars**: never stored in config files
- **Git-friendly**: `.rag/index/` can be gitignored (regenerable)

---

## 12. Open Questions

- [ ] Should `.rag/` be gitignored or committed? (index is regenerable, but slow)
- [ ] Should MCP server cache results?

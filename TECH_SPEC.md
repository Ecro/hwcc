# Embedded RAG — Technical Specification

> **Version**: 0.1.0-draft
> **Date**: 2026-02-27
> **Status**: Draft — pending review

---

## 1. What This Is

**Embedded RAG** is a **Context Compiler** for embedded engineering projects.

It transforms raw hardware documentation (datasheets, reference manuals, SVD files, schematics, errata, device trees) into AI-optimized context that any coding tool can consume — Claude Code, Codex, Cursor, Gemini CLI, Ollama, or plain clipboard paste.

### What It Is NOT

- NOT a chatbot or Q&A system
- NOT a standalone IDE (like Embedder)
- NOT a RAG retrieval engine with its own UI
- NOT a replacement for existing coding tools

### Core Value Proposition

```
WITHOUT embedded-rag:
  Engineer pastes 127-page PDF into Claude → AI hallucinates register addresses

WITH embedded-rag:
  Engineer runs `rag add datasheet.pdf` → AI gets clean register maps,
  timing specs, errata workarounds → writes correct driver code
```

### Why This Won't Become Obsolete

Even as context windows grow to 1M+ tokens, preprocessing has permanent value:
- Structured data (SVD → register maps) is always more reliable than LLM-parsed PDFs
- Cost: RAG is 1,250x cheaper per query than stuffing full context
- "Lost in middle" problem: accuracy degrades 30%+ at full context window load
- Clean markdown tables > raw PDF text extraction

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     EMBEDDED RAG                             │
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

---

## 3. Data Store Structure

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

## 4. Ingestion Pipeline

### 4.1 Document Type Detection

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

### 4.2 Processing Pipeline

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

### 4.3 Chunking Strategy

| Strategy | When Used | Token Size | Overlap |
|----------|-----------|-----------|---------|
| Recursive token split | Default for prose | 512 | 10% (50 tokens) |
| Table-aware split | Tables detected | Full table as one chunk | None |
| Section-boundary split | Chapters/sections | Variable (up to 1024) | None |
| Hierarchical | Large sections | Summary (256) + details (512) | 10% |
| Code-block preserve | Code examples | Full block as one chunk | None |

### 4.4 Metadata Per Chunk

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

---

## 5. Output / Serving Layer

### 5.1 Static Context Files

Auto-generated after every `rag add` or `rag compile`:

| Output File | Target Tool | Max Size | Content |
|------------|-------------|----------|---------|
| `CLAUDE.md` (hardware section) | Claude Code | ~120 lines | Chip info, errata, conventions, MCP tool hints |
| `AGENTS.md` | Codex CLI | ~120 lines | Same content, Codex format |
| `.gemini/GEMINI.md` | Gemini CLI | ~120 lines | Same content, Gemini format |
| `.cursor/rules/hardware.mdc` | Cursor | ~120 lines | Same content, MDC format |
| `.github/copilot-instructions.md` | GitHub Copilot | ~120 lines | Same content |

**Template-driven**: Each output uses a Jinja2 template. Users can customize templates.

**Non-destructive**: The tool appends/updates a marked section in existing files. It never overwrites user content.

```markdown
<!-- BEGIN EMBEDDED-RAG CONTEXT (auto-generated, do not edit) -->
# Hardware Context
- MCU: STM32F407VGT6 (Cortex-M4, 168MHz, 1MB Flash)
...
<!-- END EMBEDDED-RAG CONTEXT -->
```

### 5.2 MCP Server

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

### 5.3 Slash Commands

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

### 5.4 Clipboard Mode

```bash
rag context SPI --copy              # Copy SPI context to clipboard
rag context --query "DMA" --copy    # Search and copy results
rag context --all --copy            # Copy full hot context
```

### 5.5 Pipe Mode

```bash
rag context SPI | some-llm-cli     # Pipe to any CLI tool
cat prompt.txt | rag augment        # Augment stdin with relevant context
rag context --format json           # Machine-readable output
```

### 5.6 Agent Skill (Auto-trigger)

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

## 6. CLI Interface

```
embedded-rag (rag) — Context Compiler for Embedded Projects

COMMANDS:
  rag init [--chip <mcu>] [--rtos <rtos>]
      Initialize .rag/ in current project. Auto-detects SVD/config files.

  rag add <path> [--type <type>] [--chip <chip>] [--watch]
      Add document(s) to the index. Incremental — skips unchanged files.
      --type: datasheet|reference_manual|errata|schematic|app_note|code|auto
      --watch: Watch path for changes and auto-index

  rag remove <doc_id|path>
      Remove a document from the index.

  rag status
      Show indexed documents, chunk count, last compile time.

  rag compile [--target <tool>]
      Regenerate all output files (CLAUDE.md, AGENTS.md, etc.)
      --target: claude|codex|cursor|gemini|all (default: all)

  rag context <peripheral|query> [--copy] [--format md|json|text]
      Retrieve context for a peripheral or free-text query.
      --copy: Copy to clipboard

  rag mcp [--port <port>]
      Start MCP server (stdio by default, HTTP with --port).

  rag search <query>
      Search indexed documents. Returns ranked chunks with sources.

  rag config [key] [value]
      Get/set configuration values.

  rag install-hooks
      Install git hooks for auto-indexing and slash commands.

  rag version
      Show version information.
```

---

## 7. Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Language** | Python 3.11+ | Ecosystem, community, ease of contribution |
| **Package** | PyPI (`pip install embedded-rag`) | Standard distribution |
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

## 8. Embedding & LLM Provider System

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

## 9. Plugin System

### Plugin Interface

```python
from embedded_rag.plugin import Plugin, DocumentParser, KnowledgeProvider

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
[project.entry-points."embedded_rag.plugins"]
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

## 10. Integration Compatibility

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

## 11. Incremental Indexing

Documents are indexed incrementally using content hashing:

```
rag add docs/

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

Document removal: `rag remove <doc_id>` deletes chunks from ChromaDB and removes from manifest.

---

## 12. Security & Privacy

- **100% local by default**: All processing runs on the user's machine
- **No telemetry**: No data collection, no phone-home
- **Cloud is opt-in**: User explicitly configures cloud LLM/embedding providers
- **API keys via env vars**: Never stored in config files
- **Git-friendly**: `.rag/index/` can be gitignored (regenerable from source docs)
- **No file uploads**: The tool never sends documents to any server unless the user explicitly configures a cloud LLM provider for enrichment

---

## 13. License

MIT License — free forever, no restrictions.

---

## 14. Open Questions

- [ ] Should `.rag/` be gitignored or committed? (index is regenerable, but slow)
- [ ] How to handle multi-chip projects? (e.g., MCU + wireless SoC)
- [ ] Should the MCP server cache results for performance?
- [ ] How to handle document versioning? (new datasheet revision replaces old)
- [ ] Naming: `embedded-rag` vs `hwcontext` vs `embedded-context` vs other?

# Embedded RAG — Implementation Plan

> **Version**: 0.1.0-draft
> **Date**: 2026-02-27
> **Status**: Draft — pending review

---

## Phased Approach

```
Phase 0 (Foundation)     → Project setup, core data structures
Phase 1 (Ingest)         → Add documents, process, chunk, store
Phase 2 (Compile)        → Generate static context files
Phase 3 (Serve)          → MCP server + slash commands
Phase 4 (Integrate)      → Clipboard, pipe, agent skill
Phase 5 (Polish)         → Plugin system, tests, docs, PyPI release
```

---

## Phase 0: Foundation

**Goal**: Project skeleton, config system, data structures.

### Tasks

- [ ] **0.1** Initialize Python project with pyproject.toml
  - Package name: `embedded-rag`
  - CLI entry point: `rag`
  - Python 3.11+ required
  - Use `src/` layout: `src/embedded_rag/`

- [ ] **0.2** Create config system (`config.toml` parser)
  - Define `RagConfig` dataclass
  - Load/save `.rag/config.toml`
  - Support `[project]`, `[hardware]`, `[software]`, `[conventions]`, `[embedding]`, `[llm]`, `[output]` sections
  - Defaults for all values

- [ ] **0.3** Create manifest system (`manifest.json`)
  - Define `Manifest` dataclass with document entries
  - SHA-256 content hashing for change detection
  - Load/save `.rag/manifest.json`
  - Methods: `add_document()`, `remove_document()`, `is_changed()`, `get_document()`

- [ ] **0.4** Create CLI skeleton with Typer
  - `rag init`
  - `rag add`
  - `rag status`
  - `rag compile`
  - `rag context`
  - `rag search`
  - `rag mcp`
  - `rag config`
  - `rag version`
  - Rich output formatting

- [ ] **0.5** Implement `rag init`
  - Create `.rag/` directory structure
  - Auto-detect SVD files in project
  - Auto-detect existing CLAUDE.md / AGENTS.md (non-destructive)
  - Generate default `config.toml` with detected values
  - Print summary of what was created

### Deliverable
```bash
cd my-project
rag init --chip STM32F407
rag status
# → Shows empty project with config
```

---

## Phase 1: Document Ingestion

**Goal**: Add documents, process them into clean markdown, chunk, embed, store.

### Tasks

- [ ] **1.1** File type detection
  - Detect by extension + magic bytes
  - Map to parser: PDF, markdown, text, SVD, DTS, C/H headers
  - Auto-classify document type (datasheet, reference manual, errata, etc.)

- [ ] **1.2** PDF parser
  - Extract text with PyMuPDF (fitz)
  - Extract tables with pdfplumber → markdown table format
  - Preserve section headings hierarchy
  - Remove headers/footers/page numbers
  - Output: clean markdown with metadata

- [ ] **1.3** SVD parser
  - Parse CMSIS-SVD files using `cmsis-svd` library
  - Extract: peripherals, registers, fields, descriptions, reset values
  - Output: structured register map in markdown
  - This is DETERMINISTIC — no LLM needed, highest reliability

- [ ] **1.4** Markdown / text passthrough
  - Normalize whitespace and encoding
  - Detect and preserve code blocks
  - Extract front-matter metadata if present

- [ ] **1.5** Chunking engine
  - Recursive token splitter (tiktoken for counting)
  - Default: 512 tokens, 10% overlap
  - Table-aware: never split mid-table
  - Code-block-aware: never split mid-code-block
  - Section-boundary-aware: prefer splitting at headings
  - Metadata per chunk: doc_id, section_path, page, chunk_level, peripheral

- [ ] **1.6** Embedding engine
  - Abstract `EmbeddingProvider` interface
  - Ollama provider (default): `nomic-embed-text`
  - OpenAI-compatible provider: any OpenAI-compatible endpoint
  - Batch embedding for efficiency
  - Error handling: graceful fallback if Ollama not running

- [ ] **1.7** ChromaDB storage
  - Use `PersistentClient` (file-based, no server)
  - Collection per project
  - Store: embedding, chunk text, metadata
  - Incremental: add new chunks without rebuilding
  - Delete: remove chunks by doc_id

- [ ] **1.8** Implement `rag add`
  - Accept file path(s) or directory
  - Check manifest for existing/changed files
  - Process → chunk → embed → store pipeline
  - Update manifest
  - Print progress with Rich
  - Support `--type` and `--chip` hints
  - Support `--watch` for file watching (watchdog library)

- [ ] **1.9** Implement `rag remove`
  - Remove document from ChromaDB by doc_id
  - Remove from manifest
  - Remove processed markdown file

- [ ] **1.10** Implement `rag status`
  - Show: document count, chunk count, total tokens
  - Per-document: name, type, chunks, date added
  - Embedding model info
  - Store size on disk

### Deliverable
```bash
rag add docs/STM32F407_datasheet.pdf
# → Processing... 847 chunks indexed
rag add docs/RM0090_reference_manual.pdf
# → Processing... 2,341 chunks indexed
rag add board.svd
# → Parsed 43 peripherals, 892 registers
rag status
# → 3 documents, 4,080 chunks, 2.1M tokens
```

---

## Phase 2: Context Compilation

**Goal**: Generate output files that AI coding tools consume.

### Tasks

- [ ] **2.1** Hot context generator
  - Compile `.rag/context/hot.md` from all indexed documents
  - Include: chip summary, peripheral list, errata highlights, conventions
  - Respect `hot_context_max_lines` config (default 120)
  - Prioritize: errata > chip specs > peripheral list > conventions

- [ ] **2.2** Peripheral context generator
  - Compile `.rag/context/peripherals/<name>.md` per peripheral
  - Include: register map, clock config, DMA mapping, pin mapping, errata
  - Sources: SVD data + datasheet chunks + ref manual chunks
  - Cross-reference across documents

- [ ] **2.3** Jinja2 template system
  - Template per output target: claude, codex, cursor, gemini, copilot
  - Templates in `src/embedded_rag/templates/`
  - User-customizable: copy template to `.rag/templates/` to override

- [ ] **2.4** Output file generators
  - `CLAUDE.md` generator: inject hardware section with markers
  - `AGENTS.md` generator: Codex-compatible format
  - `.gemini/GEMINI.md` generator
  - `.cursor/rules/hardware.mdc` generator
  - `.github/copilot-instructions.md` generator
  - **Non-destructive**: only update between `<!-- BEGIN/END EMBEDDED-RAG -->` markers
  - Detect and preserve existing user content

- [ ] **2.5** Implement `rag compile`
  - Generate hot context
  - Generate peripheral contexts
  - Generate all target output files
  - Report what was generated/updated
  - `--target` flag to compile for specific tool only

- [ ] **2.6** Auto-compile on `rag add`
  - After adding new documents, auto-run compile
  - Can be disabled with `--no-compile` flag

### Deliverable
```bash
rag compile
# → Generated .rag/context/hot.md (118 lines)
# → Generated .rag/context/peripherals/spi.md
# → Generated .rag/context/peripherals/i2c.md
# → Updated CLAUDE.md (hardware section)
# → Updated AGENTS.md
# → Created .gemini/GEMINI.md
# → Created .cursor/rules/hardware.mdc

# Now Claude Code automatically has hardware context!
```

---

## Phase 3: MCP Server & Slash Commands

**Goal**: Dynamic context serving via MCP and user-triggered commands.

### Tasks

- [ ] **3.1** MCP server implementation
  - Use `mcp` Python SDK (official Anthropic)
  - stdio transport (default)
  - Implement tools:
    - `hw_search(query, peripheral?, chip?)` → vector search
    - `hw_registers(peripheral, register?)` → SVD/register data
    - `hw_errata(chip?, peripheral?)` → errata lookup
    - `hw_pinout(pin?, function?)` → pin mapping
    - `hw_context(peripheral)` → full pre-compiled context
    - `hw_doc(doc_id, section?)` → specific doc section
  - Implement resources:
    - `hw://peripherals` → list of peripherals
    - `hw://documents` → list of indexed documents

- [ ] **3.2** Implement `rag mcp`
  - Start MCP server in foreground (stdio)
  - Optional `--port` for HTTP transport
  - Generate `.claude/mcp.json` config snippet
  - Generate `.cursor/mcp.json` config snippet

- [ ] **3.3** Slash command generation
  - Generate `.claude/commands/hw.md`
  - Generate `.claude/commands/hw-search.md`
  - Generate `.claude/commands/hw-errata.md`
  - Generate `.claude/commands/hw-pin.md`
  - Generate `.claude/commands/hw-regs.md`
  - Generate `.claude/commands/hw-status.md`
  - Generate `.claude/commands/rag-add.md`

- [ ] **3.4** Agent skill generation
  - Generate `.claude/skills/hw-context/SKILL.md`
  - Auto-trigger on driver/HAL file patterns
  - Instruct Claude to use MCP tools before writing hardware code

- [ ] **3.5** Codex skill generation
  - Generate `.agents/skills/hw-lookup/SKILL.md`
  - Compatible with Codex skill discovery

- [ ] **3.6** Implement `rag search`
  - CLI search interface
  - Hybrid search: vector similarity + keyword matching
  - Display results with Rich: source, page, relevance score
  - `--top-k` flag (default 5)

### Deliverable
```bash
# Start MCP server
rag mcp
# → MCP server running (stdio)
# → Configure in .claude/mcp.json:
#   {"mcpServers": {"embedded-rag": {"command": "rag", "args": ["mcp"]}}}

# In Claude Code:
> "Write SPI DMA driver"
# → Claude calls hw_search("SPI DMA") automatically
# → Gets real register maps → writes correct code

# Slash commands:
> /hw SPI
# → Loads full SPI context into conversation
```

---

## Phase 4: Universal Integration

**Goal**: Clipboard, pipe, and automation support for any LLM.

### Tasks

- [ ] **4.1** Implement `rag context` clipboard mode
  - `rag context SPI --copy` → clipboard
  - `rag context --query "DMA channels" --copy`
  - `rag context --all --copy` → full hot context
  - Format: clean markdown optimized for pasting into AI chat
  - Include source citations

- [ ] **4.2** Implement pipe mode
  - `rag context SPI` → stdout (default)
  - `echo "prompt" | rag augment` → augmented prompt to stdout
  - `rag context --format json` → machine-readable output
  - `rag context --format text` → plain text (for simple LLMs)

- [ ] **4.3** `rag augment` command
  - Read prompt from stdin
  - Analyze prompt to detect relevant peripherals/topics
  - Retrieve relevant context
  - Output: augmented prompt with context prepended
  - Use case: `echo "Write SPI driver" | rag augment | ollama run llama3.2`

- [ ] **4.4** Watch mode for live re-indexing
  - `rag add --watch docs/` → background file watcher
  - Use `watchdog` library
  - On file change: re-process, update index, re-compile context
  - Useful during active development

- [ ] **4.5** Git hook installer
  - `rag install-hooks`
  - pre-commit hook: auto-index new/changed docs in `docs/`
  - post-checkout hook: verify index is current

### Deliverable
```bash
# Clipboard (any AI chat)
rag context UART --copy
# → Paste into ChatGPT / Gemini / Claude.ai

# Pipe (scripting)
echo "Fix the I2C timeout issue" | rag augment | ollama run qwen2.5

# Automation
rag add --watch docs/ &   # Background watcher
# Drop new datasheet → auto-indexed → CLAUDE.md auto-updated
```

---

## Phase 5: Polish & Release

**Goal**: Plugin system, testing, documentation, PyPI release.

### Tasks

- [ ] **5.1** Plugin system
  - Plugin base class: `embedded_rag.plugin.Plugin`
  - Entry point discovery: `embedded_rag.plugins` group
  - Plugin registry with version tracking
  - `rag plugins` command to list installed plugins

- [ ] **5.2** STM32 plugin (first official plugin)
  - SVD parser (using cmsis-svd library)
  - CubeMX .ioc file parser
  - STM32 errata database (bundled)
  - STM32 pin alternate function database

- [ ] **5.3** Device tree parser
  - Parse .dts / .dtsi files
  - Extract: nodes, compatible strings, properties, reg addresses
  - Output: structured device tree context

- [ ] **5.4** C/H header parser
  - tree-sitter based
  - Extract: function signatures, struct definitions, enums, macros
  - Understand HAL patterns (function groups per peripheral)

- [ ] **5.5** Test suite
  - Unit tests for each parser
  - Unit tests for chunking engine
  - Integration tests for full pipeline (add → compile → serve)
  - Test with real datasheets (STM32F407, ESP32, nRF52840)
  - Test MCP server tool responses

- [ ] **5.6** Documentation
  - README.md with quickstart
  - docs/getting-started.md
  - docs/configuration.md
  - docs/integration-guides/ (per coding tool)
  - docs/plugin-development.md
  - docs/contributing.md

- [ ] **5.7** PyPI release
  - Build and publish to PyPI
  - `pip install embedded-rag`
  - Verify clean install on fresh Python env
  - CLI entry point works: `rag --help`

- [ ] **5.8** GitHub repository setup
  - MIT license
  - CI/CD with GitHub Actions (lint, test, publish)
  - Issue templates
  - Contributing guide
  - Example projects in `examples/`

### Deliverable
```bash
pip install embedded-rag
pip install rag-plugin-stm32  # Optional STM32 support

cd my-project
rag init --chip STM32F407
rag add docs/
rag status
# → Ready to use with Claude Code / Codex / Cursor / any AI
```

---

## Milestone Summary

| Milestone | Phases | Key Deliverable | Est. Scope |
|-----------|--------|-----------------|------------|
| **M0: Skeleton** | Phase 0 | `rag init`, `rag status` work | Small |
| **M1: Core Pipeline** | Phase 1 | `rag add` processes PDFs and SVDs | Medium |
| **M2: Context Output** | Phase 2 | Auto-generates CLAUDE.md et al. | Medium |
| **M3: MCP + Commands** | Phase 3 | MCP server + /hw slash commands | Medium |
| **M4: Universal** | Phase 4 | Clipboard, pipe, augment, watch | Small |
| **M5: Release** | Phase 5 | PyPI package, plugin system, docs | Medium |

---

## Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| PDF table extraction quality varies | Wrong register data | Use pdfplumber + fallback to PyMuPDF; validate against SVD |
| Ollama not installed on user machine | Can't embed | Graceful error + instructions; support HuggingFace local fallback |
| MCP protocol changes | Server breaks | Pin mcp SDK version; follow Anthropic changelog |
| ChromaDB performance with large docs | Slow queries | Limit collection size; metadata filtering; benchmark |
| Context file overwrites user content | Data loss | Use marker comments; never touch content outside markers |
| Too many output files clutter project | Annoyance | Only generate for configured targets; `.gitignore` guidance |

---

## Out of Scope (v1)

- Web UI / TUI (future consideration)
- Team collaboration / sync
- Subscription / payment system
- Plugin marketplace
- Image/schematic captioning (requires vision LLM — defer to v2)
- Multi-chip project support (defer to v2)
- Fine-tuned embedding models
- Knowledge graph / GraphRAG

---

## File Structure (Implementation)

```
embedded-rag/
├── pyproject.toml
├── LICENSE                          # MIT
├── README.md
├── TECH_SPEC.md
├── PLAN.md
│
├── src/embedded_rag/
│   ├── __init__.py                  # Version, package metadata
│   ├── cli.py                       # Typer CLI (all commands)
│   ├── config.py                    # Config dataclass + TOML loader
│   ├── manifest.py                  # Manifest dataclass + JSON loader
│   ├── project.py                   # Project manager (init, status)
│   │
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── detect.py                # File type detection
│   │   ├── pdf.py                   # PDF → markdown
│   │   ├── svd.py                   # SVD → register maps
│   │   ├── markdown.py              # Markdown normalization
│   │   ├── text.py                  # Plain text handler
│   │   └── pipeline.py              # Orchestrates ingest flow
│   │
│   ├── chunk/
│   │   ├── __init__.py
│   │   ├── splitter.py              # Recursive token splitter
│   │   └── metadata.py              # Chunk metadata enrichment
│   │
│   ├── embed/
│   │   ├── __init__.py
│   │   ├── base.py                  # Abstract embedding provider
│   │   ├── ollama.py                # Ollama embeddings
│   │   └── openai_compat.py         # OpenAI-compatible API
│   │
│   ├── store/
│   │   ├── __init__.py
│   │   └── chroma.py                # ChromaDB wrapper
│   │
│   ├── compile/
│   │   ├── __init__.py
│   │   ├── hot.py                   # Hot context generator
│   │   ├── peripheral.py            # Peripheral context generator
│   │   └── output.py                # Target file generators
│   │
│   ├── serve/
│   │   ├── __init__.py
│   │   ├── mcp_server.py            # MCP server implementation
│   │   ├── search.py                # Search engine (hybrid)
│   │   └── commands.py              # Slash command generator
│   │
│   └── templates/                   # Jinja2 templates
│       ├── claude.md.j2
│       ├── agents.md.j2
│       ├── gemini.md.j2
│       ├── cursor.mdc.j2
│       ├── copilot.md.j2
│       ├── hot_context.md.j2
│       └── peripheral.md.j2
│
├── tests/
│   ├── test_config.py
│   ├── test_manifest.py
│   ├── test_ingest_pdf.py
│   ├── test_ingest_svd.py
│   ├── test_chunking.py
│   ├── test_embedding.py
│   ├── test_store.py
│   ├── test_compile.py
│   ├── test_mcp_server.py
│   └── fixtures/
│       ├── sample_datasheet.pdf
│       ├── sample.svd
│       └── sample_config.toml
│
├── examples/
│   ├── stm32f407-blinky/            # Minimal example
│   └── stm32f407-motor-ctrl/        # Full example with multiple docs
│
└── plugins/
    └── rag-plugin-stm32/            # First official plugin
        ├── pyproject.toml
        └── src/rag_plugin_stm32/
            ├── __init__.py
            ├── plugin.py
            ├── svd.py
            ├── ioc.py
            └── errata_db.py
```

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**hwcc** (Hardware Context Compiler) is a **Context Compiler** — it transforms raw hardware documentation (datasheets, SVD files, reference manuals, errata, device trees) into AI-optimized context files that any coding tool can consume (Claude Code, Codex, Cursor, Gemini CLI, Ollama). It is NOT a chatbot or standalone IDE. It preprocesses docs so AI coding agents write correct embedded code instead of hallucinating register addresses.

## Architecture

**Ports & Adapters** with ABC contracts at every pipeline stage. Each stage has an abstract base class (`base.py`), frozen dataclass data contracts (`types.py`), and a config-driven registry (`registry.py`).

### Pipeline Stages (ABC per stage)

| Stage | ABC | Module | Input → Output |
|-------|-----|--------|---------------|
| **Parse** | `BaseParser` | `src/hwcc/ingest/base.py` | `Path → ParseResult` |
| **Chunk** | `BaseChunker` | `src/hwcc/chunk/base.py` | `ParseResult → list[Chunk]` |
| **Embed** | `BaseEmbedder` | `src/hwcc/embed/base.py` | `list[Chunk] → list[EmbeddedChunk]` |
| **Store** | `BaseStore` | `src/hwcc/store/base.py` | `list[EmbeddedChunk] → persisted` |
| **Compile** | `BaseCompiler` | `src/hwcc/compile/base.py` | `store queries → output files` |
| **Serve** | (Phase 3) | `src/hwcc/serve/` | MCP server, slash commands |

### Key Modules

- **`src/hwcc/types.py`**: Frozen dataclass data contracts (`ParseResult`, `Chunk`, `ChunkMetadata`, `EmbeddedChunk`, `SearchResult`)
- **`src/hwcc/pipeline.py`**: `Pipeline` class — composes parse→chunk→embed→store via constructor injection
- **`src/hwcc/registry.py`**: `ProviderRegistry` — maps config strings (e.g. `"ollama"`) to provider factories
- **`src/hwcc/exceptions.py`**: Full exception hierarchy (`HwccError` → `ParseError`, `ChunkError`, `EmbeddingError`, `StoreError`, `CompileError`, `PipelineError`, `PluginError`)
- **`src/hwcc/config.py`**: Typed dataclass config loaded from `.rag/config.toml`
- **`src/hwcc/manifest.py`**: Document manifest with SHA-256 change detection
- **`src/hwcc/project.py`**: Project init, status, root discovery

### Design Principles

- **ABC over Protocol**: Built-in providers inherit shared logic from base classes; `@abstractmethod` enforces contracts at runtime
- **Constructor injection**: `Pipeline` receives all dependencies via `__init__` — fully testable with mocks, no DI framework
- **Frozen data contracts**: `@dataclass(frozen=True)` prevents accidental mutation between stages
- **Config-driven registry**: `[embedding] provider = "ollama"` → `ProviderRegistry.create("embedding", "ollama", config)` → instance

All project data lives in `.rag/` directory (manifest.json, ChromaDB index, processed markdown, pre-compiled context). This is the single source of truth.

## Technology Stack

Python 3.11+, Typer (CLI), ChromaDB (vectors), PyMuPDF + pdfplumber (PDF), cmsis-svd (SVD parsing), Jinja2 (templates), Rich (terminal output), mcp SDK (MCP server).

## Build & Development Commands

```bash
# Install in development mode (once project is scaffolded)
pip install -e ".[dev]"

# Run CLI
hwcc --help

# Run tests
pytest tests/
pytest tests/test_config.py -v          # Single test file
pytest tests/test_ingest_pdf.py -k "test_table_extraction"  # Single test

# Type checking
mypy src/hwcc/

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

## Key Design Decisions

- **Testable architecture**: Every pipeline stage has an ABC contract. `Pipeline` accepts mock providers via constructor injection. 99 tests verify all contracts.
- **Non-destructive output**: Context injected into CLAUDE.md/AGENTS.md between `<!-- BEGIN/END HWCC -->` markers only. Never touch user content outside markers.
- **Incremental indexing**: SHA-256 content hashing via manifest.json. `hwcc add` skips unchanged files, only re-processes modified/new documents.
- **LLM is optional**: 90% of functionality works without any LLM. Only vision captioning and enrichment summaries need LLM. Core parsing, chunking, embedding, and compilation are deterministic or use local models.
- **Multi-provider**: `ProviderRegistry` maps config strings to factories. Add new embedding/LLM/store backends by implementing the ABC and registering with the registry.
- **Plugin system**: Python entry_points (`hwcc.plugins` group). Plugins provide parsers and knowledge providers. See TECH_SPEC.md §10.
- **Config**: `.rag/config.toml` with sections: `[project]`, `[hardware]`, `[software]`, `[conventions]`, `[embedding]`, `[llm]`, `[output]`.

## Implementation Reference

Detailed technical specification: `TECH_SPEC.md`
Phased implementation plan with task breakdown: `PLAN.md`

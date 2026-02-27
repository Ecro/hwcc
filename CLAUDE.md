# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Embedded RAG is a **Context Compiler** — it transforms raw hardware documentation (datasheets, SVD files, reference manuals, errata, device trees) into AI-optimized context files that any coding tool can consume (Claude Code, Codex, Cursor, Gemini CLI, Ollama). It is NOT a chatbot or standalone IDE. It preprocesses docs so AI coding agents write correct embedded code instead of hallucinating register addresses.

## Architecture

Three-stage pipeline: **Ingest → Store → Output**

- **Ingest** (`src/embedded_rag/ingest/`): Parsers extract clean markdown from raw docs (PDF, SVD, DTS, C headers). `pipeline.py` orchestrates the flow. Steps 1-3 are fully deterministic (no LLM). Step 4 (enrichment) is optional.
- **Chunk** (`src/embedded_rag/chunk/`): Recursive 512-token splitting with 10% overlap. Table-boundary and code-block aware — never split mid-table.
- **Embed** (`src/embedded_rag/embed/`): Abstract provider interface. Default: `nomic-embed-text` via Ollama (local, free). OpenAI-compatible endpoint as alternative.
- **Store** (`src/embedded_rag/store/`): ChromaDB PersistentClient. File-based, no server, incremental insertion.
- **Compile** (`src/embedded_rag/compile/`): Generates hot context (always-loaded summary) and per-peripheral context files. Uses Jinja2 templates from `src/embedded_rag/templates/`.
- **Serve** (`src/embedded_rag/serve/`): MCP server (hw_search, hw_registers, hw_errata tools), slash command generator, search engine.

All project data lives in `.rag/` directory (manifest.json, ChromaDB index, processed markdown, pre-compiled context). This is the single source of truth — all 6 output methods read from it.

## Technology Stack

Python 3.11+, Typer (CLI), ChromaDB (vectors), PyMuPDF + pdfplumber (PDF), cmsis-svd (SVD parsing), Jinja2 (templates), Rich (terminal output), mcp SDK (MCP server).

## Build & Development Commands

```bash
# Install in development mode (once project is scaffolded)
pip install -e ".[dev]"

# Run CLI
rag --help

# Run tests
pytest tests/
pytest tests/test_config.py -v          # Single test file
pytest tests/test_ingest_pdf.py -k "test_table_extraction"  # Single test

# Type checking
mypy src/embedded_rag/

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

## Key Design Decisions

- **Non-destructive output**: Context injected into CLAUDE.md/AGENTS.md between `<!-- BEGIN/END EMBEDDED-RAG -->` markers only. Never touch user content outside markers.
- **Incremental indexing**: SHA-256 content hashing via manifest.json. `rag add` skips unchanged files, only re-processes modified/new documents.
- **LLM is optional**: 90% of functionality works without any LLM. Only vision captioning and enrichment summaries need LLM. Core parsing, chunking, embedding, and compilation are deterministic or use local models.
- **Plugin system**: Python entry_points (`embedded_rag.plugins` group). Plugins provide parsers and knowledge providers. See TECH_SPEC.md §9.
- **Config**: `.rag/config.toml` with sections: `[project]`, `[hardware]`, `[software]`, `[conventions]`, `[embedding]`, `[llm]`, `[output]`.

## Implementation Reference

Detailed technical specification: `TECH_SPEC.md`
Phased implementation plan with task breakdown: `PLAN.md`

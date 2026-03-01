# hwcc — Implementation Roadmap

> **Version**: 0.1.0-dev
> **Date**: 2026-03-01
> **Status**: Phase 2 complete — core loop works end-to-end
> **Tests**: 675 | **Source files**: 36 | **Parsers**: 5 (SVD, PDF, Markdown, Text, DTS)

---

## Milestone Overview

```
v0.1 MVP ──── Core loop works: hwcc add → hwcc compile → CLAUDE.md    [SHIPPED]
v0.2 Quality ─ Citations, pins, relevance scoring, SVD catalog, search [PLANNED]
v0.3 MCP ──── MCP server + dynamic context serving                    [PLANNED]
v1.0 Polish ── Integrations, docs, PyPI release                       [PLANNED]
Future ─────── Plugins, vendor extensions, advanced features           [FUTURE]
```

---

## v0.1 — MVP (Core Loop)

**Goal**: `hwcc init → hwcc add board.svd → hwcc compile → CLAUDE.md` works end-to-end.

### Phase 0: Foundation [DONE]

All complete: project skeleton, config system (TOML), manifest system (SHA-256), CLI skeleton (Typer), `hwcc init`.

→ Detail: `docs/plans/PLAN_PHASE0_FOUNDATION.md`

### Phase 1: Document Ingestion [DONE]

All complete: file type detection, SVD parser (P0 — per-field reset values, access types), PDF parser (PyMuPDF + pdfplumber tables), markdown/text passthrough, device tree parser (25+ SoC families), chunking engine (512-token recursive, table-aware, section-aware), embedding engine (3 providers), ChromaDB storage, `hwcc add` / `hwcc remove` / `hwcc status`, content type taxonomy (12 types), BSP config fields (soc/kernel/bootloader/distro).

→ Detail: `docs/plans/PLAN_SVD_PARSER.md`, `PLAN_PDF_PARSER.md`, `PLAN_CHUNKING_ENGINE.md`, `PLAN_EMBEDDING_ENGINE.md`, `PLAN_CHROMADB_STORAGE.md`, `PLAN_BSP_DOMAIN_SUPPORT.md`, etc.

### Phase 2: Context Compilation [DONE]

| # | Task | Status |
|---|------|--------|
| 2.1 | Hot context compiler (HotContextCompiler) | [DONE] |
| 2.2 | Peripheral context compiler (PeripheralContextCompiler) | [DONE] |
| 2.3 | Jinja2 template system with user overrides | [DONE] |
| 2.4 | Output generators (claude/codex/cursor/gemini/copilot) | [DONE] |
| 2.9 | Wire `hwcc compile` CLI to existing compiler classes | [DONE] |
| 2.10 | Auto-compile after `hwcc add` (with `--no-compile` opt-out) | [DONE] |

→ Detail: `docs/plans/PLAN_HOT_CONTEXT.md`, `PLAN_PERIPHERAL_CONTEXT.md`, `PLAN_OUTPUT_GENERATORS.md`, `PLAN_TEMPLATE_SYSTEM.md`, `PLAN_COMPILE_CLI.md`

### Ship Checklist

- [x] Wire `hwcc compile` CLI (task 2.9)
- [x] Auto-compile on `hwcc add` (task 2.10)
- [x] Fix stale docs (CLAUDE.md, TECH_SPEC defaults)
- [x] README with quickstart
- [x] PyPI publish (`pip install hwcc`)

---

## v0.2 — Quality & Search

**Goal**: Richer context output, CLI search, zero-config SVD experience.

| # | Task | Description |
|---|------|-------------|
| ~~2.5~~ | ~~Source provenance / citations~~ | ~~Inline `*Source: RM0090 §28.3.3, p.868*` per chunk~~ ✅ |
| ~~2.6~~ | ~~Pin assignments in output~~ | ~~Render `[pins]` config in hot + peripheral context~~ ✅ |
| 2.7 | Relevance-scored chunk selection | Keyword-overlap scoring (deterministic, -26.2% tokens) |
| 2.8 | Usage pattern extraction | `content_type == "config_procedure"` → "Usage Patterns" section |
| 1.13 | SVD catalog | `hwcc catalog list/add` — 300+ MCUs from cmsis-svd, zero-config |
| 3.6 | CLI search (`hwcc search`) | Hybrid vector + keyword search with Rich output |

→ Detailed plans created before each `/execute`

---

## v0.3 — MCP Server

**Goal**: Dynamic context serving via MCP protocol.

| # | Task | Description |
|---|------|-------------|
| 3.1 | MCP server implementation | 3 tools: `hw_search`, `hw_registers`, `hw_context`. stdio transport. |
| 3.2 | `hwcc mcp` CLI command | Start server, generate `.claude/mcp.json` config snippet |

→ Detailed plan: `docs/plans/PLAN_MCP_SERVER.md` (to be created)

---

## v1.0 — Integrations & Polish

**Goal**: Full release with documentation, testing, and integrations.

| # | Task | Description |
|---|------|-------------|
| 4.1 | Clipboard mode | `hwcc context SPI --copy` |
| 4.2 | Pipe mode | `hwcc context SPI \| tool`, `--format json/text/md` |
| 5.5 | Test suite hardening | Integration tests, real datasheet tests |
| 5.6 | Documentation | README, getting-started, configuration, integration guides |
| 5.7 | PyPI release | Build, publish, verify clean install |
| 5.8 | GitHub repository setup | CI/CD, issue templates, contributing guide |

---

## Future (No Timeline)

Design and implement based on user feedback. See `docs/FUTURE.md` for full descriptions.

- Plugin system (entry_points discovery)
- Vendor plugins (stm32, esp32, nrf, yocto, zephyr, freertos)
- C/H header parser (tree-sitter, structured API tables)
- Agent skills + slash commands
- `hwcc augment` command (stdin → context-enriched stdout)
- Watch mode + git hooks
- Query decomposition for multi-peripheral search
- Document versioning (silicon revision tracking)
- Hardware llms.txt standard
- DT binding YAML parser
- Kconfig parser

---

## Research References

| Source | Key Findings Applied |
|--------|---------------------|
| **EmbedGenius** (arXiv:2412.09058v2) | Pin assignments, keyword scoring (-26.2% tokens), content type taxonomy, usage patterns (+7.1% accuracy), API tables |
| **Embedder** (YC S25) | Source citations, per-field SVD reset values, SVD catalog, errata-to-register linking |

**Evaluated but rejected**:
- Hardware relationship inference → vendor-specific, plugin scope
- Coding standard presets → `[conventions]` free-text suffices
- Embedding-based compile selection → deterministic keyword scoring instead

---

## Out of Scope (v1)

- Web UI / TUI
- Team collaboration / sync
- Subscription / payment system
- Plugin marketplace
- Fine-tuned embedding models
- Knowledge graph / GraphRAG
- Post-generation validation (RespCode's approach — we solve pre-generation)
- MISRA/AUTOSAR presets
- Vendor-specific MCP federation

---

## Technical Risks

| Risk | Mitigation |
|------|------------|
| PDF table extraction quality varies | pdfplumber + PyMuPDF fallback; validate against SVD |
| Embedding model not available | ChromaDB built-in ONNX as zero-config default |
| MCP protocol changes | Pin mcp SDK version; follow changelog |
| Context file overwrites user content | Marker comments; never touch outside markers |

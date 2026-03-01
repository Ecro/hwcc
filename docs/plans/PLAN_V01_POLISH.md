# Plan: v0.1 Polish — Demo Readiness & Ship Quality

> **Date**: 2026-03-01
> **Status**: Proposed
> **Complexity**: High (17 items across 4 phases)
> **Risk**: Low per-item (each is isolated), Medium aggregate (scope discipline needed)

## Overview

The research assessment identified 17 weaknesses in 4 categories. This plan organizes them into **4 execution phases**, each independently committable, with clear scope boundaries.

```
Phase A: Demo Killers (must fix before showing to anyone)
Phase B: Output Quality (make generated context genuinely useful)
Phase C: Robustness (technical debt & safety)
Phase D: Strategic (competitive demo impact — v0.2 territory)
```

---

## Phase A: Demo Killers

**Goal**: A first-time user can `pip install`, run the tool, and not hit embarrassing failures.
**Effort**: ~2 sessions
**Commits**: 3-4

### A1. Fix README install instructions

**Problem (W3)**: README says `pip install hwcc` but package isn't on PyPI yet.
**Fix**: Change to install-from-source instructions until PyPI publish.

| File | Change |
|------|--------|
| `README.md` | Replace `pip install hwcc` with `pip install git+https://github.com/Ecro/hwcc.git` or local install instructions |

**Test**: Manual — verify README instructions work on clean venv.

### A2. Add sample project with pre-generated output

**Problem (W2)**: No way to see what hwcc produces without installing and running it.
**Fix**: Add `examples/stm32f407-motor/` with pre-generated output files.

| File | Change |
|------|--------|
| `examples/stm32f407-motor/CLAUDE.md` | create — sample with user content + hwcc section |
| `examples/stm32f407-motor/.rag/context/hot.md` | create — sample hot context |
| `examples/stm32f407-motor/.rag/context/peripherals/spi1.md` | create — sample peripheral |
| `examples/stm32f407-motor/.rag/context/peripherals/tim1.md` | create — sample peripheral |
| `examples/stm32f407-motor/.rag/config.toml` | create — sample config |
| `README.md` | Add "Example Output" section linking to examples/ |

**Source**: Copy directly from `/tmp/hwcc-demo/` artifacts (real demo output).
**Test**: Manual — files exist, README links work.

### A3. Add Rich progress indicator to `hwcc add`

**Problem (W4)**: Large SVD files take 10-30s of silence during embedding. User thinks it hung.
**Fix**: Add `rich.progress` spinner/bar around the embedding step in Pipeline.

| File | Change |
|------|--------|
| `src/hwcc/cli.py` | Add `rich.progress.Progress` context around `pipeline.process()` or use `console.status()` |

**Test**: Manual — `hwcc add` on large SVD shows progress. Unit tests unaffected (mocked pipeline).

### A4. Remove or hide stub CLI commands

**Problem (W1)**: `hwcc search`, `hwcc context`, `hwcc config`, `hwcc mcp` all print "not yet implemented". A demo audience will try them.
**Fix**: Hide unimplemented commands from `--help` by marking them `hidden=True` in Typer, or remove them entirely and re-add when implemented.

| File | Change |
|------|--------|
| `src/hwcc/cli.py` | Add `hidden=True` to `@app.command()` decorators for search, context, config, mcp |

**Test**: `hwcc --help` only shows working commands. Existing stub tests updated.

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Hidden commands not in --help output | `tests/test_cli.py` | unit |
| 2 | Stub commands still callable, still return 0 | `tests/test_cli.py` | unit |

---

## Phase B: Output Quality

**Goal**: The generated context is genuinely useful to AI coding tools, not just technically present.
**Effort**: ~3 sessions
**Commits**: 4-5

### B1. Populate `register_count` in PeripheralSummary

**Problem (W8)**: `PeripheralSummary.register_count` is always 0, so hot.md peripheral list shows bare names without useful metadata.
**Fix**: Count SVD register-level chunks per peripheral during `_gather_peripherals()` in HotContextCompiler.

| File | Change |
|------|--------|
| `src/hwcc/compile/hot_context.py` | In `_gather_peripherals()`, count chunks per peripheral from store metadata |

Actually — `_gather_peripherals()` only reads metadata (no chunk content). The register count should come from counting SVD chunks whose `section_path` 2nd element matches the peripheral name. This needs `get_chunks()` or a dedicated count method on the store.

**Simpler approach**: PeripheralContextCompiler already discovers peripherals and extracts register maps. Pass the count back. Or: count "Register Map" section headers in the rendered register_map string.

**Recommended approach**: In `HotContextCompiler._gather_peripherals()`, also call `store.get_chunk_metadata()` filtered to `doc_type == "svd"`, group by peripheral name, count unique register offsets per peripheral.

| File | Change |
|------|--------|
| `src/hwcc/compile/hot_context.py` | Enhance `_gather_peripherals()` to count SVD chunks per peripheral |

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | PeripheralSummary has non-zero register_count when SVD chunks exist | `tests/test_compile_hot_context.py` | unit |
| 2 | register_count renders in hot.md template | `tests/test_compile_hot_context.py` | unit |

### B2. Improve peripheral context structure

**Problem (W10)**: Peripheral .md files are raw chunk concatenations with no structural sections.
**Fix**: Update `peripheral.md.j2` template to add structured sections and improve readability.

| File | Change |
|------|--------|
| `src/hwcc/templates/peripheral.md.j2` | Add Overview section header, separate Register Map and Additional Details with clear headings |
| `src/hwcc/compile/peripheral.py` | Extract peripheral description from SVD metadata for overview section |

Current template:
```jinja2
# {{ peripheral_name }} — {{ mcu }}
{{ peripheral_details }}
## Register Map
{{ register_map }}
```

Improved template:
```jinja2
# {{ peripheral_name }} — {{ mcu }}

{% if peripheral_description %}
{{ peripheral_description }}
{% endif %}

{% if register_map %}
## Register Map
{{ register_map }}
{% endif %}

{% if peripheral_details %}
## Additional Documentation
{{ peripheral_details }}
{% endif %}

{% if errata %}
## Known Errata
...
{% endif %}
```

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Peripheral template renders with structured sections | `tests/test_compile_peripheral.py` | unit |
| 2 | SVD description appears in peripheral output | `tests/test_compile_peripheral.py` | unit |

### B3. Extract and pass peripheral description from SVD

**Problem**: SVD files contain `<description>` elements per peripheral (e.g., "Serial peripheral interface") but this is lost in the pipeline. The peripheral context files have no overview.
**Fix**: Store peripheral description in ChunkMetadata or extract from first SVD chunk per peripheral.

The SVD parser already puts the peripheral description in the first chunk's content as the header line (e.g., `## SPI1\n\n**Base Address:**...`). The description is present in the rendered content but not as a separate field.

**Simpler approach**: Parse the description from the first SVD chunk's content for each peripheral (it follows the `**Description:**` pattern). No pipeline change needed.

| File | Change |
|------|--------|
| `src/hwcc/compile/peripheral.py` | Add `_extract_description()` that parses description from register map content |
| `src/hwcc/compile/context.py` | Add `peripheral_description` field to CompileContext (or reuse existing `peripheral_details` naming) |

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Description extracted from SVD register map content | `tests/test_compile_peripheral.py` | unit |

### B4. Differentiate target templates minimally

**Problem (W9)**: claude/agents/gemini/copilot templates are near-identical. The "multi-tool" value prop is weak.
**Fix**: Add tool-specific instructions to each template where applicable.

| File | Change |
|------|--------|
| `src/hwcc/templates/claude.md.j2` | Add "When writing hardware code, check .rag/context/peripherals/ for register details" |
| `src/hwcc/templates/agents.md.j2` | Add Codex-specific formatting hints |
| `src/hwcc/templates/cursor.mdc.j2` | Already differentiated (frontmatter globs). Add `alwaysApply: true` |
| `src/hwcc/templates/gemini.md.j2` | Add Gemini-specific hints |

**Scope**: Minimal — only add 2-3 lines per template. Do NOT redesign templates.

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Each target template renders differently | `tests/test_compile_templates.py` | unit |

---

## Phase C: Robustness

**Goal**: Fix technical debt that causes real problems at scale or in unusual conditions.
**Effort**: ~2 sessions
**Commits**: 3-4

### C1. Add `--verbose` flag to CLI

**Problem (W14)**: Users have no way to get debug output when something goes wrong.
**Fix**: Add `--verbose` / `-v` global option via Typer callback.

| File | Change |
|------|--------|
| `src/hwcc/cli.py` | Add `@app.callback()` with `--verbose` option, configure logging level |

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `--verbose` sets logging level to DEBUG | `tests/test_cli.py` | unit |
| 2 | Default logging level is WARNING | `tests/test_cli.py` | unit |

### C2. Fix provider registration fragility

**Problem (W12)**: `import hwcc.embed` as a side-effect registration is fragile. Any code path that skips this import gets empty registry.
**Fix**: Make registry auto-discover providers on first `.create()` call using a lazy import.

| File | Change |
|------|--------|
| `src/hwcc/registry.py` | Add `_ensure_registered()` method that does lazy import of `hwcc.embed` on first `create()` call |
| `src/hwcc/cli.py` | Remove `import hwcc.embed  # noqa: F401` (no longer needed) |

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Registry auto-discovers providers without explicit import | `tests/test_registry.py` | unit |
| 2 | create() works without prior import of hwcc.embed | `tests/test_registry.py` | integration |

### C3. Memory-bounded chunk retrieval

**Problem (W11)**: `PeripheralContextCompiler.compile()` calls `store.get_chunks()` which loads ALL chunks into memory. For large projects (10+ documents), this is wasteful.
**Fix**: Add `get_chunks(doc_type=...)` filter parameter to BaseStore/ChromaStore.

| File | Change |
|------|--------|
| `src/hwcc/store/base.py` | Add optional `doc_type` filter to `get_chunks()` |
| `src/hwcc/store/chromadb_store.py` | Implement filtered `get()` using ChromaDB `where` clause |
| `src/hwcc/compile/peripheral.py` | Use `store.get_chunks(doc_type="svd")` and `store.get_chunks(doc_type_ne="svd")` |

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `get_chunks(doc_type="svd")` returns only SVD chunks | `tests/test_store.py` | unit |
| 2 | `get_chunks()` without filter still returns all | `tests/test_store.py` | unit |

### C4. Improve XXE probe size (minor)

**Problem (W13)**: XXE mitigation only reads first 8KB. Documented as bypassable.
**Fix**: Increase probe size to 64KB and add a note in security docs. Full XML parsing mitigation would be a separate effort.

| File | Change |
|------|--------|
| `src/hwcc/ingest/svd.py` | Increase `_SAFETY_PROBE_SIZE` from 8192 to 65536 |

**Test**: Existing XXE tests still pass. No new tests needed.

---

## Phase D: Strategic (v0.2 Territory)

**Goal**: Features that make the competitive demo compelling. These are larger efforts.
**Effort**: Multiple sessions each
**Status**: Deferred — plan only, execute in v0.2

### D1. Source citations per chunk (W6, task 2.5)

Track provenance through the pipeline: each chunk carries `source_doc`, `source_page`, `source_section`. Compile stage renders `*Source: RM0090 §28.3.3, p.868*` inline.

→ Already planned as task 2.5 in PLAN.md for v0.2.

### D2. `hwcc search` implementation (W1 partial, task 3.6)

Hybrid vector + keyword search with Rich-formatted results. Core UX command.

→ Already planned as task 3.6 in PLAN.md for v0.2.

### D3. SVD catalog (W16, task 1.13)

`hwcc catalog list/add` using cmsis-svd's bundled 300+ SVD files. Zero-friction onboarding.

→ Already planned as task 1.13 in PLAN.md for v0.2.

### D4. Errata extraction from PDF (W5)

Populate `ErrataSummary` from errata PDFs using content_type detection and heuristic parsing.

→ New task for v0.2. Template infrastructure already exists.

### D5. Before/after showcase (W15)

Create a compelling demo showing "LLM without hwcc hallucinates registers" vs "LLM with hwcc gets them right". Example or documentation, not code.

→ Marketing/docs task for v0.2 or README update.

### D6. Peripheral cross-referencing with fuzzy matching (W7)

Currently exact-match on section_path elements. Add fuzzy matching (e.g., "Serial Peripheral Interface" → "SPI1") using keyword overlap.

→ New task for v0.2. Ties into relevance scoring (task 2.7).

---

## Execution Order

```
Phase A (Demo Killers)     →  commit per item  →  4 commits
Phase B (Output Quality)   →  commit per item  →  4 commits
Phase C (Robustness)       →  commit per item  →  4 commits
Phase D (Strategic)        →  deferred to v0.2  →  plan references only
```

**Recommended execution within phases**:

```
A1 (README fix)        — 10 minutes, trivial
A4 (hide stubs)        — 20 minutes, small
A3 (progress bar)      — 30 minutes, small
A2 (sample project)    — 45 minutes, copy from demo artifacts

B1 (register_count)    — 30 minutes, small logic change
B3 (SVD description)   — 30 minutes, parse from content
B2 (template structure) — 20 minutes, template edit (depends on B3)
B4 (template differentiation) — 20 minutes, template edits

C1 (--verbose flag)    — 30 minutes, CLI plumbing
C2 (lazy registration) — 30 minutes, registry refactor
C3 (filtered get_chunks) — 45 minutes, store interface change
C4 (XXE probe size)    — 5 minutes, constant change
```

## NON-GOALS (Explicitly Out of Scope)

- [ ] MCP server implementation — v0.3
- [ ] Plugin system — Future
- [ ] Pin assignment rendering — v0.2 task 2.6
- [ ] Relevance-scored chunk selection — v0.2 task 2.7
- [ ] Usage pattern extraction — v0.2 task 2.8
- [ ] PyPI publish mechanics — separate wrapup task
- [ ] Test suite expansion beyond what's needed for each fix
- [ ] Refactoring existing passing code

## Exit Criteria

```
□ hwcc --help shows only working commands
□ README has working install instructions
□ examples/ directory exists with real output
□ hwcc add shows progress for large files
□ Peripheral hot.md list includes register counts
□ Peripheral .md files have structured sections
□ --verbose flag works
□ All 675+ tests pass
□ No ruff/mypy violations
```

---

> **Last Updated**: 2026-03-01

# Plan: Re-scope hwcc Documents into Master Blueprints

> **Date**: 2026-03-01
> **Type:** refactor (documentation restructure)
> **Status**: Draft

---

## Scope Declaration

### Change Intent
- **Type:** refactor
- **Single Concern:** Restructure TECH_SPEC.md and PLAN.md into concise master blueprints that show the FULL vision at a high level, with detailed specs delegated to per-feature docs

### Concern Separation Rule
This change is ONLY about: Document restructure — elevating to blueprint level
This change is NOT about: Cutting features, writing new code, or changing architecture

---

## Problem Statement

**What:** TECH_SPEC.md (845 lines) and PLAN.md (671 lines) mix blueprint-level vision with implementation-level detail. Some done tasks have 10 lines of sub-bullets. Future features have full API specs. You can't see the forest for the trees.

**Why:** Master docs should be architectural blueprints — the whole building visible at a glance. Detailed pipe fittings belong in per-feature plans (`docs/plans/PLAN_*.md`), which already exist.

**Success:** An engineer reads TECH_SPEC.md in 5 minutes and understands the FULL vision. Reads PLAN.md in 3 minutes and knows every milestone, what's done, what's active, what's planned. Dives into `docs/plans/PLAN_*.md` for implementation details.

---

## Document Architecture

```
TECH_SPEC.md          ← Master blueprint (FULL vision, ~400 lines)
                         Every feature mentioned, none detailed
                         Status tags: [DONE] [ACTIVE] [PLANNED] [FUTURE]

PLAN.md               ← Master roadmap (~250 lines)
                         Every milestone, every task = ONE LINE
                         Links to detailed plans
                         Clear v0.1 / v0.2 / v1.0 milestones

docs/plans/PLAN_*.md  ← Detailed per-feature plans (already exist, 21 files)
                         Implementation steps, test plans, impact analysis
                         Created on-demand before each /execute

docs/STRATEGY.md      ← Competitive analysis + market research
                         Moved from TECH_SPEC §2 (not a tech spec)

CLAUDE.md             ← Project instructions for Claude Code
                         Updated to match reality
```

### Guiding Principle

| Level | Document | Detail | Example |
|-------|----------|--------|---------|
| **Vision** | TECH_SPEC.md | What the system IS and DOES | "MCP server exposes hw_search, hw_registers, hw_context tools" |
| **Roadmap** | PLAN.md | When things ship, one line per task | "3.1 MCP server (hw_search, hw_registers, hw_context) [PLANNED]" |
| **Implementation** | docs/plans/PLAN_*.md | How to build it | Full API spec, parameters, test plan, file changes |

**Rule:** If a section in TECH_SPEC grows past 30 lines, it belongs in a PLAN_*.md file with a link from the master.

---

## TECH_SPEC.md Master Blueprint Structure

Target: ~400 lines. Every feature present, none over-detailed.

```markdown
# hwcc — Technical Specification (Master Blueprint)

## 1. What This Is
   - Core value proposition (10 lines)
   - What it is NOT (5 lines)
   - Why preprocessing > context stuffing (5 lines)
   Keep. Trim "why won't become obsolete" from 8 lines to 3.

## 2. Architecture Overview
   - Pipeline diagram (keep)
   - ABC contracts table (keep)
   - Data flow diagram (keep)
   - Provider registry (keep, 5 lines)
   - Exception hierarchy (keep)
   MERGE current §3 here. Remove code examples (those are in source).

## 3. Data Store Structure
   - .rag/ directory tree (keep)
   - config.toml example (keep, shorten)
   - manifest.json example (keep, shorten)
   Keep current §4. Minor trim.

## 4. Ingestion Pipeline
   - Document type detection table (keep)
   - Processing pipeline diagram (keep)
   - Chunking strategy table (keep)
   - Content type taxonomy table (keep)
   - SVD field-level reset values (keep, 3 lines not 10)
   Keep current §5. Remove code examples.

## 5. Output & Serving Layer
   CONSOLIDATE current §6 (was 7 sub-sections, ~150 lines).

   ### 5.1 Static Context Files [DONE]
     - Output table (5 targets) — keep
     - Peripheral context 6-section structure — keep
     - Hot context structure — keep
     - Non-destructive markers — 2 lines

   ### 5.2 MCP Server [PLANNED]
     - Tool table (3 tools: hw_search, hw_registers, hw_context)
     - One line each. No parameter specs. No example calls.
     - Link: → see docs/plans/PLAN_MCP_SERVER.md when created

   ### 5.3 CLI Search [PLANNED]
     - One line: "hwcc search <query> — hybrid vector + keyword search"

   ### 5.4 Clipboard & Pipe [FUTURE]
     - 3 lines: what they do, why useful
     - No API spec, no code examples

## 6. CLI Interface
   - Command table with one-line descriptions (keep)
   - Status tags per command: [DONE] [STUB] [PLANNED]
   Remove detailed flag descriptions. Those are in --help.

## 7. Technology Stack
   - Core dependencies table (keep, FIX: remove tree-sitter, litellm, pyperclip)
   - Optional dependencies table (keep)

## 8. Provider System
   SIMPLIFY current §9 from 30 lines to 10.
   - Embedding: ChromaDB ONNX (default) | Ollama | OpenAI-compat
   - LLM: Ollama (default) | any OpenAI-compat endpoint
   - "90% works with zero LLM" — keep this one line

## 9. Extension Points [FUTURE]
   REPLACE current §10 (plugin system, 60 lines) with 15 lines:
   - Plugin interface concept (5 lines)
   - Planned areas: vendor-specific parsers, knowledge providers
   - "Design deferred until core pipeline has users"

## 10. Incremental Indexing
   Keep current §12 as-is (15 lines).

## 11. Security & Privacy
   Keep current §13 as-is (10 lines).

## 12. Open Questions
   Trim to only truly open questions.

REMOVE entirely:
  - §2 Competitive Landscape → docs/STRATEGY.md
  - §11 Integration Compatibility Matrix → README.md
```

### What Gets MOVED vs REMOVED

| Current Section | Lines | Action | Destination |
|----------------|:---:|--------|-------------|
| §2 Competitive Landscape | 65 | MOVE | `docs/STRATEGY.md` |
| §6.2 MCP detailed API | 20 | CONDENSE | 3 lines in master |
| §6.3 Slash commands (7 commands) | 15 | CONDENSE | 2 lines in master |
| §6.4 Clipboard mode | 8 | CONDENSE | 1 line in master |
| §6.5 Pipe mode | 8 | CONDENSE | 1 line in master |
| §6.6 Agent skill YAML | 25 | CONDENSE | 2 lines in master |
| §9 Provider tiers (detailed chains) | 20 | SIMPLIFY | 10 lines |
| §10 Plugin system (code examples) | 40 | CONDENSE | 15 lines, no code |
| §11 Integration matrix | 15 | MOVE | README |
| Code examples throughout | ~60 | REMOVE | Already in source code |

**Nothing is deleted from the vision.** Every feature stays mentioned. Detail moves to the right document.

---

## PLAN.md Master Roadmap Structure

Target: ~250 lines. Every task = one line. Status visible at a glance.

```markdown
# hwcc — Implementation Roadmap

## Current Status
  v0.1-dev | Phase 2 active | 669 tests | 36 source files

## Milestones

### v0.1 — MVP (Core Loop)
  Goal: hwcc add → hwcc compile → CLAUDE.md works end-to-end

  Phase 0: Foundation [DONE]
    ✓ 0.1-0.5 (collapsed to one line: "Project skeleton, config, manifest, CLI, init")

  Phase 1: Ingest [DONE]
    ✓ 1.1-1.12, 1.15 (collapsed: "SVD, PDF, MD, text, DTS parsers. Chunking. Embedding. Store. Content types. Reset values.")
    - 1.13 SVD catalog [DEFERRED to v0.2]
    - 1.14 Document versioning [DEFERRED to v0.2]

  Phase 2: Compile [ACTIVE]
    ✓ 2.1 Hot context compiler
    ✓ 2.2 Peripheral context compiler
    ✓ 2.3 Template system (Jinja2)
    ✓ 2.4 Output generators (claude/codex/cursor/gemini/copilot)
    → 2.9 Wire hwcc compile CLI [BLOCKING v0.1]
    → 2.10 Auto-compile on hwcc add [BLOCKING v0.1]
    - 2.5 Source citations [v0.2]
    - 2.6 Pin assignments in output [v0.2]
    - 2.7 Relevance scoring [v0.2]
    - 2.8 Usage pattern extraction [v0.2]

  Ship: README + PyPI publish

### v0.2 — Quality & Search
  - 1.13 SVD catalog (zero-config UX)
  - 2.5 Source provenance / citations
  - 2.6 Pin assignments in output
  - 2.7 Relevance-scored chunk selection
  - 2.8 Usage pattern extraction
  - 3.6 hwcc search CLI
  Link: → detailed plans in docs/plans/

### v0.3 — MCP Server
  - 3.1 MCP server (hw_search, hw_registers, hw_context)
  - 3.2 hwcc mcp CLI command
  Link: → docs/plans/PLAN_MCP_SERVER.md (to be created)

### v1.0 — Integrations & Polish
  - Clipboard mode (hwcc context --copy)
  - Pipe mode (hwcc context | tool)
  - Slash commands
  - Agent skills
  Link: → Design based on user feedback from v0.1-v0.3

### Future (No Timeline)
  - Plugin system
  - Vendor plugins (stm32, esp32, nrf, yocto, zephyr, freertos)
  - C/H header parser
  - Query decomposition
  - Watch mode + git hooks
  - hwcc augment command
  - Document versioning
  - Hardware llms.txt standard
  Link: → docs/FUTURE.md

## Out of Scope (v1)
  (keep current list, add items from above)

## Research References
  (keep, trim to table only — no prose)
```

### Key Differences from Current PLAN.md

| Current | Proposed |
|---------|----------|
| Done tasks have 5-10 lines of sub-bullets | Done tasks collapsed to ✓ one-liners |
| All tasks at same detail level | Only ACTIVE tasks get detail |
| Linear phases (must finish 2 before 3) | Milestone-based (v0.1, v0.2, v0.3) |
| 50+ tasks, unclear what ships when | Clear: 2 tasks block v0.1, everything else is later |
| Strategic focus section (15 lines) | Status line (1 line) |
| File structure section (80 lines) | Remove — it's in the actual file system |

---

## Other Documents

### docs/STRATEGY.md (NEW)

Move TECH_SPEC §2 here intact:
- Market positioning diagram
- Competitor table
- Strategic gaps table
- Complementary ecosystem
- Market validation bullets

This IS valuable content — it just doesn't belong in a tech spec.

### CLAUDE.md (UPDATE)

Fix stale claims:
- "99 tests" → "669 tests"
- Update pipeline stages table
- Update build commands if needed
- Reflect actual status of each module

### docs/FUTURE.md (NEW)

Wish list of all deferred features with 1-2 line descriptions each. Nothing is lost, everything has a home.

---

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Create STRATEGY.md | `docs/STRATEGY.md` | Move TECH_SPEC §2 competitive landscape here |
| 2 | Create FUTURE.md | `docs/FUTURE.md` | Wish list of all deferred features |
| 3 | Rewrite TECH_SPEC.md | `TECH_SPEC.md` | Master blueprint: full vision, concise, status-tagged |
| 4 | Rewrite PLAN.md | `PLAN.md` | Master roadmap: milestone-based, one line per task |
| 5 | Update CLAUDE.md | `CLAUDE.md` | Fix stale claims, match reality |

### Dependency Chain

```
Step 1 (STRATEGY.md) — independent, do first to clear material for TECH_SPEC rewrite
Step 2 (FUTURE.md) — independent
Step 3 (TECH_SPEC) — after step 1 (needs §2 removed)
Step 4 (PLAN.md) — after step 2 (needs feature list for FUTURE refs)
Step 5 (CLAUDE.md) — after steps 3-4 (references need to be accurate)

Steps 1+2 can be parallel. Steps 3+4 can be parallel.
```

---

## NON-GOALS

- [ ] Writing new feature code
- [ ] Changing any Python source files
- [ ] Deleting ANY feature from the vision — everything stays, just at the right detail level
- [ ] Changing the architecture
- [ ] Detailed plans for v0.2+ features (those get written when we start each milestone)

---

## Exit Criteria

```
□ TECH_SPEC.md is a master blueprint (~400 lines, full vision, no implementation detail)
□ PLAN.md is a master roadmap (~250 lines, every task visible, one line each)
□ docs/STRATEGY.md contains competitive analysis (moved from TECH_SPEC)
□ docs/FUTURE.md lists all deferred features (nothing lost)
□ CLAUDE.md matches reality (test count, tech stack, defaults)
□ Every feature in current docs is present somewhere (nothing deleted)
□ Status tags [DONE] [ACTIVE] [PLANNED] [FUTURE] on every feature
□ v0.1 blocking tasks clearly identified
□ No code changes
```

---

> **Last Updated:** 2026-03-01

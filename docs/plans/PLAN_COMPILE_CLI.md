# Plan: Wire hwcc compile CLI and auto-compile on add

## Scope Declaration
- **Type:** feature
- **Single Concern:** Connect existing compiler classes to `hwcc compile` CLI and auto-trigger after `hwcc add`
- **Phase:** 2 (Compile)
- **Complexity:** Low
- **Risk:** Low

## Problem Statement
**What:** `hwcc compile` prints "not yet implemented" even though `HotContextCompiler`, `PeripheralContextCompiler`, and `OutputCompiler` are fully implemented and tested. This blocks the entire v0.1 core loop.
**Why:** Without this, nobody can use hwcc end-to-end.
**Success:** `hwcc add board.svd && hwcc compile` produces `.rag/context/hot.md`, `.rag/context/peripherals/*.md`, and `CLAUDE.md` with hardware context.

## NON-GOALS (Explicitly Out of Scope)
- [ ] Source citations (task 2.5) — v0.2
- [ ] Pin assignments (task 2.6) — v0.2
- [ ] Relevance scoring (task 2.7) — v0.2
- [ ] Usage pattern extraction (task 2.8) — v0.2
- [ ] New templates or template changes
- [ ] Config command wiring
- [ ] Search command wiring

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/cli.py` | modify | Replace `compile_cmd` stub with real implementation; add `_compile_project()` helper; call it from `add` command |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `compile_cmd()` | CLI (typer) | `HotContextCompiler.compile()`, `PeripheralContextCompiler.compile()`, `OutputCompiler.compile()` |
| `_compile_project()` | `compile_cmd()`, `add()` | Same compilers, `load_config()`, `ChromaStore()`, `ProjectManager` |

### Pipeline Impact
| Pipeline Stage | Upstream | Downstream |
|---------------|----------|------------|
| Compile | Store (has chunks) | Output files (CLAUDE.md etc.) |

## Technical Approach

### How existing compilers work

1. **HotContextCompiler(project_root)** — reads manifest + store metadata + config → writes `.rag/context/hot.md`
2. **PeripheralContextCompiler(project_root)** — reads SVD chunks from store → writes `.rag/context/peripherals/*.md`
3. **OutputCompiler(project_root)** — reads `hot.md` + config → injects into CLAUDE.md/AGENTS.md/etc.

Execution order matters: Hot → Peripheral → Output (Output reads hot.md).

### Implementation

Add a `_compile_project()` helper that:
1. Loads config and creates store
2. Runs HotContextCompiler
3. Runs PeripheralContextCompiler
4. Runs OutputCompiler
5. Reports results via Rich

Wire it into:
- `compile_cmd()` — replacing the stub
- `add()` — called after successful document addition (with `--no-compile` opt-out)

## Implementation Steps

| # | Task | Description |
|---|------|-------------|
| 1 | Add `_compile_project()` helper to `cli.py` | Instantiate 3 compilers, run in order, report results |
| 2 | Wire `compile_cmd()` to `_compile_project()` | Replace `_not_implemented("compile")` |
| 3 | Add `--no-compile` flag to `add` command | Default: auto-compile after add |
| 4 | Call `_compile_project()` at end of `add` | After all documents processed, if any were added |
| 5 | Write tests | Test compile CLI and auto-compile behavior |

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `hwcc compile` produces hot.md when store has chunks | `tests/test_cli.py` | integration |
| 2 | `hwcc compile` produces peripheral files for SVD data | `tests/test_cli.py` | integration |
| 3 | `hwcc compile` produces CLAUDE.md with markers | `tests/test_cli.py` | integration |
| 4 | `hwcc compile` on empty project exits gracefully | `tests/test_cli.py` | unit |
| 5 | `hwcc compile --target claude` only produces CLAUDE.md | `tests/test_cli.py` | unit |
| 6 | `hwcc add` auto-compiles after adding document | `tests/test_cli.py` | integration |
| 7 | `hwcc add --no-compile` skips compilation | `tests/test_cli.py` | unit |

### Acceptance Criteria
| # | Scenario | Expected Result |
|---|----------|----------------|
| 1 | `hwcc init && hwcc add board.svd` | CLAUDE.md has hardware section between markers |
| 2 | `hwcc compile` with no docs | Exits cleanly, prints "nothing to compile" |
| 3 | `hwcc compile --target claude` | Only CLAUDE.md generated, not AGENTS.md |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/cli.py` | modify | Add `_compile_project()`, wire `compile_cmd`, add auto-compile to `add` |

## Exit Criteria
```
□ hwcc compile produces hot.md + peripheral/*.md + CLAUDE.md
□ hwcc add auto-compiles (with --no-compile opt-out)
□ hwcc compile on empty project exits gracefully
□ All 669+ existing tests still pass
□ New tests pass
□ ruff + mypy clean
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] Manual test: `hwcc init --chip STM32F407 && hwcc add tests/fixtures/*.svd && hwcc status`

## Document Updates Needed
- [ ] **PLAN.md:** Mark tasks 2.9 and 2.10 as done

---

> **Last Updated:** 2026-03-01

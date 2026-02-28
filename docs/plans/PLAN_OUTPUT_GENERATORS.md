# Plan: 2.4 Output File Generators

## Scope Declaration
- **Type:** feature
- **Single Concern:** Implement `OutputCompiler` that renders target-specific output files (CLAUDE.md, AGENTS.md, etc.) with non-destructive marker-based injection into existing files.
- **Phase:** 2 (Context Compilation)
- **Complexity:** Medium
- **Risk:** Medium (file I/O with existing user files requires careful non-destructive logic)

## Problem Statement
**What:** Create a compiler that generates tool-specific output files from compiled context, injecting hardware sections between markers in existing files without destroying user content.
**Why:** This is the "tool-agnostic differentiator" (Gap G3) — one `hwcc compile` produces output for Claude Code, Codex, Cursor, Gemini, and Copilot simultaneously. No competitor does this.
**Success:** Running OutputCompiler generates all configured target files with correct content, preserving existing user content outside markers.

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/compile/output.py` | create | New `OutputCompiler(BaseCompiler)` class |
| `src/hwcc/compile/__init__.py` | modify | Add `OutputCompiler` to exports |
| `tests/test_compile_output.py` | create | Tests for OutputCompiler |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `OutputCompiler.compile()` | Future `hwcc compile` CLI (task 2.5) | `TemplateEngine.render_target()`, `CompileContext.from_config()`, `HotContextCompiler._gather_documents()` pattern |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Compile | Reads `.rag/context/hot.md` (from HotContextCompiler) | Writes to project root (CLAUDE.md, AGENTS.md, etc.) |

## NON-GOALS (Explicitly Out of Scope)
- [ ] CLI command (`hwcc compile`) — Task 2.5
- [ ] Auto-compile on `hwcc add` — Task 2.6
- [ ] Template modifications — Templates already exist and work
- [ ] MCP server integration — Phase 3
- [ ] Peripheral/HotContext compiler changes — Already complete
- [ ] Store/embed/ingest changes — Unrelated pipeline stages

## Technical Approach

### Option A: Single OutputCompiler class (Recommended)

One `OutputCompiler(BaseCompiler)` that iterates over `config.output.targets`, renders each template, and performs marker-based injection.

**Key design:**

1. **Constructor**: Takes `project_root: Path` (same pattern as HotContextCompiler)
2. **compile()**: Iterates configured targets, renders each, injects into files
3. **_inject_content()**: Core non-destructive logic:
   - File exists with markers → replace between markers (inclusive)
   - File exists without markers → append rendered content
   - File doesn't exist → create with rendered content
4. **_build_context()**: Builds CompileContext with hot_context from `.rag/context/hot.md`
5. **_gather_documents()**: Reuse pattern from HotContextCompiler (reads manifest)
6. **_gather_peripherals()**: Reuse pattern from HotContextCompiler (reads store metadata)

**Marker injection algorithm:**
```
rendered = engine.render_target(target, context)
# rendered already contains BEGIN/END markers from template

if file exists:
    existing = file.read_text()
    begin_idx = existing.find(begin_marker)
    end_idx = existing.find(end_marker)
    if begin_idx >= 0 and end_idx >= 0 and end_idx > begin_idx:
        # Replace marker section
        new = existing[:begin_idx] + rendered + existing[end_idx + len(end_marker):]
        # Strip trailing whitespace after end marker
    elif begin_idx >= 0:
        # Malformed: begin but no end — append after existing content
        new = existing + "\n\n" + rendered
    else:
        # No markers — append
        new = existing.rstrip() + "\n\n" + rendered + "\n"
else:
    new = rendered
file.write_text(new)
```

- **Pros:** Simple, follows existing patterns, one class handles all targets
- **Cons:** None significant

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Write tests (RED) | `tests/test_compile_output.py` | TDD: write all test cases first |
| 2 | Implement OutputCompiler | `src/hwcc/compile/output.py` | Core compiler with non-destructive injection |
| 3 | Export from __init__ | `src/hwcc/compile/__init__.py` | Add OutputCompiler to public API |
| 4 | Verify (GREEN) | — | All tests pass, lint/mypy clean |

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Generates output files for all configured targets | `tests/test_compile_output.py` | unit |
| 2 | Creates parent directories (e.g., .cursor/rules/) | `tests/test_compile_output.py` | unit |
| 3 | Returns list of written paths | `tests/test_compile_output.py` | unit |
| 4 | Reads hot_context from .rag/context/hot.md | `tests/test_compile_output.py` | unit |
| 5 | Works without hot_context (minimal fallback) | `tests/test_compile_output.py` | unit |
| 6 | Non-destructive: preserves content before markers | `tests/test_compile_output.py` | unit |
| 7 | Non-destructive: preserves content after markers | `tests/test_compile_output.py` | unit |
| 8 | Non-destructive: replaces marker section on re-compile | `tests/test_compile_output.py` | unit |
| 9 | Appends when existing file has no markers | `tests/test_compile_output.py` | unit |
| 10 | Creates new file when none exists | `tests/test_compile_output.py` | unit |
| 11 | Respects config.output.targets (only generates configured) | `tests/test_compile_output.py` | unit |
| 12 | Skips unknown targets with warning | `tests/test_compile_output.py` | unit |
| 13 | Wraps exceptions in CompileError | `tests/test_compile_output.py` | unit |
| 14 | Empty store produces valid output | `tests/test_compile_output.py` | unit |
| 15 | Renders correct content per target (Claude has MCP hints, etc.) | `tests/test_compile_output.py` | unit |
| 16 | Handles malformed markers (begin without end) | `tests/test_compile_output.py` | unit |
| 17 | Single target config generates only that target | `tests/test_compile_output.py` | unit |
| 18 | Idempotent: re-running produces same result | `tests/test_compile_output.py` | unit |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | OutputCompiler.compile() with default config | Creates CLAUDE.md, AGENTS.md, .cursor/rules/hardware.mdc, .gemini/GEMINI.md | automated |
| 2 | Existing CLAUDE.md with user content + markers | User content preserved, hwcc section updated | automated |
| 3 | Existing CLAUDE.md without markers | Hwcc section appended at end | automated |
| 4 | Re-run after content change | Only marker section changes, rest preserved | automated |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/compile/__init__.py` | modify | Add `OutputCompiler` to imports and `__all__` |

## Files to Create
| File | Purpose |
|------|---------|
| `src/hwcc/compile/output.py` | OutputCompiler class — renders + injects target output files |
| `tests/test_compile_output.py` | Tests for OutputCompiler |

## Exit Criteria
```
□ OutputCompiler generates all 5 target formats
□ Non-destructive injection preserves user content
□ Marker-based replacement works correctly
□ hot_context embedding works (reads from .rag/context/hot.md)
□ Respects config.output.targets
□ All tests pass: pytest tests/
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No unintended side effects in: peripheral.py, hot_context.py, templates.py, store/

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None (output targets already documented)
- [ ] **PLAN.md:** Mark task 2.4 as complete

---

> **Last Updated:** 2026-02-28

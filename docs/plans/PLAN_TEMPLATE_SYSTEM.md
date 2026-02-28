# Plan: Phase 2, Task 2.3 — Jinja2 Template System

## Scope Declaration
- **Type:** feature
- **Single Concern:** Implement the Jinja2 template engine and template files that render hardware context into tool-specific output formats
- **Phase:** 2 (Context Compilation)
- **Complexity:** Medium
- **Risk:** Low

## Problem Statement
**What:** Build the Jinja2 template infrastructure that renders structured hardware context data into tool-specific output formats (CLAUDE.md, AGENTS.md, .cursorrules, GEMINI.md, copilot-instructions.md, hot context, and peripheral context).

**Why:** Task 2.3 is the rendering layer that all other Phase 2 tasks depend on. Tasks 2.1 (hot context), 2.2 (peripheral context), and 2.4 (output generators) all need a template engine to produce their output. Additionally, the template format seeds the "hardware llms.txt" standard (Gap G6) — a well-documented, customizable template format becomes the de facto standard for hardware AI context.

**Success:** `TemplateEngine` loads built-in templates, supports user overrides from `.rag/templates/`, renders all 7 template types with typed context data, and has full test coverage.

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/compile/templates.py` | create | `TemplateEngine` class — Jinja2 environment setup, template loading with override support, rendering API |
| `src/hwcc/compile/context.py` | create | Template context dataclasses — `TargetInfo`, `DocumentSummary`, `PeripheralSummary`, `ErrataSummary`, `CompileContext` |
| `src/hwcc/compile/__init__.py` | modify | Export new classes |
| `src/hwcc/templates/hot_context.md.j2` | create | Hot context template (~50 lines) |
| `src/hwcc/templates/claude.md.j2` | create | CLAUDE.md hardware section template |
| `src/hwcc/templates/agents.md.j2` | create | AGENTS.md (Codex) template |
| `src/hwcc/templates/gemini.md.j2` | create | .gemini/GEMINI.md template |
| `src/hwcc/templates/cursor.mdc.j2` | create | .cursor/rules/hardware.mdc template |
| `src/hwcc/templates/copilot.md.j2` | create | .github/copilot-instructions.md template |
| `src/hwcc/templates/peripheral.md.j2` | create | Per-peripheral context template |
| `tests/test_compile_templates.py` | create | Template engine + rendering tests |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `TemplateEngine` | Future: `compile/hot.py` (2.1), `compile/output.py` (2.4) | `jinja2.Environment`, `jinja2.FileSystemLoader` |
| `CompileContext` | Future: `compile/hot.py` (2.1), `compile/peripheral.py` (2.2) | `config.HwccConfig`, `manifest.DocumentEntry` |
| Template files | `TemplateEngine.render()` | N/A (data files) |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Compile | None — new code, no existing callers | Provides rendering foundation for 2.1, 2.2, 2.4 |

## NON-GOALS (Explicitly Out of Scope)
- [ ] `compile/hot.py` — Hot context generator (task 2.1, separate concern: store querying logic)
- [ ] `compile/peripheral.py` — Peripheral context generator (task 2.2, separate concern: store querying logic)
- [ ] `compile/output.py` — Output file generators with non-destructive marker injection (task 2.4)
- [ ] `hwcc compile` CLI command implementation (task 2.5)
- [ ] Auto-compile on `hwcc add` (task 2.6)
- [ ] `BaseStore` interface changes (e.g., `get_by_metadata()`) — needed by 2.1/2.2, not by templates
- [ ] Registry registration of compiler providers — happens when concrete compilers exist (2.1/2.4)

## Technical Approach

### Option A: FileSystemLoader with Ordered Search Paths (Recommended)

Use Jinja2's `FileSystemLoader` with multiple search paths. User override templates in `.rag/templates/` are checked first, then built-in templates in `src/hwcc/templates/`.

```python
loader = jinja2.FileSystemLoader([
    str(project_root / ".rag" / "templates"),  # User overrides (checked first)
    str(builtin_template_dir),                  # Built-in (fallback)
])
env = jinja2.Environment(loader=loader, ...)
```

- **Pros:** Zero-config override mechanism (just drop a file in `.rag/templates/`), Jinja2's native feature, template inheritance works across both directories
- **Cons:** None significant

### Built-in Template Discovery

Use `importlib.resources` (Python 3.11+) to locate built-in templates reliably, whether running from source or installed package:

```python
from importlib.resources import files
builtin_dir = files("hwcc") / "templates"
```

Hatchling's wheel config (`packages = ["src/hwcc"]`) already includes all files under `src/hwcc/`, so `.j2` files are packaged automatically.

### Target Registry

Define a constant mapping from config target names to template files and output paths:

```python
TARGET_REGISTRY: dict[str, TargetInfo] = {
    "claude": TargetInfo(
        template="claude.md.j2",
        output_path=Path("CLAUDE.md"),
        begin_marker="<!-- BEGIN HWCC CONTEXT (auto-generated, do not edit) -->",
        end_marker="<!-- END HWCC CONTEXT -->",
    ),
    ...
}
```

This mapping is consumed by the output generators (task 2.4) but defined here as it's intrinsic to the template system's contract.

### Template Context Design

A `CompileContext` dataclass holds all data available to templates. The compile implementations (2.1, 2.2) will populate this and pass it to `engine.render()`.

Templates receive context as flat keyword arguments: `template.render(**asdict(context))`.

### Template Safety

- `jinja2.Environment(autoescape=False)` — output is markdown, not HTML
- `undefined=jinja2.StrictUndefined` — fail loudly on missing variables during development
- `keep_trailing_newline=True` — preserve file format
- `trim_blocks=True, lstrip_blocks=True` — clean Jinja2 control structure whitespace

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Create template context dataclasses | `src/hwcc/compile/context.py` | Define `TargetInfo`, `DocumentSummary`, `PeripheralSummary`, `ErrataSummary`, `CompileContext` frozen dataclasses |
| 2 | Create TemplateEngine class | `src/hwcc/compile/templates.py` | Jinja2 environment setup with dual search paths, `render()`, `render_target()`, `list_templates()`, `get_target_info()` methods |
| 3 | Create hot_context.md.j2 | `src/hwcc/templates/hot_context.md.j2` | Internal hot context template: chip summary, peripheral list, errata, conventions |
| 4 | Create peripheral.md.j2 | `src/hwcc/templates/peripheral.md.j2` | Per-peripheral context: register map, config notes, DMA, errata |
| 5 | Create target templates | `src/hwcc/templates/{claude,agents,gemini,cursor,copilot}.*` | 5 tool-specific output templates with appropriate formatting per target |
| 6 | Update compile __init__.py | `src/hwcc/compile/__init__.py` | Export `TemplateEngine`, `CompileContext`, `TargetInfo`, and other context types |
| 7 | Write tests | `tests/test_compile_templates.py` | Comprehensive tests for engine, rendering, overrides, error handling |
| 8 | Verify | N/A | `pytest`, `ruff check`, `ruff format`, `mypy` |

## Detailed Design

### context.py — Template Context Data Structures

```python
@dataclass(frozen=True)
class TargetInfo:
    """Metadata for an output target (claude, codex, cursor, etc.)."""
    template: str          # e.g., "claude.md.j2"
    output_path: Path      # Relative path from project root, e.g., Path("CLAUDE.md")
    begin_marker: str      # Non-destructive injection start marker
    end_marker: str        # Non-destructive injection end marker
    description: str       # Human-readable target description

@dataclass(frozen=True)
class DocumentSummary:
    """Summary of an indexed document for template rendering."""
    doc_id: str
    title: str
    doc_type: str
    chip: str
    chunk_count: int

@dataclass(frozen=True)
class PeripheralSummary:
    """Summary of a peripheral for template rendering."""
    name: str
    description: str
    register_count: int
    chip: str

@dataclass(frozen=True)
class ErrataSummary:
    """Summary of an errata entry for template rendering."""
    errata_id: str
    title: str
    description: str
    affected_peripheral: str
    severity: str               # "low" | "medium" | "high" | "critical"

@dataclass(frozen=True)
class CompileContext:
    """All data available to templates during compilation.

    Populated by the compile stage (tasks 2.1, 2.2) and passed
    to TemplateEngine.render().
    """
    # From config
    project_name: str
    project_description: str
    mcu: str
    mcu_family: str
    architecture: str
    clock_mhz: int
    flash_kb: int
    ram_kb: int
    rtos: str
    hal: str
    language: str
    build_system: str
    register_access: str
    error_handling: str
    naming: str

    # Compiled data
    documents: tuple[DocumentSummary, ...]
    peripherals: tuple[PeripheralSummary, ...]
    errata: tuple[ErrataSummary, ...]

    # Peripheral-specific (only for peripheral.md.j2)
    peripheral_name: str = ""
    register_map: str = ""
    peripheral_details: str = ""

    # Metadata
    hwcc_version: str = ""
    generated_at: str = ""
    mcp_available: bool = False

    # Pre-rendered content (for target templates that embed hot context)
    hot_context: str = ""
```

### templates.py — TemplateEngine

```python
class TemplateEngine:
    """Jinja2 template engine with built-in and user-override support.

    Template search order:
      1. .rag/templates/ (user overrides, optional)
      2. src/hwcc/templates/ (built-in, always present)
    """

    def __init__(self, project_root: Path | None = None) -> None:
        ...

    def render(self, template_name: str, context: CompileContext) -> str:
        """Render a template with the given compile context."""
        ...

    def render_target(self, target: str, context: CompileContext) -> str:
        """Render the template for a specific output target (e.g., 'claude')."""
        ...

    def list_templates(self) -> list[str]:
        """List all available template names (built-in + overrides)."""
        ...

    def is_overridden(self, template_name: str) -> bool:
        """Check if a template has a user override."""
        ...

    @staticmethod
    def get_target_info(target: str) -> TargetInfo:
        """Get the TargetInfo for a config target name."""
        ...

    @staticmethod
    def supported_targets() -> list[str]:
        """List all supported output target names."""
        ...
```

### Target Registry (constant in templates.py)

```python
TARGET_REGISTRY: dict[str, TargetInfo] = {
    "claude": TargetInfo(
        template="claude.md.j2",
        output_path=Path("CLAUDE.md"),
        begin_marker="<!-- BEGIN HWCC CONTEXT (auto-generated, do not edit) -->",
        end_marker="<!-- END HWCC CONTEXT -->",
        description="Claude Code context file",
    ),
    "codex": TargetInfo(
        template="agents.md.j2",
        output_path=Path("AGENTS.md"),
        begin_marker="<!-- BEGIN HWCC CONTEXT (auto-generated, do not edit) -->",
        end_marker="<!-- END HWCC CONTEXT -->",
        description="OpenAI Codex agent instructions",
    ),
    "cursor": TargetInfo(
        template="cursor.mdc.j2",
        output_path=Path(".cursor/rules/hardware.mdc"),
        begin_marker="<!-- BEGIN HWCC CONTEXT (auto-generated, do not edit) -->",
        end_marker="<!-- END HWCC CONTEXT -->",
        description="Cursor IDE rules file",
    ),
    "gemini": TargetInfo(
        template="gemini.md.j2",
        output_path=Path(".gemini/GEMINI.md"),
        begin_marker="<!-- BEGIN HWCC CONTEXT (auto-generated, do not edit) -->",
        end_marker="<!-- END HWCC CONTEXT -->",
        description="Google Gemini CLI context file",
    ),
    "copilot": TargetInfo(
        template="copilot.md.j2",
        output_path=Path(".github/copilot-instructions.md"),
        begin_marker="<!-- BEGIN HWCC CONTEXT (auto-generated, do not edit) -->",
        end_marker="<!-- END HWCC CONTEXT -->",
        description="GitHub Copilot instructions",
    ),
}
```

### Template File Designs

#### hot_context.md.j2

The internal hot context file (`.rag/context/hot.md`). Provides a concise hardware summary.

Key sections: Target Hardware, Indexed Documents, Peripherals, Errata Highlights, Coding Conventions. Uses conditionals to omit empty sections. Respects `hot_context_max_lines` by keeping content compact.

#### claude.md.j2

The CLAUDE.md hardware section. Wraps hot context with markers. Adds MCP tool hints if available. Includes "generated by" footer.

#### agents.md.j2

Same structure as claude.md.j2 but uses Codex-compatible formatting and agent-specific instructions (e.g., "Use hw_search tool...").

#### gemini.md.j2 / cursor.mdc.j2 / copilot.md.j2

Variations on the same content optimized for each tool's conventions. Cursor uses MDC format. Gemini uses its specific instruction format. Copilot uses GitHub's format.

#### peripheral.md.j2

Per-peripheral detailed context. Register map table, configuration notes, DMA mapping, related errata. Used by the peripheral context generator (task 2.2).

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | TemplateEngine loads built-in templates | `tests/test_compile_templates.py` | unit |
| 2 | TemplateEngine renders hot_context.md.j2 with full context | `tests/test_compile_templates.py` | unit |
| 3 | TemplateEngine renders each target template (claude, codex, cursor, gemini, copilot) | `tests/test_compile_templates.py` | unit |
| 4 | TemplateEngine renders peripheral.md.j2 | `tests/test_compile_templates.py` | unit |
| 5 | User override in .rag/templates/ takes precedence over built-in | `tests/test_compile_templates.py` | unit |
| 6 | is_overridden() returns correct status | `tests/test_compile_templates.py` | unit |
| 7 | list_templates() returns all available templates | `tests/test_compile_templates.py` | unit |
| 8 | render_target() maps target name to correct template | `tests/test_compile_templates.py` | unit |
| 9 | render_target() raises CompileError for unknown target | `tests/test_compile_templates.py` | unit |
| 10 | Templates handle empty optional fields gracefully | `tests/test_compile_templates.py` | unit |
| 11 | Templates handle empty peripheral/errata/document lists | `tests/test_compile_templates.py` | unit |
| 12 | get_target_info() returns correct TargetInfo for each target | `tests/test_compile_templates.py` | unit |
| 13 | supported_targets() returns all 5 targets | `tests/test_compile_templates.py` | unit |
| 14 | CompileContext.from_config() factory method works correctly | `tests/test_compile_templates.py` | unit |
| 15 | Target templates contain correct markers (BEGIN/END HWCC CONTEXT) | `tests/test_compile_templates.py` | unit |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Create TemplateEngine with no project root | Loads only built-in templates | automated |
| 2 | Create TemplateEngine with project root that has .rag/templates/ | Loads both user + built-in templates | automated |
| 3 | Render claude.md.j2 with sample context | Output contains hardware info, markers, MCP hints | automated |
| 4 | Place custom claude.md.j2 in .rag/templates/ | Custom template used instead of built-in | automated |
| 5 | Render with minimal context (empty optional fields) | No errors, empty sections omitted | automated |
| 6 | All rendered target outputs contain correct BEGIN/END markers | Marker strings present in output | automated |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/compile/__init__.py` | modify | Add exports for TemplateEngine, CompileContext, TargetInfo, etc. |

## Files to Create
| File | Purpose |
|------|---------|
| `src/hwcc/compile/context.py` | Template context dataclasses |
| `src/hwcc/compile/templates.py` | TemplateEngine class |
| `src/hwcc/templates/hot_context.md.j2` | Hot context template |
| `src/hwcc/templates/peripheral.md.j2` | Per-peripheral context template |
| `src/hwcc/templates/claude.md.j2` | CLAUDE.md hardware section |
| `src/hwcc/templates/agents.md.j2` | AGENTS.md (Codex) template |
| `src/hwcc/templates/gemini.md.j2` | .gemini/GEMINI.md template |
| `src/hwcc/templates/cursor.mdc.j2` | .cursor/rules/hardware.mdc |
| `src/hwcc/templates/copilot.md.j2` | .github/copilot-instructions.md |
| `tests/test_compile_templates.py` | Template engine + rendering tests |

## Exit Criteria
```
□ TemplateEngine loads built-in templates from src/hwcc/templates/
□ TemplateEngine supports user overrides from .rag/templates/
□ All 7 template files render correctly with sample context data
□ Empty/optional fields handled gracefully (no errors, clean output)
□ Target registry maps all 5 targets to correct templates and paths
□ All 15+ tests pass
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched (no compile/hot.py, no compile/output.py, no CLI changes)
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/test_compile_templates.py -v`
- [ ] Full suite passes: `pytest tests/`
- [ ] Lint passes: `ruff check src/hwcc/compile/ tests/test_compile_templates.py`
- [ ] Format correct: `ruff format --check src/hwcc/compile/ tests/test_compile_templates.py`
- [ ] Types correct: `mypy src/hwcc/compile/`
- [ ] No unintended side effects in: existing compile/base.py, existing tests, CLI

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None (template system already documented in §6.1 and §8)
- [ ] **PLAN.md:** Mark task 2.3 as `[x]` after completion

---

> **Last Updated:** 2026-02-28

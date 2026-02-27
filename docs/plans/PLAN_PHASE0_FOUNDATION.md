# Plan: Phase 0 — Foundation

## Scope Declaration
- **Type:** feature
- **Single Concern:** Create the project skeleton, core data structures, config/manifest systems, CLI skeleton, and `hwcc init` command
- **Phase:** Phase 0 (Foundation) from PLAN.md
- **Complexity:** Medium
- **Risk:** Low

### Concern Separation Rule
This change is ONLY about: project scaffolding, core data structures, CLI skeleton, and `hwcc init`
This change is NOT about: parsers, chunking, embedding, ChromaDB, MCP server, compile, or any Phase 1+ work

## Problem Statement
**What:** Bootstrap the hwcc Python project from zero to a working `hwcc init` + `hwcc status` + `hwcc version` CLI
**Why:** No source code exists yet. Everything depends on this foundation being solid — config loading, manifest tracking, CLI framework, project initialization.
**Success:** `pip install -e ".[dev]"` works, `hwcc init --chip STM32F407` creates `.rag/` with valid config, `hwcc status` shows empty project, all tests pass.

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `pyproject.toml` | create | Package metadata, dependencies, entry points, dev tools config |
| `src/hwcc/__init__.py` | create | Package version, `__all__` |
| `src/hwcc/cli.py` | create | Typer app with all command stubs |
| `src/hwcc/config.py` | create | `HwccConfig` dataclass, TOML load/save, defaults |
| `src/hwcc/manifest.py` | create | `Manifest` + `DocumentEntry` dataclasses, JSON load/save, hashing |
| `src/hwcc/project.py` | create | `ProjectManager` — init, status, directory structure |
| `src/hwcc/exceptions.py` | create | `HwccError` hierarchy |
| `tests/conftest.py` | create | Shared fixtures (tmp project dirs, sample configs) |
| `tests/test_config.py` | create | Config load/save/defaults tests |
| `tests/test_manifest.py` | create | Manifest CRUD + hashing tests |
| `tests/test_cli.py` | create | CLI invocation tests (init, status, version) |
| `tests/test_project.py` | create | Project init, directory creation tests |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `HwccConfig` | `cli.py`, `project.py` | `tomli`, `tomli_w` |
| `Manifest` | `cli.py`, `project.py` | `json`, `hashlib` |
| `ProjectManager` | `cli.py` | `HwccConfig`, `Manifest`, `pathlib` |
| `cli.py` (Typer) | Entry point (`hwcc` command) | `ProjectManager`, `HwccConfig`, `Manifest` |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Foundation (this) | None (first stage) | All future phases depend on config, manifest, CLI, exceptions |

## NON-GOALS (Explicitly Out of Scope)
- [ ] Ingest parsers (PDF, SVD, markdown, DTS) — Phase 1
- [ ] Chunking engine — Phase 1
- [ ] Embedding engine — Phase 1
- [ ] ChromaDB storage — Phase 1
- [ ] Compile/output generation — Phase 2
- [ ] MCP server — Phase 3
- [ ] Plugin system — Phase 5
- [ ] Jinja2 templates — Phase 2
- [ ] `hwcc add` / `hwcc remove` implementation — Phase 1
- [ ] `hwcc compile` / `hwcc search` / `hwcc mcp` implementation — Phase 2-3

## Technical Approach

### Architecture Decisions

**Config system**: `@dataclass` with nested sections matching `config.toml` structure. TOML loaded with `tomli`, saved with `tomli_w`. All fields have sensible defaults so `hwcc init` works with zero user input.

**Manifest system**: `@dataclass` with `DocumentEntry` list. JSON serialization. SHA-256 hashing for change detection. Methods: `add_document()`, `remove_document()`, `is_changed()`, `get_document()`.

**CLI**: Single `cli.py` with Typer app. Stub all commands from TECH_SPEC §7 but only implement `init`, `status`, `version` in Phase 0. Stubs raise `NotImplementedError` with helpful message.

**Project manager**: Handles `.rag/` directory creation, config generation, SVD auto-detection, existing CLAUDE.md detection.

**Exception hierarchy**: `HwccError` base → `ConfigError`, `ManifestError`, `ProjectError`. Keep it minimal — add parser/embed/store errors in their respective phases.

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Create pyproject.toml | `pyproject.toml` | Package metadata, dependencies (typer, rich, tomli, tomli-w), dev deps (pytest, ruff, mypy), entry point `hwcc = "hwcc.cli:app"`, ruff+mypy config |
| 2 | Create package init | `src/hwcc/__init__.py` | `__version__ = "0.1.0"`, `__all__` |
| 3 | Create exception hierarchy | `src/hwcc/exceptions.py` | `HwccError`, `ConfigError`, `ManifestError`, `ProjectError` |
| 4 | Create config system | `src/hwcc/config.py` | `ProjectConfig`, `HardwareConfig`, `SoftwareConfig`, `ConventionsConfig`, `EmbeddingConfig`, `LlmConfig`, `OutputConfig`, `HwccConfig` dataclasses. `load_config(path)`, `save_config(config, path)`, `default_config()` functions. |
| 5 | Create manifest system | `src/hwcc/manifest.py` | `DocumentEntry` (frozen dataclass), `Manifest` dataclass. `load_manifest(path)`, `save_manifest(manifest, path)`, `compute_hash(path)` functions. CRUD methods on Manifest. |
| 6 | Create project manager | `src/hwcc/project.py` | `ProjectManager` class. Methods: `init(chip, rtos)` — creates `.rag/` structure + default config; `status()` — returns project status dict; `find_project_root()` — walk up to find `.rag/`; auto-detect SVD files; detect existing CLAUDE.md. |
| 7 | Create CLI skeleton | `src/hwcc/cli.py` | Typer app with commands: `init`, `add`, `remove`, `status`, `compile`, `context`, `mcp`, `search`, `config_cmd`, `version`. Only `init`, `status`, `version` are implemented; others are stubs. Rich console output. |
| 8 | Create empty package inits | `src/hwcc/ingest/__init__.py`, `src/hwcc/chunk/__init__.py`, `src/hwcc/embed/__init__.py`, `src/hwcc/store/__init__.py`, `src/hwcc/compile/__init__.py`, `src/hwcc/serve/__init__.py` | Empty `__init__.py` with `__all__ = []` for future subpackages |
| 9 | Write tests | `tests/conftest.py`, `tests/test_config.py`, `tests/test_manifest.py`, `tests/test_project.py`, `tests/test_cli.py` | Full test suite for all Phase 0 code |
| 10 | Verify | — | `pip install -e ".[dev]"`, `pytest`, `ruff check`, `mypy`, manual `hwcc init` test |

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Default config has all sections with sensible values | `tests/test_config.py` | unit |
| 2 | Config round-trips through TOML (save → load → compare) | `tests/test_config.py` | unit |
| 3 | Config loads partial TOML (missing sections get defaults) | `tests/test_config.py` | unit |
| 4 | Config rejects invalid values (negative clock, empty MCU) | `tests/test_config.py` | unit |
| 5 | Empty manifest creates valid JSON | `tests/test_manifest.py` | unit |
| 6 | Manifest add_document creates entry with hash | `tests/test_manifest.py` | unit |
| 7 | Manifest remove_document deletes entry | `tests/test_manifest.py` | unit |
| 8 | Manifest is_changed detects modified file | `tests/test_manifest.py` | unit |
| 9 | Manifest get_document returns correct entry | `tests/test_manifest.py` | unit |
| 10 | Manifest round-trips through JSON (save → load → compare) | `tests/test_manifest.py` | unit |
| 11 | compute_hash returns consistent SHA-256 | `tests/test_manifest.py` | unit |
| 12 | ProjectManager.init creates .rag/ directory structure | `tests/test_project.py` | unit |
| 13 | ProjectManager.init creates valid config.toml | `tests/test_project.py` | unit |
| 14 | ProjectManager.init creates empty manifest.json | `tests/test_project.py` | unit |
| 15 | ProjectManager.init with --chip sets hardware.mcu | `tests/test_project.py` | unit |
| 16 | ProjectManager.init detects existing .rag/ (idempotent) | `tests/test_project.py` | unit |
| 17 | ProjectManager.status shows document count 0 for fresh project | `tests/test_project.py` | unit |
| 18 | ProjectManager.find_project_root walks up directories | `tests/test_project.py` | unit |
| 19 | `hwcc version` prints version string | `tests/test_cli.py` | integration |
| 20 | `hwcc init` creates .rag/ in cwd | `tests/test_cli.py` | integration |
| 21 | `hwcc init --chip STM32F407` sets chip in config | `tests/test_cli.py` | integration |
| 22 | `hwcc status` works on initialized project | `tests/test_cli.py` | integration |
| 23 | `hwcc status` fails gracefully on uninitialized project | `tests/test_cli.py` | integration |
| 24 | Stub commands print "not yet implemented" message | `tests/test_cli.py` | integration |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | `pip install -e ".[dev]"` | Installs without errors, `hwcc` command available | manual |
| 2 | `hwcc version` | Prints `hwcc 0.1.0` | automated |
| 3 | `hwcc init --chip STM32F407` in empty dir | Creates `.rag/config.toml` with `mcu = "STM32F407"`, `.rag/manifest.json`, subdirs | automated |
| 4 | `hwcc status` after init | Shows "0 documents, 0 chunks" | automated |
| 5 | `hwcc add foo.pdf` | Prints "Not yet implemented" | automated |
| 6 | `pytest tests/` | All tests pass | automated |
| 7 | `ruff check src/ tests/` | No lint errors | manual |
| 8 | `mypy src/hwcc/` | No type errors | manual |

## Files to Create
| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, deps, tool config |
| `src/hwcc/__init__.py` | Package root, version |
| `src/hwcc/exceptions.py` | Custom exception hierarchy |
| `src/hwcc/config.py` | Config dataclasses + TOML I/O |
| `src/hwcc/manifest.py` | Manifest dataclass + JSON I/O + hashing |
| `src/hwcc/project.py` | Project init/status/discovery |
| `src/hwcc/cli.py` | Typer CLI with all commands |
| `src/hwcc/ingest/__init__.py` | Empty subpackage placeholder |
| `src/hwcc/chunk/__init__.py` | Empty subpackage placeholder |
| `src/hwcc/embed/__init__.py` | Empty subpackage placeholder |
| `src/hwcc/store/__init__.py` | Empty subpackage placeholder |
| `src/hwcc/compile/__init__.py` | Empty subpackage placeholder |
| `src/hwcc/serve/__init__.py` | Empty subpackage placeholder |
| `src/hwcc/templates/.gitkeep` | Template directory placeholder |
| `tests/__init__.py` | Test package |
| `tests/conftest.py` | Shared fixtures |
| `tests/test_config.py` | Config tests |
| `tests/test_manifest.py` | Manifest tests |
| `tests/test_project.py` | Project manager tests |
| `tests/test_cli.py` | CLI integration tests |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `.gitignore` | create | Standard Python gitignore + `.rag/index/` |

## Exit Criteria
```
□ pyproject.toml valid, installable with pip install -e ".[dev]"
□ hwcc version prints 0.1.0
□ hwcc init --chip STM32F407 creates correct .rag/ structure
□ hwcc status shows empty project state
□ Config round-trips through TOML correctly
□ Manifest tracks documents with SHA-256 hashes
□ All 24 tests pass
□ ruff check passes with zero errors
□ mypy passes with zero errors
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/ -v`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Format correct: `ruff format --check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] Manual test: `cd /tmp/test-project && hwcc init --chip STM32F407 && hwcc status && hwcc version`
- [ ] No unintended side effects in: TECH_SPEC.md, PLAN.md, CLAUDE.md (documentation untouched)

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None
- [ ] **PLAN.md:** Mark tasks 0.1–0.5 as complete after execution

---

> **Last Updated:** 2026-02-27

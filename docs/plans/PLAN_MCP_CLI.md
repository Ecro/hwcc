# Plan: Task 3.2 — `hwcc mcp` CLI Command

## Scope Declaration
- **Type:** feature
- **Single Concern:** Wire the `hwcc mcp` CLI command to start the MCP server and generate config snippets
- **Phase:** v0.3 (MCP Server)
- **Complexity:** Low
- **Risk:** Low (additive — replaces a stub, no existing behavior changes)

## Problem Statement
**What:** Replace the `hwcc mcp` stub with a working command that starts the MCP server and optionally generates config snippets for AI coding tools.

**Why:** Task 3.1 shipped the MCP server module with `run_server()` entry point, but there's no CLI way to start it. Users need `hwcc mcp` to launch the server and `hwcc mcp --config` to get the JSON config they paste into their tool's MCP settings.

**Success:** `hwcc mcp` starts the stdio MCP server. `hwcc mcp --config` prints a ready-to-paste JSON config snippet for Claude Code.

---

## Design

### Command Behavior

```
hwcc mcp              # Start MCP server (stdio, blocking)
hwcc mcp --config     # Print MCP config snippet to stdout
```

### `hwcc mcp` (default — start server)

1. Check `mcp` package is importable; if not, print helpful install message and exit
2. Verify project is initialized (`ProjectManager.is_initialized`)
3. Call `run_server()` from `hwcc.serve` — blocks on stdio

### `hwcc mcp --config`

Prints a JSON snippet the user can paste into `.claude/mcp.json` or equivalent:

```json
{
  "mcpServers": {
    "hwcc": {
      "command": "hwcc",
      "args": ["mcp"]
    }
  }
}
```

Does NOT write files — just prints to stdout. The user decides where to paste it.

### Optional Dependency Handling

The `mcp` package is optional (`pip install hwcc[mcp]`). The CLI command must handle the missing import gracefully:

```python
try:
    from hwcc.serve import run_server
except ImportError:
    console.print("[red]MCP support requires extra dependencies.[/red]")
    console.print("Install with: [bold]pip install hwcc\\[mcp][/bold]")
    raise typer.Exit(code=1)
```

The `--config` flag does NOT need the `mcp` package (it just prints JSON), so it should work even without the extra.

---

## Impact Analysis

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/cli.py` | modify | Replace `mcp` stub (lines 598-606) with working implementation |

### Dependency Chain

| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `mcp()` CLI command | Typer CLI dispatch | `hwcc.serve.run_server()`, `ProjectManager` |

### Pipeline Impact

None — this is a thin CLI wrapper over already-complete server code.

## NON-GOALS (Do NOT Touch)

- [ ] `src/hwcc/serve/server.py` — already complete, just consume `run_server()`
- [ ] `src/hwcc/serve/__init__.py` — already exports `run_server`
- [ ] `pyproject.toml` — `mcp` optional dep already configured
- [ ] `src/hwcc/exceptions.py` — `McpError` already exists
- [ ] HTTP/SSE transport — stdio only
- [ ] Auto-writing config files — just print to stdout

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Replace `mcp` command stub | `src/hwcc/cli.py` | Remove `_not_implemented("mcp")`, add `--config` flag, import guard for `mcp` package, call `run_server()` |
| 2 | Unhide the command | `src/hwcc/cli.py` | Remove `hidden=True` from `@app.command()` decorator |
| 3 | Write CLI tests | `tests/test_cli.py` | Test `--config` output, missing-project error, missing-mcp-package error |
| 4 | Verify | — | Full test suite, lint, types |

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/cli.py` | modify | Replace mcp stub with working command |
| `tests/test_cli.py` | modify | Add TestMcp class with CLI tests |

## Files to Create

None.

## Test Plan

### Unit Tests

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | `hwcc mcp --config` prints valid JSON with mcpServers key | `tests/test_cli.py` | unit |
| 2 | `hwcc mcp --config` works without mcp package installed | `tests/test_cli.py` | unit |
| 3 | `hwcc mcp` on uninitialized project exits with error | `tests/test_cli.py` | unit |
| 4 | `hwcc mcp` when mcp package missing shows install hint | `tests/test_cli.py` | unit |
| 5 | `hwcc mcp --help` shows command help (not hidden) | `tests/test_cli.py` | unit |

### Acceptance Criteria (Testable)

| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | `hwcc mcp --config` | Prints valid JSON config snippet | automated |
| 2 | `hwcc mcp` without project | "No hwcc project found" error, exit 1 | automated |
| 3 | `hwcc mcp` without mcp package | "pip install hwcc[mcp]" hint, exit 1 | automated |
| 4 | `hwcc --help` | Shows `mcp` in command list | automated |

## Exit Criteria
```
- `hwcc mcp --config` prints valid JSON config snippet
- `hwcc mcp` starts server when project exists and mcp installed
- Graceful error when mcp package not installed
- Graceful error when project not initialized
- Command visible in `hwcc --help`
- All tests pass (existing + new)
- ruff + mypy clean
- No changes to NON-GOAL files
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/test_cli.py tests/test_serve_mcp.py -v`
- [ ] Full suite: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No unintended side effects in: serve module, pyproject.toml

## Document Updates Needed
- [ ] **PLAN.md:** Check off task 3.2, mark v0.3 as shipped
- [ ] **TECH_SPEC.md:** Update MCP section status if needed

---

> **Last Updated:** 2026-03-02

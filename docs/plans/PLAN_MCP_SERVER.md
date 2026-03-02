# Plan: Task 3.1 — MCP Server Implementation

## Scope Declaration
- **Type:** feature
- **Single Concern:** Implement MCP server exposing hwcc's vector store as 3 tools via stdio transport
- **Phase:** v0.3 (MCP Server)
- **Complexity:** Medium
- **Risk:** Low (additive feature — new module, no existing code modified except CLI stub + dependencies)

## Problem Statement
**What:** Expose hwcc's indexed hardware documentation via the Model Context Protocol, so AI coding agents (Claude Code, Cursor, VS Code Copilot) can query registers, search docs, and get peripheral context on-demand during coding sessions.

**Why:** Static context files (CLAUDE.md) are limited to ~120 lines of hot context. A project with 7,000+ chunks has far more information than fits in a static file. MCP enables on-demand retrieval — the LLM only pulls what it needs, when it needs it. Research shows server-side filtering reduces token usage by 65% vs dumping full docs into context.

**Success:** `hwcc mcp` starts a stdio MCP server. Claude Code can call `hw_search("SPI DMA")`, `hw_registers("SPI1")`, and `hw_context("SPI1")` and get relevant hardware documentation back.

---

## Design

### Architecture

The MCP server is a thin layer over existing hwcc infrastructure:

```
MCP Client (Claude Code)
    │ stdio (JSON-RPC)
    ▼
FastMCP Server (src/hwcc/serve/server.py)
    │
    ├── hw_search()  ──▶ SearchEngine (existing)
    ├── hw_registers() ──▶ BaseStore.get_chunks() (existing)
    └── hw_context()  ──▶ Read pre-compiled .rag/context/peripherals/*.md
    │
    ├── Resource: hw://peripherals  ──▶ list peripheral names from store
    └── Resource: hw://documents    ──▶ list indexed documents from manifest
```

### SDK Choice: FastMCP (High-Level API)

Use `mcp.server.fastmcp.FastMCP` — decorator-based, handles serialization, tool schemas auto-generated from type hints. No need for the low-level `Server` API.

### Lifespan Pattern

Use FastMCP's lifespan context manager to initialize heavy resources (ChromaDB store, embedder) once at server startup, not per-request:

```python
@asynccontextmanager
async def hwcc_lifespan(server: FastMCP) -> AsyncIterator[HwccContext]:
    # Find project root, load config, init store + embedder
    yield HwccContext(config=config, store=store, search_engine=engine, project_root=root)
```

### Tools

#### 1. `hw_search(query, chip?, doc_type?, peripheral?, top_k?)`

Free-text semantic search across all indexed hardware docs. Wraps `SearchEngine.search()`.

Returns: Markdown-formatted results with metadata (chip, doc_type, peripheral, score).

#### 2. `hw_registers(peripheral, register?, chip?)`

Get register maps from SVD data. Uses `store.get_chunks(where={"peripheral": ..., "content_type": "register_description"})`.

Returns: Markdown register documentation with reset values and field descriptions.

#### 3. `hw_context(peripheral, chip?)`

Get full pre-compiled peripheral context (the same content as `.rag/context/peripherals/<name>.md`). Falls back to store query if pre-compiled file doesn't exist.

Returns: Complete peripheral context (register map + usage patterns + API reference + errata).

### Resources

#### `hw://peripherals`
List all peripherals found in the store with chip and register count.

#### `hw://documents`
List all indexed documents from the manifest with doc_type, chip, and chunk count.

### Transport

stdio only (for v0.3). This is what Claude Code, Cursor, and VS Code use. HTTP/SSE can be added later if needed.

### Dependency: `mcp` package

Add `mcp>=1.0` as an **optional dependency** (`pip install hwcc[mcp]`). This avoids bloating the core install for users who only want static output. The `hwcc mcp` CLI command checks for the import and gives a helpful error if not installed.

---

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Add MCP optional dependency | `pyproject.toml` | Add `mcp>=1.0` to `[project.optional-dependencies]` |
| 2 | Add McpError exception | `src/hwcc/exceptions.py` | New exception for MCP server errors |
| 3 | Create MCP server module | `src/hwcc/serve/server.py` | FastMCP server with lifespan, 3 tools, 2 resources |
| 4 | Update serve __init__ | `src/hwcc/serve/__init__.py` | Export server entry point |
| 5 | Write tests | `tests/test_serve_mcp.py` | Unit tests with mocked store/embedder |
| 6 | Verify | — | Full test suite, lint, types |

**Note:** Task 3.2 (`hwcc mcp` CLI command wiring) is a separate task and NOT in scope here. The server module exposes a `run_server()` entry point that 3.2 will call.

## Files to Create

| File | Purpose |
|------|---------|
| `src/hwcc/serve/server.py` | MCP server: FastMCP instance, lifespan, tools, resources |
| `tests/test_serve_mcp.py` | Unit tests for all tools and resources |

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `pyproject.toml` | modify | Add `mcp` optional dependency |
| `src/hwcc/exceptions.py` | modify | Add `McpError` |
| `src/hwcc/serve/__init__.py` | modify | Export `run_server` |

## NON-GOALS (Do NOT Touch)

- [ ] `src/hwcc/cli.py` — CLI wiring is task 3.2, not 3.1
- [ ] `src/hwcc/search.py` — already complete, just consume it
- [ ] `src/hwcc/store/` — already complete, just consume it
- [ ] `src/hwcc/embed/` — already complete, just consume it
- [ ] `src/hwcc/compile/` — read pre-compiled files, don't modify compile logic
- [ ] Templates — MCP serves data, not rendered templates
- [ ] HTTP/SSE transport — stdio only for v0.3

## Test Plan

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | hw_search returns formatted results | `tests/test_serve_mcp.py` | unit |
| 2 | hw_search with filters passes them through | `tests/test_serve_mcp.py` | unit |
| 3 | hw_search with empty store returns no results message | `tests/test_serve_mcp.py` | unit |
| 4 | hw_registers returns register chunks for peripheral | `tests/test_serve_mcp.py` | unit |
| 5 | hw_registers with specific register filters | `tests/test_serve_mcp.py` | unit |
| 6 | hw_registers with no results returns message | `tests/test_serve_mcp.py` | unit |
| 7 | hw_context reads pre-compiled peripheral file | `tests/test_serve_mcp.py` | unit |
| 8 | hw_context falls back to store when no file exists | `tests/test_serve_mcp.py` | unit |
| 9 | hw_context with unknown peripheral returns message | `tests/test_serve_mcp.py` | unit |
| 10 | peripherals resource lists peripherals from store | `tests/test_serve_mcp.py` | unit |
| 11 | documents resource lists docs from manifest | `tests/test_serve_mcp.py` | unit |
| 12 | lifespan initializes and cleans up resources | `tests/test_serve_mcp.py` | unit |
| 13 | run_server entry point is importable | `tests/test_serve_mcp.py` | unit |
| 14 | McpError in exception hierarchy | `tests/test_serve_mcp.py` | unit |

## Exit Criteria
```
□ MCP server module created with 3 tools + 2 resources
□ run_server() entry point exposed from hwcc.serve
□ All tests pass (existing + new)
□ mcp is optional dependency (hwcc[mcp])
□ No changes to NON-GOAL files
□ ruff + mypy clean
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] Manual test: install hwcc[mcp], run server, test with MCP client
- [ ] No unintended side effects in: CLI, compile, store, embed modules

## Document Updates Needed
- [ ] **TECH_SPEC.md:** Update §5.2 MCP Server status from [PLANNED] to [DONE]
- [ ] **PLAN.md:** Check off task 3.1

---

> **Last Updated:** 2026-03-02

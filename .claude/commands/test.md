# /test - Run Tests

Run pytest with various modes for different testing needs.

## Recommended Model

```
model: opus
thinking: default
```

**Note:** Slash commands inherit the session's model. Ultrathink not needed for running tests.

## Usage

```
/test
/test $ARGUMENTS
```

## Arguments

`$ARGUMENTS` - Test mode or specific test target

## Test Modes

| Mode | Command | Description |
|------|---------|-------------|
| `quick` | `/test` or `/test quick` | ruff + mypy + pytest (fast) |
| `unit` | `/test unit` | All unit tests verbose |
| `verbose` | `/test verbose` | pytest with verbose output |
| `coverage` | `/test coverage` | pytest with coverage report |
| `full` | `/test full` | lint + format + types + tests + coverage |
| `lint` | `/test lint` | ruff check only |
| `format` | `/test format` | ruff format check only |
| `type` | `/test type` | mypy only |
| `single` | `/test single test_config` | Single test file |
| `match` | `/test match "test_table"` | Pattern match tests |

## Implementation

### Quick Mode (Default)

```bash
# Check Python version
python3 --version  # Must be 3.11+

# Lint
ruff check src/ tests/

# Type check
mypy src/hwcc/

# Tests (fast, stop on first failure)
pytest tests/ --tb=short -q -x
```

**Report:**

| Check | Result |
|-------|--------|
| Python Version | {version} |
| Ruff Lint | PASS / FAIL |
| Mypy Types | PASS / FAIL |
| Pytest | {passed}/{total} PASS / FAIL |

### Unit Mode

```bash
pytest tests/ -v
```

**Expected test suites** (once implemented):
- `test_config.py` - Configuration loading and validation
- `test_manifest.py` - Manifest operations and SHA-256 hashing
- `test_ingest_pdf.py` - PDF text and table extraction
- `test_ingest_svd.py` - SVD register map parsing
- `test_chunking.py` - Token-aware text splitting
- `test_embedding.py` - Embedding provider interface
- `test_store.py` - ChromaDB operations
- `test_compile.py` - Context compilation
- `test_mcp_server.py` - MCP server tools

### Coverage Mode

```bash
# Terminal report with missing lines
pytest --cov=hwcc --cov-report=term-missing tests/

# Also generate HTML report
pytest --cov=hwcc --cov-report=html tests/
```

### Full Mode

Run everything in order:

```bash
# 1. Lint
ruff check src/ tests/

# 2. Format check
ruff format --check src/ tests/

# 3. Type check
mypy src/hwcc/

# 4. Full test suite with coverage
pytest --cov=hwcc --cov-report=term-missing tests/ -v
```

**Report:**

| Check | Result |
|-------|--------|
| Ruff Lint | PASS / FAIL |
| Ruff Format | PASS / FAIL |
| Mypy Types | PASS / FAIL |
| Pytest | {passed}/{total} |
| Coverage | {percent}% |

### Single File Mode

```bash
# Run a specific test file
pytest tests/test_config.py -v
```

### Pattern Match Mode

```bash
# Run tests matching a pattern
pytest -k "test_table" -v
```

## Test Infrastructure

| Component | Tool |
|-----------|------|
| Framework | pytest |
| Coverage | pytest-cov |
| Shared fixtures | `conftest.py` |
| Mocking | `unittest.mock`, `pytest-mock` |
| Temp files | `tmp_path` fixture |
| Sample data | `tests/fixtures/` |

## Test Report Format

```markdown
## Test Results

### Summary
| Metric | Value |
|--------|-------|
| Mode | {quick/unit/coverage/full} |
| Total Tests | {N} |
| Passed | {N} |
| Failed | {N} |
| Skipped | {N} |
| Coverage | {percent}% (if applicable) |

### Failures (if any)
| Test | File | Error |
|------|------|-------|
| `{test_name}` | `{file}:{line}` | {brief error} |

### Next Steps
{if all pass}
- Continue with current task
- `/review` if ready for review

{if failures}
- Fix failing tests before proceeding
- Check test_name for assertion details
```

## Notes

- Quick mode is the default — use it frequently during development
- Coverage mode generates HTML report in `htmlcov/`
- Full mode is recommended before `/wrapup`
- Single file mode is useful during TDD (RED-GREEN-REFACTOR)

# Plan: Phase 1 — SVD Parser (P0 Differentiator)

## Scope Declaration

- **Type:** feature
- **Single Concern:** Implement CMSIS-SVD file parser that converts `.svd` files into structured markdown register maps
- **Phase:** 1 (Document Ingestion), Task 1.2
- **Complexity:** Medium
- **Risk:** Low (deterministic parsing, well-defined input format, mature library)

## Problem Statement

**What:** Implement an SVD parser (`SvdParser`) that reads CMSIS-SVD files and produces structured markdown containing peripheral register maps with bit-level field detail.

**Why:** This is the #1 differentiator (P0 gap G2). RespCode benchmarks prove 3/4 LLMs get register addresses wrong without proper context. SVD parsing is 100% deterministic — no LLM needed, highest reliability. Zero open-source competition exists for SVD → AI context compilation.

**Success:** `SvdParser.parse("STM32F407.svd", config)` returns a `ParseResult` with clean markdown register maps that include peripheral names, base addresses, register offsets, field bit positions, access types, reset values, and descriptions.

## Impact Analysis

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/ingest/svd.py` | create | New `SvdParser(BaseParser)` implementation |
| `src/hwcc/ingest/__init__.py` | modify | Export `SvdParser` in `__all__` |
| `pyproject.toml` | modify | Add `cmsis-svd>=0.4` to dependencies |
| `tests/test_ingest_svd.py` | create | Unit tests for SVD parser |
| `tests/fixtures/sample.svd` | create | Minimal SVD fixture file for testing |

### Dependency Chain

| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `SvdParser.parse()` | `Pipeline.process()` | `cmsis_svd.SVDParser`, `ParseResult()` |
| `SvdParser.supported_extensions()` | `BaseParser.can_parse()`, `Pipeline` | — |

### Pipeline Impact

| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| **Parse** (this stage) | None — entry point | Produces `ParseResult` consumed by chunker |
| Chunk | — | Chunker will receive markdown with register tables; table-aware chunking will need to preserve tables (future Phase 1.5 work) |
| Embed/Store | — | Standard text embedding — no special handling needed |

## NON-GOALS (Explicitly Out of Scope)

- [ ] **Chunking engine** — Save for task 1.5 (separate concern)
- [ ] **File type detection** — Save for task 1.1 (separate concern)
- [ ] **PDF parser** — Save for task 1.3 (separate concern)
- [ ] **`hwcc add` CLI command** — Save for task 1.8 (separate concern)
- [ ] **Registry registration** — No auto-registration; parser is instantiated directly by pipeline composer
- [ ] **Jinja2 templates** — Phase 2 concern; this parser outputs markdown directly
- [ ] **Errata cross-referencing** — Phase 2, task 2.2
- [ ] **MCP server tools** (hw_registers) — Phase 3
- [ ] **Refactoring existing code** — No changes to types.py, pipeline.py, or base classes

## Technical Approach

### Option A: cmsis-svd library with markdown generation (Recommended)

Use the `cmsis-svd` PyPI library (`SVDParser.for_xml_file()`) to parse SVD XML, then generate structured markdown from the parsed data model.

**Pros:**
- Mature library (handles derivedFrom resolution, clusters, register arrays)
- Lightweight pure-Python dependency
- Handles SVD schema validation
- Pre-indexed vendor SVDs available (bonus for future)

**Cons:**
- Known limitation: some cluster handling edge cases
- Library API uses `Optional` extensively — need null checks

### cmsis-svd Library API (Key Classes)

```python
from cmsis_svd.parser import SVDParser

parser = SVDParser.for_xml_file("STM32F407.svd")
device = parser.get_device()  # SVDDevice

# SVDDevice: name, description, cpu, peripherals[]
# SVDPeripheral: name, base_address, description, registers[], interrupts[], derived_from
# SVDRegister: name, address_offset, size, access, reset_value, description, fields[]
# SVDField: name, bit_offset, bit_width, access, description
# SVDAccessType: READ_ONLY, WRITE_ONLY, READ_WRITE, WRITE_ONCE, READ_WRITE_ONCE
```

### Markdown Output Format

```markdown
# STM32F407 Register Map

**Device:** STM32F407
**Description:** STM32F407 microcontroller
**CPU:** CM4, revision r1p0

---

## SPI1

**Base Address:** `0x40013000`
**Description:** Serial peripheral interface

### Registers

| Register | Offset | Size | Access | Reset | Description |
|----------|--------|------|--------|-------|-------------|
| CR1 | 0x00 | 32 | RW | 0x0000 | Control register 1 |
| CR2 | 0x04 | 32 | RW | 0x0000 | Control register 2 |

### CR1 Fields

| Field | Bits | Access | Reset | Description |
|-------|------|--------|-------|-------------|
| BIDIMODE | [15:15] | RW | 0 | Bidirectional data mode enable |
| DFF | [11:11] | RW | 0 | Data frame format |
| SSM | [9:9] | RW | 0 | Software slave management |
| SPE | [6:6] | RW | 0 | SPI enable |
| BR | [5:3] | RW | 0 | Baud rate control |
| MSTR | [2:2] | RW | 0 | Master selection |
| CPOL | [1:1] | RW | 0 | Clock polarity |
| CPHA | [0:0] | RW | 0 | Clock phase |

---
```

### Access Type Abbreviations

| SVD Access Type | Abbreviation |
|----------------|--------------|
| `READ_ONLY` | RO |
| `WRITE_ONLY` | WO |
| `READ_WRITE` | RW |
| `WRITE_ONCE` | W1 |
| `READ_WRITE_ONCE` | RW1 |
| (None/inherit) | — |

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Add cmsis-svd dependency | `pyproject.toml` | Add `cmsis-svd>=0.4` to core dependencies |
| 2 | Create SVD test fixture | `tests/fixtures/sample.svd` | Minimal valid SVD with 2 peripherals, registers, fields, derived peripheral |
| 3 | Implement SvdParser class | `src/hwcc/ingest/svd.py` | Full parser: parse SVD → structured markdown `ParseResult` |
| 4 | Update ingest __init__.py | `src/hwcc/ingest/__init__.py` | Export `SvdParser` in `__all__` |
| 5 | Write unit tests | `tests/test_ingest_svd.py` | Comprehensive tests covering all scenarios |
| 6 | Verify with ruff + mypy | — | Lint and type-check all new code |

### Step 3 Detail: SvdParser Implementation

```
SvdParser(BaseParser)
├── parse(path, config) → ParseResult
│   ├── Load SVD via SVDParser.for_xml_file(str(path))
│   ├── Get device via parser.get_device()
│   ├── Generate device header markdown
│   ├── For each peripheral:
│   │   ├── Generate peripheral section header (name, base_address, description)
│   │   ├── Generate register table (name, offset, size, access, reset, description)
│   │   └── For each register with fields:
│   │       └── Generate field detail table (name, bits, access, reset, description)
│   ├── Build metadata tuple (peripheral_count, register_count, cpu_name)
│   └── Return ParseResult(doc_id, content, doc_type="svd", title, chip, metadata)
│
├── supported_extensions() → frozenset({".svd"})
│
└── Internal helpers:
    ├── _format_access(access: SVDAccessType | None) → str
    ├── _format_hex(value: int | None, width: int) → str
    ├── _format_bit_range(offset: int, width: int) → str
    ├── _render_device_header(device: SVDDevice) → str
    ├── _render_peripheral(peripheral: SVDPeripheral) → str
    ├── _render_register_table(registers: list) → str
    └── _render_field_table(register_name: str, fields: list) → str
```

### Key Design Decisions

1. **One ParseResult per SVD file** — the entire device maps to a single ParseResult. Chunking (splitting by peripheral) is the chunker's job, not the parser's.

2. **Markdown output, not structured data** — `ParseResult.content` is markdown. This aligns with the pipeline contract: parsers produce clean markdown, chunkers split it.

3. **Chip name from SVD device name** — `ParseResult.chip` is extracted from `device.name`. The `--chip` CLI override happens at the pipeline level, not in the parser.

4. **Derived peripherals expanded** — cmsis-svd resolves `derivedFrom` automatically during preprocessing. The parser just iterates the final list.

5. **Register arrays expanded** — `SVDPeripheralArray` and `SVDRegisterArray` contain expanded lists. We iterate the expanded form.

6. **Clusters flattened** — Clusters contain nested registers. We recursively extract all registers from clusters and present them in the same table as top-level registers, with a section path prefix.

7. **Peripherals sorted alphabetically** — consistent output regardless of SVD ordering.

8. **Registers sorted by offset** — natural hardware layout order.

9. **Fields sorted by bit position (descending)** — MSB first, matching convention in datasheets.

## Test Plan

### Unit Tests

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Parse minimal SVD file — verify ParseResult fields | `tests/test_ingest_svd.py` | unit |
| 2 | Verify peripheral count and names extracted | `tests/test_ingest_svd.py` | unit |
| 3 | Verify register table format (offset, size, access, reset) | `tests/test_ingest_svd.py` | unit |
| 4 | Verify field detail table (bit range, access, description) | `tests/test_ingest_svd.py` | unit |
| 5 | Verify derived peripheral is included with correct base address | `tests/test_ingest_svd.py` | unit |
| 6 | Verify doc_type is "svd" | `tests/test_ingest_svd.py` | unit |
| 7 | Verify chip name extracted from device name | `tests/test_ingest_svd.py` | unit |
| 8 | Verify metadata contains peripheral and register counts | `tests/test_ingest_svd.py` | unit |
| 9 | Verify supported_extensions returns frozenset({".svd"}) | `tests/test_ingest_svd.py` | unit |
| 10 | Verify can_parse works for .svd and rejects .pdf | `tests/test_ingest_svd.py` | unit |
| 11 | Verify ParseError raised for invalid/corrupt SVD file | `tests/test_ingest_svd.py` | unit |
| 12 | Verify ParseError raised for nonexistent file | `tests/test_ingest_svd.py` | unit |
| 13 | Verify access type formatting (RO, WO, RW, W1, RW1) | `tests/test_ingest_svd.py` | unit |
| 14 | Verify hex formatting of addresses and reset values | `tests/test_ingest_svd.py` | unit |
| 15 | Verify registers sorted by offset, fields sorted by bit position desc | `tests/test_ingest_svd.py` | unit |
| 16 | Verify peripheral with no registers produces section with note | `tests/test_ingest_svd.py` | unit |
| 17 | Verify register with no fields omits field table | `tests/test_ingest_svd.py` | unit |

### Test Fixture: `tests/fixtures/sample.svd`

Minimal valid CMSIS-SVD file containing:
- Device: `TESTCHIP` with CPU info
- Peripheral `TIMER0` at `0x40000000`:
  - Register `CR` at offset `0x00` (32-bit, RW, reset `0x00000000`):
    - Field `EN` [0:0] RW — Timer enable
    - Field `MODE` [2:1] RW — Timer mode
    - Field `IRQ_EN` [3:3] RW — Interrupt enable
  - Register `SR` at offset `0x04` (32-bit, RO, reset `0x00000001`):
    - Field `BUSY` [0:0] RO — Timer busy
    - Field `OVF` [1:1] RO — Overflow flag
  - Register `CNT` at offset `0x08` (32-bit, RO, reset `0x00000000`, no fields)
- Peripheral `TIMER1` derived from `TIMER0` at `0x40001000`
  - Same registers/fields (inherited via derivedFrom)

### Acceptance Criteria (Testable)

| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Parse valid SVD file | Returns ParseResult with markdown content | automated |
| 2 | Markdown contains register table with correct columns | Table headers: Register, Offset, Size, Access, Reset, Description | automated |
| 3 | Markdown contains field detail tables | Table headers: Field, Bits, Access, Reset, Description | automated |
| 4 | Invalid SVD raises ParseError | `ParseError` with descriptive message | automated |
| 5 | ParseResult.chip matches device name | `chip == "TESTCHIP"` | automated |
| 6 | Peripheral base addresses formatted as hex | `0x40000000` format | automated |
| 7 | All tests pass | `pytest tests/test_ingest_svd.py` exits 0 | automated |
| 8 | Type checks pass | `mypy src/hwcc/ingest/svd.py` exits 0 | automated |
| 9 | Lint passes | `ruff check src/hwcc/ingest/svd.py` exits 0 | automated |

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `pyproject.toml` | modify | Add `cmsis-svd>=0.4` dependency |
| `src/hwcc/ingest/__init__.py` | modify | Add `SvdParser` to `__all__` and imports |

## Files to Create

| File | Purpose |
|------|---------|
| `src/hwcc/ingest/svd.py` | SVD parser implementation |
| `tests/test_ingest_svd.py` | Unit tests for SVD parser |
| `tests/fixtures/sample.svd` | Minimal SVD fixture file |

## Exit Criteria

```
[x] SvdParser implements BaseParser ABC correctly
[x] Parse produces structured markdown with register maps
[x] Derived peripherals handled (via cmsis-svd library)
[x] All 17 unit tests pass
[x] mypy strict mode passes
[x] ruff check passes
[x] All changes within declared scope (no scope creep)
[x] NON-GOALS remain untouched
```

## Verification Strategy

- [ ] Tests pass: `pytest tests/test_ingest_svd.py -v`
- [ ] Full suite passes: `pytest tests/`
- [ ] Lint passes: `ruff check src/hwcc/ingest/svd.py tests/test_ingest_svd.py`
- [ ] Format correct: `ruff format --check src/hwcc/ingest/svd.py tests/test_ingest_svd.py`
- [ ] Types correct: `mypy src/hwcc/ingest/svd.py`
- [ ] No unintended side effects in: types.py, pipeline.py, base.py, registry.py, existing tests

## Document Updates Needed

- [ ] **TECH_SPEC.md:** None (SVD parser already specified)
- [ ] **PLAN.md:** Mark task 1.2 as complete when done

---

> **Last Updated:** 2026-02-28

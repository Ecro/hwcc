# Plan: EmbedGenius-Inspired Improvements (6 Items, Phase-Aligned)

> **Source**: [EmbedGenius: Towards Automated Software Development for Generic Embedded IoT Systems](https://arxiv.org/html/2412.09058v2)
> **Date**: 2026-02-28
> **Status**: Draft — pending review

---

## Scope Declaration

- **Type:** feature (6 improvements across multiple phases)
- **Single Concern:** Integrate hardware-domain intelligence inspired by EmbedGenius into hwcc's existing pipeline stages
- **Phases:** 1 (Chunk), 2 (Compile/Config), 3 (Serve), 5 (C/H Parser)
- **Complexity:** Medium-High (aggregate)
- **Risk:** Low-Medium (each improvement is independently deployable)

### Concern Separation Rule

This plan covers 6 independent improvements. Each MUST be implemented as a separate commit/PR. They share a research origin but are architecturally independent — no improvement depends on another (though #3 enhances #4).

### NOT About

- Post-generation validation loops (EmbedGenius's compile/flash loop) — explicitly out of scope per PLAN.md
- Library dependency resolution — too platform-specific
- Any changes to the ABC contracts (`BaseParser`, `BaseChunker`, `BaseEmbedder`, `BaseStore`, `BaseCompiler` signatures) — these are stable

---

## Overview: 6 Improvements by Phase

| # | Improvement | Phase | Effort | Impact | Files Changed |
|---|-------------|-------|--------|--------|---------------|
| 1 | Pin/connection config | **Phase 2** (Config/Compile) | Low | High | 3 files + 2 templates |
| 2 | Relevance-scored peripheral detail selection | **Phase 2** (Compile) | Medium | High | 2 files + 1 test |
| 3 | Richer hardware content type taxonomy | **Phase 1** (Chunk) | Medium | Medium | 2 files + 1 test |
| 4 | Usage pattern extraction for peripheral context | **Phase 2** (Compile) | Medium | High | 2 files + 1 template + 1 test |
| 5 | Structured API table in C/H parser | **Phase 5** (task 5.4) | High | High | New parser + template + tests |
| 6 | Query decomposition for MCP search | **Phase 3** (Serve) | Medium | Medium | New module + tests |

---

## Improvement #1: Pin/Connection Config

**Phase:** 2 (Config/Compile)
**Effort:** Low | **Impact:** High
**Inspired by:** EmbedGenius requires pin assignments as structured data to prevent LLMs from guessing pin numbers.

### Problem

`HardwareConfig` (`src/hwcc/config.py:56-65`) has MCU specs but no pin mapping. The hot context and peripheral templates cannot tell the AI "SPI1_SCK is on PA5." Pin guessing is one of the most common embedded code errors.

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/config.py` | modify | Add `PinsConfig` dataclass with `mappings: dict[str, str]`, wire into `HwccConfig` |
| `src/hwcc/compile/hot.py` | modify | Pass pin mappings to `CompileContext`, render in template |
| `src/hwcc/compile/peripheral.py` | modify | Filter pin mappings per peripheral, pass to template |
| `src/hwcc/templates/hot_context.md.j2` | modify | Add "Pin Assignments" section |
| `src/hwcc/templates/peripheral.md.j2` | modify | Add "Pin Assignments" section filtered to peripheral |

### Technical Approach

Add a new config section:

```python
@dataclass
class PinsConfig:
    """[pins] section -- board-level pin assignments."""
    mappings: dict[str, str] = field(default_factory=dict)
```

Config TOML:
```toml
[pins]
spi1_sck = "PA5"
spi1_mosi = "PA7"
spi1_miso = "PA6"
spi1_nss = "PA4"
led_status = "PC13"
uart_debug_tx = "PA2"
uart_debug_rx = "PA3"
```

Pin filtering for peripheral context: match pin names starting with peripheral name (case-insensitive). E.g., for peripheral "SPI1", match "spi1_sck", "spi1_mosi", etc.

### NON-GOALS

- [ ] Auto-discovery of pins from SVD alternate function tables — save for Phase 5 (STM32 plugin)
- [ ] Pin conflict detection — future feature
- [ ] Schematic parsing — out of scope entirely

### Test Plan

| # | Test | File | Type |
|---|------|------|------|
| 1 | `PinsConfig` loads from TOML with arbitrary key-value pairs | `tests/test_config.py` | unit |
| 2 | Empty `[pins]` section produces empty dict | `tests/test_config.py` | unit |
| 3 | Hot context template renders pin assignments section | `tests/test_compile_hot_context.py` | unit |
| 4 | Peripheral template renders filtered pin assignments | `tests/test_compile_peripheral.py` | unit |
| 5 | Config round-trip preserves pin mappings | `tests/test_config.py` | unit |

### Implementation Steps

| # | Task | File(s) |
|---|------|---------|
| 1 | Add `PinsConfig` dataclass | `config.py` |
| 2 | Add `pins: PinsConfig` field to `HwccConfig` | `config.py` |
| 3 | Update `_load_section` to handle dict-style config | `config.py` |
| 4 | Add `pin_assignments` to `CompileContext` | `compile/hot.py` |
| 5 | Render pin section in `hot_context.md.j2` | `templates/hot_context.md.j2` |
| 6 | Filter pins per peripheral in `PeripheralContextCompiler` | `compile/peripheral.py` |
| 7 | Render filtered pins in `peripheral.md.j2` | `templates/peripheral.md.j2` |
| 8 | Add tests | `tests/test_config.py`, `tests/test_compile_hot_context.py`, `tests/test_compile_peripheral.py` |

---

## Improvement #2: Relevance-Scored Peripheral Detail Selection

**Phase:** 2 (Compile)
**Effort:** Medium | **Impact:** High
**Inspired by:** EmbedGenius's "Selective Memory Pick-up" using TF-IDF similarity — reduced token consumption by 26.2%.

### Problem

`PeripheralContextCompiler._gather_peripheral_details()` (`compile/peripheral.py:201-237`) selects non-SVD chunks by matching peripheral names in `section_path`, then takes the **first 5 by chunk_id order** — a purely positional selection with no relevance scoring.

```python
relevant.sort(key=lambda c: c.chunk_id)  # sorted by ID, not relevance
relevant = relevant[:_MAX_DETAIL_CHUNKS]  # takes first 5 regardless of quality
```

This misses relevant content where the peripheral name doesn't appear in the heading hierarchy, and includes low-value chunks just because they appear early in the document.

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/compile/peripheral.py` | modify | `_gather_peripheral_details()` uses store.search() with embedder for semantic ranking |
| `src/hwcc/compile/base.py` | modify | Add optional `embedder` parameter to `BaseCompiler.compile()` |
| `tests/test_compile_peripheral.py` | modify | Add tests for relevance-scored selection |

### Technical Approach

**Option A: Embedding-based search (Recommended)**

Change `_gather_peripheral_details()` to use `store.search()` with an embedded query of the peripheral name + context keywords. The `BaseStore.search()` at `store/chroma.py:103-188` already supports `where` metadata filters.

The `compile()` method signature change: Add `embedder: BaseEmbedder | None = None` as an optional parameter. When provided, use embedding search. When `None`, fall back to the existing section_path matching (backward compatibility).

```python
def _gather_peripheral_details(
    self,
    peripheral_name: str,
    store: BaseStore,
    embedder: BaseEmbedder | None = None,
    chip: str = "",
) -> str:
    if embedder is not None:
        # Semantic search: embed peripheral name, search with metadata filter
        query = f"{peripheral_name} configuration usage registers"
        query_embedding = embedder.embed_query(query)
        where = {"doc_type": {"$ne": "svd"}}
        if chip:
            where["chip"] = chip
        results = store.search(query_embedding, k=_MAX_DETAIL_CHUNKS, where=where)
        # Filter results by relevance score threshold
        relevant_chunks = [r.chunk for r in results if r.score > 0.3]
        if relevant_chunks:
            return "\n\n---\n\n".join(c.content for c in relevant_chunks).strip()

    # Fallback: original section_path matching
    # ... existing code ...
```

**Option B: TF-IDF local scoring (No embedder dependency)**

Compute TF-IDF similarity between the peripheral name and each non-SVD chunk's content using scikit-learn or a simple custom implementation. No embedder needed, but adds a dependency or custom code.

**Decision: Option A** — leverages existing infrastructure (store.search + embedder.embed_query), no new dependencies, naturally extends the compile stage.

### Dependency Chain

| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `_gather_peripheral_details()` | `PeripheralContextCompiler.compile()` | `store.search()`, `embedder.embed_query()` |
| `BaseCompiler.compile()` signature | `Pipeline`, CLI `hwcc compile` | All concrete compilers |

### Pipeline Impact

| Pipeline Stage | Upstream | Downstream |
|---------------|----------|------------|
| Compile | Embed stage (now used at compile time too) | Output files (better peripheral context quality) |

### NON-GOALS

- [ ] Changing `BaseCompiler` ABC signature — keep `embedder` as a concrete implementation detail, not in the ABC
- [ ] Re-embedding at compile time — use pre-stored embeddings, only embed the query string
- [ ] Changing chunk storage format — no schema changes

### Test Plan

| # | Test | File | Type |
|---|------|------|------|
| 1 | With embedder: returns semantically relevant chunks | `tests/test_compile_peripheral.py` | unit |
| 2 | Without embedder: falls back to section_path matching (backward compat) | `tests/test_compile_peripheral.py` | unit |
| 3 | Respects `_MAX_DETAIL_CHUNKS` limit with embedding search | `tests/test_compile_peripheral.py` | unit |
| 4 | Filters by chip when multi-chip | `tests/test_compile_peripheral.py` | unit |
| 5 | Low-score results are filtered out (score threshold) | `tests/test_compile_peripheral.py` | unit |

### Implementation Steps

| # | Task | File(s) |
|---|------|---------|
| 1 | Add `embedder` parameter to `PeripheralContextCompiler.__init__()` | `compile/peripheral.py` |
| 2 | Refactor `_gather_peripheral_details()` to accept `store` + `embedder` | `compile/peripheral.py` |
| 3 | Implement embedding-based search path with fallback | `compile/peripheral.py` |
| 4 | Update `compile()` to pass `store` + `embedder` to detail gatherer | `compile/peripheral.py` |
| 5 | Update CLI/pipeline to pass embedder to PeripheralContextCompiler | Where compiler is instantiated |
| 6 | Add unit tests with mock embedder | `tests/test_compile_peripheral.py` |

---

## Improvement #3: Richer Hardware Content Type Taxonomy

**Phase:** 1 (Chunk)
**Effort:** Medium | **Impact:** Medium (foundational — enables #4)
**Inspired by:** EmbedGenius distinguishes API declarations, usage examples, and functionality descriptions as separate knowledge types.

### Problem

`MarkdownChunker._detect_content_type()` (`chunk/markdown.py:448-456`) only classifies chunks into 4 generic structural types: `code`, `table`, `section`, `prose`. There is no hardware-domain awareness.

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/chunk/markdown.py` | modify | Extend `_detect_content_type()` with hardware-domain patterns |
| `tests/test_chunk.py` | modify | Add tests for new content types |

### Technical Approach

Add pattern-based detection AFTER the existing structural checks. The structural types (`code`, `table`, `section`) remain as top-priority. Within `table` and `prose`, apply hardware-domain heuristics:

```python
import re

# Hardware domain patterns (compiled once at module level)
_REGISTER_RE = re.compile(
    r"(?:0x[0-9A-Fa-f]+|offset|reset\s*value|bit\s*\d+|access\s*type|read.only|write.only)",
    re.IGNORECASE,
)
_TIMING_RE = re.compile(
    r"(?:\d+\s*(?:ns|us|ms|MHz|kHz)|setup\s*time|hold\s*time|propagation\s*delay)",
    re.IGNORECASE,
)
_CONFIG_PROCEDURE_RE = re.compile(
    r"(?:initialization|configure|programming\s*sequence|enable\s*the|step\s*\d+[.:]|procedure)",
    re.IGNORECASE,
)
_ERRATA_RE = re.compile(
    r"(?:errata|erratum|silicon\s*bug|workaround|limitation|ES\d{4})",
    re.IGNORECASE,
)
_PIN_MAPPING_RE = re.compile(
    r"(?:alternate\s*function|AF\d+|GPIO|pin\s*assignment|remap)",
    re.IGNORECASE,
)
_ELECTRICAL_RE = re.compile(
    r"(?:V[_]?[A-Z]+|mA|uA|\d+\.\d+\s*V|current\s*consumption|power\s*supply)",
    re.IGNORECASE,
)

def _detect_content_type(self, text: str) -> str:
    """Detect the primary content type of a chunk."""
    # Structural types (highest priority)
    if _FENCE_RE.search(text):
        return "code"
    if _TABLE_SEP_RE.search(text):
        # Refine table type with domain knowledge
        if _REGISTER_RE.search(text):
            return "register_table"
        if _PIN_MAPPING_RE.search(text):
            return "pin_mapping"
        if _TIMING_RE.search(text):
            return "timing_spec"
        if _ELECTRICAL_RE.search(text):
            return "electrical_spec"
        return "table"
    if _HEADING_RE.search(text):
        return "section"

    # Domain-specific prose types
    if _ERRATA_RE.search(text):
        return "errata"
    if _CONFIG_PROCEDURE_RE.search(text):
        return "config_procedure"
    if _TIMING_RE.search(text):
        return "timing_spec"
    if _REGISTER_RE.search(text):
        return "register_description"

    return "prose"
```

**New content types (8 total, up from 4):**

| Content Type | Detection | Example Content |
|-------------|-----------|----------------|
| `register_table` | Table + register keywords | Register map tables with offset, reset value columns |
| `register_description` | Prose + register keywords | Text describing register fields and their functions |
| `timing_spec` | Timing unit keywords | Setup/hold times, clock frequencies |
| `config_procedure` | Configuration/init keywords | "Step 1: Enable the peripheral clock..." |
| `errata` | Errata/workaround keywords | "Silicon bug ES0182 §2.1.8: SPI CRC unreliable..." |
| `pin_mapping` | GPIO/AF keywords | Alternate function tables, pin assignment text |
| `electrical_spec` | Voltage/current keywords | Power supply requirements, current consumption |
| `code` / `table` / `section` / `prose` | (unchanged) | Generic structural types |

### Backward Compatibility

- `ChunkMetadata.content_type` (`types.py:31`) already accepts arbitrary strings — no schema change needed
- Existing chunks with old types (`code`, `table`, `section`, `prose`) remain valid
- Re-indexing (`hwcc add --force`) would assign new types to existing documents
- All downstream consumers that don't filter on content_type are unaffected

### NON-GOALS

- [ ] ML-based content classification — keep it regex/pattern based for determinism
- [ ] Changing ChunkMetadata schema — field already accepts strings
- [ ] Re-indexing existing stores — new types apply to new documents only

### Test Plan

| # | Test | File | Type |
|---|------|------|------|
| 1 | Register table detected from offset/bit columns | `tests/test_chunk.py` | unit |
| 2 | Timing spec detected from ns/MHz values | `tests/test_chunk.py` | unit |
| 3 | Config procedure detected from "initialization" / "step N" | `tests/test_chunk.py` | unit |
| 4 | Errata detected from "workaround" / "ES0182" | `tests/test_chunk.py` | unit |
| 5 | Pin mapping detected from "alternate function" / "AF" | `tests/test_chunk.py` | unit |
| 6 | Electrical spec detected from voltage/current | `tests/test_chunk.py` | unit |
| 7 | Existing types (code, table, section, prose) still detected correctly | `tests/test_chunk.py` | regression |
| 8 | Priority order: code > table subtypes > section > prose subtypes | `tests/test_chunk.py` | unit |

### Implementation Steps

| # | Task | File(s) |
|---|------|---------|
| 1 | Define compiled regex patterns at module level | `chunk/markdown.py` |
| 2 | Refactor `_detect_content_type()` with domain-specific sub-classification | `chunk/markdown.py` |
| 3 | Add unit tests for each new content type | `tests/test_chunk.py` |
| 4 | Add regression tests for existing types | `tests/test_chunk.py` |

---

## Improvement #4: Usage Pattern Extraction for Peripheral Context

**Phase:** 2 (Compile)
**Effort:** Medium | **Impact:** High
**Inspired by:** EmbedGenius's "Utility Table" — their 2nd biggest accuracy booster (+7.1% accuracy, +15% completion).

### Problem

`peripheral.md.j2` only has `register_map` and `peripheral_details` (raw chunks). There is no structured "usage patterns" section that bridges the gap between "here are the registers" and "here is how to use them."

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/compile/peripheral.py` | modify | Add `_extract_usage_patterns()` method |
| `src/hwcc/templates/peripheral.md.j2` | modify | Add "Usage Patterns" section |
| `tests/test_compile_peripheral.py` | modify | Add tests for usage pattern extraction |

### Technical Approach

Extract chunks whose:
1. `section_path` contains configuration/programming keywords (case-insensitive): "configuration", "programming", "initialization", "how to", "procedure", "setup", "enable"
2. OR `content_type` is `"config_procedure"` (from Improvement #3, if implemented)

Group by operation type (init, read, write, configure, interrupt) based on section_path keywords, and render as structured steps.

```python
_USAGE_KEYWORDS = {
    "initialization": "Initialization",
    "configuration": "Configuration",
    "programming": "Programming",
    "how to": "How To",
    "procedure": "Procedure",
    "setup": "Setup",
    "enable": "Enable",
    "interrupt": "Interrupt Configuration",
    "dma": "DMA Configuration",
}

def _extract_usage_patterns(
    self,
    peripheral_name: str,
    non_svd_chunks: list[Chunk],
    chip: str = "",
) -> list[dict[str, str]]:
    """Extract usage pattern chunks for a peripheral.

    Returns list of {"task": "...", "steps": "..."} dicts.
    """
    patterns = []
    for chunk in non_svd_chunks:
        if not self._section_path_mentions_peripheral(
            chunk.metadata.section_path, peripheral_name
        ):
            continue
        if chip and chunk.metadata.chip != chip:
            continue

        # Check content_type first (from Improvement #3)
        if chunk.metadata.content_type == "config_procedure":
            task = self._infer_task_name(chunk.metadata.section_path, peripheral_name)
            patterns.append({"task": task, "steps": chunk.content})
            continue

        # Fallback: check section_path for usage keywords
        path_lower = chunk.metadata.section_path.lower()
        for keyword, label in _USAGE_KEYWORDS.items():
            if keyword in path_lower:
                task = self._infer_task_name(chunk.metadata.section_path, peripheral_name)
                patterns.append({"task": task, "steps": chunk.content})
                break

    # Deduplicate and limit
    seen = set()
    unique = []
    for p in patterns:
        if p["task"] not in seen:
            seen.add(p["task"])
            unique.append(p)
    return unique[:_MAX_USAGE_PATTERNS]  # e.g., 5
```

Template addition to `peripheral.md.j2`:
```jinja2
{% if usage_patterns %}

## Usage Patterns

{% for pattern in usage_patterns %}
### {{ pattern.task }}

{{ pattern.steps }}

{% endfor %}
{% endif %}
```

### Dependency on Improvement #3

- **With #3 implemented**: Can use `content_type == "config_procedure"` for precise detection
- **Without #3**: Falls back to section_path keyword matching only — still functional, slightly less precise

### NON-GOALS

- [ ] LLM-based summarization of usage patterns — keep it deterministic
- [ ] Cross-document usage pattern merging — each chunk stands alone
- [ ] Modifying the Chunk or ChunkMetadata schema

### Test Plan

| # | Test | File | Type |
|---|------|------|------|
| 1 | Chunks with "Configuration" in section_path are extracted | `tests/test_compile_peripheral.py` | unit |
| 2 | Chunks with `content_type == "config_procedure"` are extracted | `tests/test_compile_peripheral.py` | unit |
| 3 | Deduplication by task name works | `tests/test_compile_peripheral.py` | unit |
| 4 | Limit to `_MAX_USAGE_PATTERNS` respected | `tests/test_compile_peripheral.py` | unit |
| 5 | Template renders usage patterns section | `tests/test_compile_peripheral.py` | integration |
| 6 | Empty patterns = no section rendered | `tests/test_compile_peripheral.py` | unit |

### Implementation Steps

| # | Task | File(s) |
|---|------|---------|
| 1 | Add `_USAGE_KEYWORDS` dict and `_MAX_USAGE_PATTERNS` constant | `compile/peripheral.py` |
| 2 | Implement `_extract_usage_patterns()` method | `compile/peripheral.py` |
| 3 | Implement `_infer_task_name()` helper | `compile/peripheral.py` |
| 4 | Call from `compile()`, pass `usage_patterns` to template | `compile/peripheral.py` |
| 5 | Add "Usage Patterns" section to `peripheral.md.j2` | `templates/peripheral.md.j2` |
| 6 | Add tests | `tests/test_compile_peripheral.py` |

---

## Improvement #5: Structured API Table in C/H Header Parser

**Phase:** 5 (task 5.4)
**Effort:** High | **Impact:** High
**Inspired by:** EmbedGenius extracts API tables from `.h` files with structure: (Function Name, Parameters, Return Value, Peripheral Association).

### Problem

The C/H header parser is planned (PLAN.md task 5.4) but not implemented. The plan says "tree-sitter based, extract function signatures, struct definitions, enums, macros" but doesn't specify output format.

### Design Guidance (for future implementation)

When implementing task 5.4, the parser output should be a **structured API table per peripheral**, not a raw AST dump:

```markdown
## SPI API Reference

| Function | Parameters | Returns | Description |
|----------|-----------|---------|-------------|
| HAL_SPI_Init | SPI_HandleTypeDef* | HAL_StatusTypeDef | Initialize SPI peripheral |
| HAL_SPI_Transmit | handle, data, size, timeout | HAL_StatusTypeDef | Blocking transmit |
| HAL_SPI_TransmitReceive_DMA | handle, txData, rxData, size | HAL_StatusTypeDef | DMA transmit+receive |
```

**Key design decisions:**

1. **Group functions by peripheral** — detectable from naming convention: `HAL_SPI_*`, `HAL_I2C_*`, `HAL_UART_*`. Set `ChunkMetadata.peripheral` accordingly.
2. **Set content_type to `"api_reference"`** — new content type for Improvement #3 taxonomy.
3. **Extract function signatures, not function bodies** — the AI needs the interface, not the implementation.
4. **Include typedefs and enums** — `SPI_HandleTypeDef`, `HAL_StatusTypeDef` are essential context.
5. **Parse both `.h` (declarations) and `.c` (Doxygen comments)** for complete API documentation.
6. **Include this structured table in peripheral context** — `PeripheralContextCompiler` should include API reference alongside register map.

### Files to Create (Future)

| File | Purpose |
|------|---------|
| `src/hwcc/ingest/c_header.py` | C/H parser using tree-sitter |
| `src/hwcc/templates/api_reference.md.j2` | API table template |
| `tests/test_ingest_c_header.py` | Parser tests |
| `tests/fixtures/sample_hal_spi.h` | Test fixture |

### NON-GOALS (for task 5.4)

- [ ] Full C compilation or preprocessing — parse surface syntax only
- [ ] Understanding function bodies — extract signatures and comments only
- [ ] Supporting arbitrary C codebases — focus on HAL/driver header patterns

### This Is Design Guidance Only

No implementation now. This section documents design decisions informed by EmbedGenius research to be applied when Phase 5 task 5.4 is implemented.

---

## Improvement #6: Query Decomposition for MCP Search

**Phase:** 3 (Serve)
**Effort:** Medium | **Impact:** Medium
**Inspired by:** EmbedGenius decomposes tasks into component-specific sub-functionalities before retrieval.

### Problem

The MCP server (Phase 3, not yet implemented) will expose `hw_search(query)` as a single-query vector search. Complex queries like "Record DHT11 temperature to SD card" span multiple peripherals but would be searched as a single monolithic query.

### Design Guidance (for future implementation)

When implementing `hw_search()` in the MCP server (PLAN.md task 3.1), add optional query decomposition:

```python
def _decompose_query(self, query: str, known_peripherals: list[str]) -> list[str]:
    """Decompose a complex query into per-peripheral sub-queries.

    Uses simple keyword extraction (no LLM needed):
    1. Scan query for known peripheral names from store metadata
    2. Identify operation types: init, read, write, configure, interrupt, DMA
    3. Generate sub-queries: "{peripheral} {operation}"
    """
    found_peripherals = [
        p for p in known_peripherals
        if p.lower() in query.lower()
    ]

    if len(found_peripherals) <= 1:
        return [query]  # Simple query, no decomposition needed

    operations = _extract_operations(query)  # ["read", "write", "configure", etc.]

    sub_queries = []
    for peripheral in found_peripherals:
        for op in (operations or ["usage"]):
            sub_queries.append(f"{peripheral} {op}")

    return sub_queries
```

**Implementation pattern:**
1. Get known peripheral names from `store.get_chunk_metadata()` (already cached in MCP server)
2. Extract peripheral mentions from query via case-insensitive substring matching
3. Extract operation keywords via regex
4. Run parallel sub-searches per peripheral+operation
5. Merge results with deduplication by `chunk_id`, keep highest-scoring instance

### Files to Create (Future)

| File | Purpose |
|------|---------|
| `src/hwcc/serve/decompose.py` | Query decomposition logic |
| `tests/test_serve_decompose.py` | Decomposition tests |

### This Is Design Guidance Only

No implementation now. This section documents design decisions for Phase 3 task 3.1.

---

## Implementation Order (Recommended)

```
Phase 1 work (Chunk stage):
  #3 Richer content type taxonomy  ← foundational, enables #4

Phase 2 work (Compile stage):
  #1 Pin/connection config         ← lowest effort, highest immediate impact
  #4 Usage pattern extraction      ← benefits from #3 but doesn't require it
  #2 Relevance-scored selection    ← medium effort, significant quality boost

Phase 3 work (Serve stage):
  #6 Query decomposition           ← design only now, implement with MCP server

Phase 5 work (Polish):
  #5 C/H parser API tables         ← design only now, implement with task 5.4
```

### Execution Plan

```
Batch 1 (can be done now):
  Step 1: #3 Content type taxonomy (chunk/markdown.py)
  Step 2: #1 Pin config (config.py + templates)
  Step 3: #4 Usage pattern extraction (compile/peripheral.py + template)
  Step 4: #2 Relevance-scored selection (compile/peripheral.py)

Batch 2 (deferred — design documented above):
  Step 5: #6 Query decomposition (when Phase 3 starts)
  Step 6: #5 C/H parser API tables (when Phase 5 task 5.4 starts)
```

---

## Impact Analysis

### Pipeline Impact

| Stage | What Changes | Upstream Effect | Downstream Effect |
|-------|-------------|-----------------|-------------------|
| **Chunk** (#3) | Content type detection enriched | None | Better metadata for compile-time filtering |
| **Config** (#1) | New `[pins]` section | None | Pin data available to compile and serve |
| **Compile** (#1,#2,#4) | Better peripheral context selection + new sections | Needs embedder (#2), needs chunk types (#4 benefits from #3) | Higher quality output files |
| **Serve** (#6) | Query decomposition | Needs known peripheral list | Better MCP search results |
| **Ingest** (#5) | New C/H parser | None | New chunks with API reference content type |

### Dependency Chain Between Improvements

```
#3 (content types) ──enhances──▶ #4 (usage patterns)
                                  │
#1 (pins config)                  │  (all others are independent)
#2 (relevance scoring)            │
#5 (C/H parser)                   │
#6 (query decomposition)          │
```

Only #3 → #4 has a dependency (and it's soft — #4 works without #3, just less precisely).

---

## Files to Modify (Batch 1 — Implementable Now)

| File | Improvement(s) | Change Type |
|------|---------------|-------------|
| `src/hwcc/config.py` | #1 | Add `PinsConfig` dataclass |
| `src/hwcc/chunk/markdown.py` | #3 | Extend `_detect_content_type()` |
| `src/hwcc/compile/peripheral.py` | #1, #2, #4 | Pin filtering, embedding search, usage patterns |
| `src/hwcc/compile/hot.py` | #1 | Pass pin data to template |
| `src/hwcc/templates/hot_context.md.j2` | #1 | Pin Assignments section |
| `src/hwcc/templates/peripheral.md.j2` | #1, #4 | Pin Assignments + Usage Patterns sections |
| `tests/test_config.py` | #1 | PinsConfig tests |
| `tests/test_chunk.py` | #3 | Content type tests |
| `tests/test_compile_peripheral.py` | #1, #2, #4 | Peripheral compiler tests |
| `tests/test_compile_hot_context.py` | #1 | Hot context pin rendering tests |

## Files to Create (Batch 1)

None — all changes are modifications to existing files.

## Files to Create (Batch 2 — Future)

| File | Improvement | Purpose |
|------|------------|---------|
| `src/hwcc/ingest/c_header.py` | #5 | C/H header parser |
| `src/hwcc/serve/decompose.py` | #6 | Query decomposition |
| `src/hwcc/templates/api_reference.md.j2` | #5 | API table template |
| `tests/test_ingest_c_header.py` | #5 | Parser tests |
| `tests/test_serve_decompose.py` | #6 | Decomposition tests |

---

## Exit Criteria

### Batch 1 (Implementable Now)

```
[ ] #3: _detect_content_type() returns 8+ content types with hardware domain awareness
[ ] #1: [pins] config section loads, renders in hot and peripheral templates
[ ] #4: Usage patterns extracted and rendered in peripheral context
[ ] #2: Peripheral detail selection uses embedding search when embedder available
[ ] All existing tests still pass (no regressions)
[ ] New tests cover all added behavior
[ ] ruff check passes
[ ] mypy passes
```

### Batch 2 (Design Only — Future Exit Criteria)

```
[ ] #5: C/H parser extracts structured API tables per peripheral (Phase 5)
[ ] #6: MCP hw_search decomposes multi-peripheral queries (Phase 3)
```

---

## Verification Strategy

- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] Manual test: `hwcc add sample.svd && hwcc compile` produces improved peripheral context
- [ ] No unintended side effects in: existing pipeline stages, ABC contracts, data contracts

## Document Updates Needed

- [ ] **TECH_SPEC.md**: Update §5.4 Metadata Per Chunk with new content types; add `[pins]` to §4 config.toml example
- [ ] **PLAN.md**: Add note to task 5.4 referencing EmbedGenius API table design; add note to task 3.1 referencing query decomposition design

---

> **Last Updated:** 2026-02-28

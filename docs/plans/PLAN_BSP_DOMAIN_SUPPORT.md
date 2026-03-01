# Plan: Embedded Linux / BSP Domain Support

> **Date**: 2026-03-01
> **Type**: Feature (architectural design + implementation roadmap)
> **Status**: Draft — awaiting review

---

## Scope Declaration

### Change Intent
- **Type:** feature
- **Single Concern:** Define how Embedded Linux / BSP features integrate into hwcc's existing architecture and implement the foundational pieces

### Concern Separation Rule
This change is ONLY about: Architectural design for BSP domain + first implementation (DTS parser + config extension + BSP templates)
This change is NOT about: MCP server tools, plugin system, Yocto/Buildroot-specific features, kernel source parsing

---

## Problem Statement

**What:** hwcc currently targets MCU/RTOS engineers exclusively. Embedded Linux / BSP engineers — who deal with SoC reference manuals, device trees, kernel configs, and board bring-up — have no equivalent tool. Embedder (the main competitor) also ignores this market entirely.

**Why:** This is an uncontested niche. BSP engineers face the same "AI hallucination" problem but with different document types:
- 3,000-6,000 page SoC reference manuals (i.MX8, RK3588, AM62x)
- Device tree sources that define board hardware topology
- Kernel device tree binding schemas that define valid DTS properties
- Vendor BSP documentation (often scattered and contradictory)

**Success:** A BSP engineer can run `hwcc init --soc imx8mp`, add their SoC reference manual and board device tree, and get AI-optimized context that prevents hallucinated device tree properties, wrong compatible strings, and incorrect register addresses.

---

## Strategic Context

### Why BSP is hwcc's Best Opportunity

| Factor | Explanation |
|--------|-------------|
| **Zero competition** | Embedder focuses on MCU/RTOS. No tool serves BSP engineers. |
| **Same core pain** | AI hallucinates DTS properties just like it hallucinates register addresses |
| **Pipeline fits** | parse→chunk→embed→store→compile works for DTS just like for SVD |
| **Tool-agnostic advantage** | BSP engineers already use Claude Code / VS Code terminal workflows |
| **Open-source alignment** | Linux kernel is open-source; BSP engineers strongly prefer open-source tools |

### What BSP Engineers Actually Need from AI Context

| Scenario | Documents Needed | What AI Gets Wrong |
|----------|-----------------|-------------------|
| Bring up SPI on custom board | SoC ref manual SPI chapter + DTS binding + example DTS | Wrong compatible string, wrong clock parent, wrong pin mux |
| Debug Ethernet PHY | PHY datasheet + SoC ENET chapter + DTS binding + MDIO config | Wrong MDIO address, wrong PHY mode (RGMII vs RMII) |
| Add device tree overlay | Sensor datasheet + SoC I2C chapter + DTS binding | Wrong I2C bus, wrong interrupt flags, missing pinctrl |
| Port BSP to new kernel | Kernel changelog + updated binding schemas | Uses deprecated DTS properties, old API names |

---

## Architectural Design: How BSP Features Fit hwcc

### Design Principle: Extend, Don't Fork

BSP support is NOT a separate mode or domain split. It is **additional document types flowing through the same pipeline** with **richer config and richer compilation output**.

```
EXISTING PIPELINE (unchanged):
  Path → BaseParser.parse() → ParseResult
       → BaseChunker.chunk() → list[Chunk]
       → BaseEmbedder.embed_chunks() → list[EmbeddedChunk]
       → BaseStore.add() → persisted
       → BaseCompiler.compile() → output files

BSP ADDS:
  New parsers:  DeviceTreeParser, KconfigParser (implement BaseParser)
  New config:   [hardware] gets soc/board/kernel fields
  New context:  CompileContext gets BSP fields
  New templates: hot_context.md.j2 gains BSP sections
  New output:   .rag/context/devicetree/ directory
```

### Why This Works

1. **Types are free-form strings** — `ChunkMetadata.doc_type`, `.chip`, `.content_type` are all `str`, not enum-constrained. New values (e.g., `doc_type="device_tree"`, `content_type="device_tree_node"`) work immediately.

2. **Detection already supports DTS** — `FileFormat.DEVICE_TREE` and `DocType.DEVICE_TREE` already exist in `detect.py`. Extension `.dts`/`.dtsi` already mapped. Only the parser implementation is missing.

3. **Config ignores unknown keys** — `_load_section()` filters unknown keys, so adding new fields to `HardwareConfig` is backwards-compatible.

4. **Templates use conditionals** — `hot_context.md.j2` already uses `{% if mcu %}` blocks. BSP blocks would use `{% if soc %}` — both can coexist.

5. **Peripheral is the JOIN point** — For both MCU and BSP, the peripheral (SPI, I2C, UART) is the central concept. BSP just adds more context per peripheral (DTS binding, DTS snippet, kernel driver reference).

---

## Detailed Changes

### 1. Config Extension (`src/hwcc/config.py`)

Add BSP-relevant fields to `HardwareConfig` and `SoftwareConfig`:

```python
@dataclass
class HardwareConfig:
    # Existing MCU fields (unchanged)
    mcu: str = ""
    mcu_family: str = ""
    architecture: str = ""
    clock_mhz: int = 0
    flash_kb: int = 0
    ram_kb: int = 0
    # NEW: BSP fields
    soc: str = ""              # e.g., "i.MX8M Plus"
    soc_family: str = ""       # e.g., "i.MX8"
    board: str = ""            # e.g., "EVK" or custom board name

@dataclass
class SoftwareConfig:
    # Existing fields (unchanged)
    rtos: str = ""
    hal: str = ""
    language: str = "C"
    build_system: str = ""
    # NEW: BSP fields
    kernel: str = ""           # e.g., "linux-6.6"
    bootloader: str = ""       # e.g., "U-Boot 2024.01"
    distro: str = ""           # e.g., "Yocto kirkstone" or "Buildroot 2024.02"
```

**Design rationale:**
- No separate `[bsp]` section — BSP is hardware + software, not a third thing
- `soc` vs `mcu` coexist — some projects use both (i.MX8 has Cortex-M core too)
- All new fields default to `""` — backwards compatible, MCU-only projects unaffected
- `hwcc init --soc imx8mp` populates `soc`, `hwcc init --chip STM32F407` populates `mcu` — both valid

### 2. Device Tree Parser (`src/hwcc/ingest/devicetree.py`)

New parser implementing `BaseParser`:

```
Input:  .dts or .dtsi file
Output: ParseResult with structured markdown content
```

**What the parser extracts:**
- Node hierarchy (tree structure)
- Compatible strings (which kernel driver binds)
- `reg` properties (memory-mapped addresses)
- `interrupts` properties
- `clocks` and `clock-names`
- `pinctrl-*` references
- `status` property (enabled/disabled)
- `#include` / `/include/` resolution (follow dtsi includes)
- Property values and their types

**Output format** (clean markdown, same as other parsers):

```markdown
# Device Tree: imx8mp-custom-board

## Node: / (root)
- compatible: "custom,board", "fsl,imx8mp"
- model: "Custom Board"

## Node: /soc/bus@30800000/spi@30820000
- **Compatible**: "fsl,imx8mp-ecspi", "fsl,imx51-ecspi"
- **Reg**: 0x30820000 0x10000
- **Interrupts**: GIC_SPI 31 IRQ_TYPE_LEVEL_HIGH
- **Clocks**: <&clk IMX8MP_CLK_ECSPI1_ROOT>
- **Clock-names**: "ipg", "per"
- **Status**: okay
- **Pinctrl**: pinctrl_ecspi1

### Child: spidev@0
- compatible: "rohm,dh2228fv"
- reg: <0>
- spi-max-frequency: <10000000>
```

**Chunking behavior:**
- Each peripheral node = one chunk (natural boundary)
- Child nodes stay with parent unless large
- Root-level metadata = summary chunk
- `content_type = "device_tree_node"`
- `peripheral` extracted from node name (e.g., `spi@30820000` → `SPI`)

**Implementation approach:**
- Pure Python parser (no external dependency) — DTS syntax is simple enough
- Handle `/dts-v1/;` pragma
- Handle `#include` and `/include/` by recording references (not full resolution — that requires the kernel tree)
- Handle `&label` phandle references
- Convert property values to human-readable format

**Why not use an external library:**
- `dtc` (device tree compiler) is a C tool — would need subprocess calls
- Python `fdt` library exists but is for DTB (binary), not DTS (source)
- DTS is a simple format — a focused parser is ~300-400 lines

### 3. CompileContext Extension (`src/hwcc/compile/context.py`)

Add BSP fields:

```python
@dataclass(frozen=True)
class CompileContext:
    # ... existing fields ...

    # NEW: BSP fields (from config)
    soc: str = ""
    soc_family: str = ""
    board: str = ""
    kernel: str = ""
    bootloader: str = ""
    distro: str = ""

    # NEW: BSP compiled data
    device_tree_nodes: tuple[DeviceTreeNodeSummary, ...] = ()
```

```python
@dataclass(frozen=True)
class DeviceTreeNodeSummary:
    """Summary of a device tree node for template rendering."""
    node_path: str           # e.g., "/soc/bus@30800000/spi@30820000"
    compatible: str          # e.g., "fsl,imx8mp-ecspi"
    peripheral: str          # e.g., "SPI"
    status: str              # "okay" | "disabled" | ""
    reg_address: str         # e.g., "0x30820000"
```

Update `from_config()` to populate BSP fields.

### 4. Template Updates

#### `hot_context.md.j2` — Add BSP section (conditional)

```jinja2
{# Existing MCU section stays #}
{% if mcu %}
## Target Hardware
- **MCU**: {{ mcu }}...
{% endif %}

{# NEW: BSP section, coexists with MCU section #}
{% if soc %}
## Target SoC
- **SoC**: {{ soc }}{% if architecture %} ({{ architecture }}){% endif %}

{% if soc_family %}- **Family**: {{ soc_family }}
{% endif %}
{% if board %}- **Board**: {{ board }}
{% endif %}
{% endif %}

{% if kernel or bootloader or distro %}
## Linux Stack
{% if kernel %}- **Kernel**: {{ kernel }}
{% endif %}
{% if bootloader %}- **Bootloader**: {{ bootloader }}
{% endif %}
{% if distro %}- **Distribution**: {{ distro }}
{% endif %}
{% endif %}

{# NEW: Device tree topology (when DTS has been indexed) #}
{% if device_tree_nodes %}
## Device Tree Topology
| Node | Compatible | Address | Status |
|------|-----------|---------|--------|
{% for node in device_tree_nodes %}
| {{ node.node_path }} | {{ node.compatible }} | {{ node.reg_address }} | {{ node.status }} |
{% endfor %}
{% endif %}
```

#### `peripheral.md.j2` — Enhance with DTS context

When a peripheral has both SVD/register data AND device tree data, the peripheral context page becomes a unified view:

```jinja2
# {{ peripheral_name }}

{% if register_map %}
## Register Map
{{ register_map }}
{% endif %}

{# NEW: Device tree section for this peripheral #}
{% if peripheral_dts_binding %}
## Device Tree Binding
{{ peripheral_dts_binding }}
{% endif %}

{% if peripheral_dts_snippet %}
## Device Tree Example
{{ peripheral_dts_snippet }}
{% endif %}

{% if peripheral_details %}
## Details
{{ peripheral_details }}
{% endif %}
```

### 5. Content Type Taxonomy Extension (`src/hwcc/chunk/markdown.py`)

Add BSP-specific content types to `CONTENT_TYPES`:

```python
CONTENT_TYPES: frozenset[str] = frozenset({
    # Existing
    "code", "register_table", "register_description", "timing_spec",
    "config_procedure", "errata", "pin_mapping", "electrical_spec",
    "api_reference", "table", "section", "prose",
    # NEW: BSP types
    "device_tree_node",      # Parsed DTS node
    "dt_binding",            # Device tree binding schema
    "kernel_config",         # Kconfig option
    "boot_config",           # U-Boot / bootloader config
})
```

### 6. Peripheral Discovery Enhancement (`src/hwcc/compile/peripheral.py`)

Currently `_discover_peripherals()` only finds peripherals from SVD chunks (pattern: `"DeviceName Register Map > PeripheralName"`). Add DTS-based discovery:

```python
def _discover_peripherals(self, store: BaseStore) -> list[str]:
    peripherals = set()

    # Existing: SVD-based discovery
    svd_chunks = store.get_chunk_metadata({"doc_type": "svd"})
    for meta in svd_chunks:
        if meta.peripheral:
            peripherals.add(meta.peripheral)

    # NEW: DTS-based discovery
    dts_chunks = store.get_chunk_metadata({"doc_type": "device_tree"})
    for meta in dts_chunks:
        if meta.peripheral:
            peripherals.add(meta.peripheral)

    return sorted(peripherals)
```

---

## NON-GOALS (Explicitly Out of Scope)

- [ ] **Kconfig parser** — Valuable but lower priority. Save for follow-up plan.
- [ ] **U-Boot config parser** — Save for follow-up.
- [ ] **Kernel source parsing (tree-sitter)** — Already planned as Phase 5, separate concern.
- [ ] **DT binding YAML parser** — Requires kernel source tree. Save for follow-up.
- [ ] **Full DTS include resolution** — Would need kernel tree access. Record references only.
- [ ] **MCP server tools (hw_devicetree, hw_binding)** — Phase 3, separate plan.
- [ ] **Plugin system changes** — Phase 5, separate plan.
- [ ] **Yocto/Buildroot-specific features** — Plugin territory.
- [ ] **TECH_SPEC.md competitive landscape update** — Separate docs change.
- [ ] **CLI changes (hwcc init --soc)** — Small follow-up after config lands.

---

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Extend HardwareConfig + SoftwareConfig | `src/hwcc/config.py` | Add `soc`, `soc_family`, `board`, `kernel`, `bootloader`, `distro` fields |
| 2 | Update CompileContext | `src/hwcc/compile/context.py` | Add BSP fields + `DeviceTreeNodeSummary` + update `from_config()` |
| 3 | Implement DeviceTreeParser | `src/hwcc/ingest/devicetree.py` | Parse .dts/.dtsi → ParseResult with structured markdown |
| 4 | Register DTS parser | `src/hwcc/ingest/__init__.py` | Add `"device_tree": DeviceTreeParser` to `_PARSER_MAP` |
| 5 | Add BSP content types | `src/hwcc/chunk/markdown.py` | Add `device_tree_node`, `dt_binding`, `kernel_config`, `boot_config` |
| 6 | Update hot_context template | `src/hwcc/templates/hot_context.md.j2` | Add conditional BSP sections (SoC, Linux stack, DT topology) |
| 7 | Update peripheral template | `src/hwcc/templates/peripheral.md.j2` | Add DTS binding + DTS snippet sections |
| 8 | Enhance peripheral discovery | `src/hwcc/compile/peripheral.py` | Add DTS-based peripheral discovery alongside SVD-based |
| 9 | Write tests | `tests/test_ingest_devicetree.py`, `tests/test_config.py` | Parser tests + config extension tests |
| 10 | Update TECH_SPEC.md | `TECH_SPEC.md` | Add BSP domain to architecture docs |

### Dependency Chain

```
Step 1 (config) ──→ Step 2 (context) ──→ Step 6, 7 (templates)
                                     └──→ Step 8 (peripheral discovery)

Step 3 (parser) ──→ Step 4 (registration)
               └──→ Step 5 (content types)
               └──→ Step 9 (tests)

Steps 1-2 and Steps 3-5 can be done in parallel.
Steps 6-8 depend on both.
Step 9 can start after Step 3.
Step 10 after everything.
```

---

## Test Plan

### Unit Tests

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | DTS parser extracts node hierarchy from simple DTS | `tests/test_ingest_devicetree.py` | unit |
| 2 | DTS parser extracts compatible strings | `tests/test_ingest_devicetree.py` | unit |
| 3 | DTS parser extracts reg addresses, interrupts, clocks | `tests/test_ingest_devicetree.py` | unit |
| 4 | DTS parser handles /include/ references | `tests/test_ingest_devicetree.py` | unit |
| 5 | DTS parser handles &label phandle syntax | `tests/test_ingest_devicetree.py` | unit |
| 6 | DTS parser handles empty/minimal DTS files | `tests/test_ingest_devicetree.py` | unit |
| 7 | DTS parser sets correct metadata (doc_type, peripheral, content_type) | `tests/test_ingest_devicetree.py` | unit |
| 8 | DTS parser returns valid ParseResult contract | `tests/test_ingest_devicetree.py` | unit |
| 9 | Config loads BSP fields (soc, kernel, board) from TOML | `tests/test_config.py` | unit |
| 10 | Config ignores BSP fields when absent (backwards compat) | `tests/test_config.py` | unit |
| 11 | CompileContext.from_config() populates BSP fields | `tests/test_compile_hot_context.py` | unit |
| 12 | Hot context template renders BSP section when soc is set | `tests/test_compile_templates.py` | unit |
| 13 | Hot context template skips BSP section when soc is empty | `tests/test_compile_templates.py` | unit |
| 14 | Peripheral discovery finds peripherals from DTS chunks | `tests/test_compile_peripheral.py` | unit |
| 15 | File detection returns DEVICE_TREE for .dts/.dtsi | `tests/test_detect.py` | unit (exists) |

### Integration Tests

| # | Test Description | File | Type |
|---|-----------------|------|------|
| 16 | Full pipeline: .dts → parse → chunk → embed → store | `tests/test_pipeline.py` | integration |
| 17 | Compile with mixed SVD + DTS produces unified peripheral context | `tests/test_compile_peripheral.py` | integration |

### Acceptance Criteria (Testable)

| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | `hwcc add board.dts` | DTS parsed, chunks stored with peripheral metadata | automated |
| 2 | `hwcc compile` with DTS indexed | hot.md includes Device Tree Topology table | automated |
| 3 | Config with `soc = "i.MX8M Plus"` | hot.md shows "Target SoC" section | automated |
| 4 | Project with both SVD + DTS | Peripheral context merges register map + DTS binding | automated |
| 5 | Old config (no BSP fields) | Loads without error, BSP fields default to empty | automated |

---

## Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/config.py` | modify | Add soc, soc_family, board, kernel, bootloader, distro fields |
| `src/hwcc/compile/context.py` | modify | Add BSP fields, DeviceTreeNodeSummary, update from_config() |
| `src/hwcc/compile/peripheral.py` | modify | Add DTS-based peripheral discovery |
| `src/hwcc/chunk/markdown.py` | modify | Add BSP content types to CONTENT_TYPES |
| `src/hwcc/ingest/__init__.py` | modify | Register DeviceTreeParser |
| `src/hwcc/templates/hot_context.md.j2` | modify | Add BSP sections |
| `src/hwcc/templates/peripheral.md.j2` | modify | Add DTS binding/snippet sections |

## Files to Create

| File | Purpose |
|------|---------|
| `src/hwcc/ingest/devicetree.py` | Device tree parser (.dts/.dtsi → ParseResult) |
| `tests/test_ingest_devicetree.py` | Device tree parser tests |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| DTS syntax edge cases | Medium | Low | Focus on common patterns first; add edge cases iteratively |
| Include resolution complexity | High | Medium | Don't resolve includes in v1 — just record references |
| Peripheral name extraction from DTS | Medium | Low | Use node name heuristics (e.g., `spi@addr` → SPI) |
| Config backwards compatibility | Low | High | All new fields default to ""; `_load_section` ignores unknowns |
| Template complexity | Low | Low | Use conditional blocks; test both MCU-only and BSP paths |

---

## Exit Criteria

```
[ ] DeviceTreeParser passes all unit tests
[ ] Config loads BSP fields correctly (new and old configs)
[ ] hot_context.md.j2 renders BSP sections when soc is configured
[ ] Peripheral context includes DTS data when available
[ ] All 569+ existing tests still pass (no regressions)
[ ] All changes within declared scope (no scope creep)
[ ] NON-GOALS remain untouched
```

## Verification Strategy

- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] Manual test: create a sample .dts file, run through pipeline
- [ ] No unintended side effects in: MCP server, plugin system, existing parsers

## Document Updates Needed

- [ ] **TECH_SPEC.md:** Add BSP domain to §2 (competitive landscape), §3 (architecture), §5 (ingestion)
- [ ] **PLAN.md:** Add BSP tasks, potentially as Phase 1.15+ or new sub-phase
- [ ] **CLAUDE.md:** Add DTS parser to pipeline stages table

---

## Future Work (separate plans)

These are explicitly deferred for follow-up plans:

| Feature | Why Deferred | Estimated Plan |
|---------|-------------|----------------|
| DT binding YAML parser | Requires kernel source tree access | PLAN_DT_BINDING_PARSER.md |
| Kconfig parser | Lower priority than DTS | PLAN_KCONFIG_PARSER.md |
| `hwcc init --soc` CLI | Depends on config extension landing | PLAN_BSP_CLI.md |
| BSP-specific MCP tools | Phase 3, depends on MCP server | PLAN_MCP_SERVER.md |
| Yocto/Buildroot plugins | Plugin system not yet implemented | PLAN_BSP_PLUGINS.md |
| Pre-built SoC catalog | Like SVD catalog but for SoC reference manuals | PLAN_SOC_CATALOG.md |

---

> **Last Updated:** 2026-03-01

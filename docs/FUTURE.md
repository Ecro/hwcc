# hwcc — Future Features

> Features with no timeline. Design and implement based on user feedback.
> Nothing here is cancelled — it's properly sequenced after the core ships.
> **See also**: `TECH_SPEC.md` (technical blueprint), `PLAN.md` (roadmap), `docs/STRATEGY.md` (market context)

---

## Plugin System

Extensible architecture for vendor-specific parsers and knowledge providers.

- `Plugin` base class with `parsers()` and `knowledge()` methods
- Python entry_points discovery (`hwcc.plugins` group)
- `hwcc plugins` command to list installed plugins
- Design deferred until core pipeline has users and third-party demand exists
- Current `ProviderRegistry` + `_PARSER_MAP` suffice for built-in providers

## Vendor Plugins

Official plugins for vendor-specific hardware knowledge:

| Plugin | Provides |
|--------|----------|
| `hwcc-plugin-stm32` | CubeMX .ioc parser, errata DB, pinout DB, bus/DMA/IRQ inference |
| `hwcc-plugin-esp32` | ESP-IDF config parser, ESP32 register maps |
| `hwcc-plugin-nrf` | nRF Connect SDK support, nRF SVD files |
| `hwcc-plugin-yocto` | BitBake recipe awareness, machine config parsing |
| `hwcc-plugin-zephyr` | Zephyr DTS + Kconfig, board overlay support |
| `hwcc-plugin-freertos` | FreeRTOSConfig.h parser, API reference |

## C/H Header Parser

tree-sitter based parser for structured API tables from C/H headers.

- Extract function signatures, structs, enums, macros
- Group by peripheral via naming convention (`HAL_SPI_*`)
- Output structured API tables: `(Function, Parameters, Returns, Description)`
- Set `content_type = "api_reference"` in chunk metadata
- Note: Claude Code can already read C headers directly — value is in structured summarization

## Universal Integration (Phase 4)

### Clipboard Mode
`hwcc context SPI --copy` — copy peripheral context to clipboard for pasting into any AI chat.

### Pipe Mode
`hwcc context SPI | llm-tool` — pipe context to any CLI tool. JSON/text/markdown output formats.

### hwcc augment
Read prompt from stdin, detect relevant peripherals, prepend context, output augmented prompt.
`echo "Write SPI driver" | hwcc augment | ollama run llama3.2`

### Watch Mode
`hwcc add --watch docs/` — background file watcher (watchdog library). Auto re-index on file change.

### Git Hooks
`hwcc install-hooks` — pre-commit auto-index, post-checkout verify index currency.

## Agent Skills & Slash Commands

### Slash Commands
Generate `.claude/commands/` files for hardware context access:
`/hw <peripheral>`, `/hw-search <query>`, `/hw-errata`, `/hw-pin`, `/hw-regs`, `/hw-status`

### Agent Skill
Generate `.claude/skills/hw-context/SKILL.md` — auto-trigger on driver/HAL file patterns. Instruct AI to use MCP tools before writing hardware code.

### Codex Skill
Generate `.agents/skills/hw-lookup/SKILL.md` for Codex skill discovery.

## Query Decomposition

Decompose complex multi-peripheral queries into per-peripheral sub-queries.
Extract peripheral names via regex matching. Run parallel sub-searches, merge with deduplication.
No LLM needed. Inspired by EmbedGenius task decomposition.

## Document Versioning

Add `document_version` and `silicon_revision` fields to manifest `DocumentEntry`.
Enable revision-aware context: "STM32F407 Rev Z (latest)".
Passive metadata storage — no interactive prompts.

## Hardware llms.txt Standard

Define a formal specification for hardware-optimized AI context format.
Seed via our Jinja2 templates as the de facto standard.
Consider publishing as a community specification.

## DT Binding YAML Parser

Parse kernel device tree binding schemas (`Documentation/devicetree/bindings/*.yaml`).
Validate DTS properties against binding schemas.
Prevent the #1 BSP error: wrong/invalid device tree properties.
Requires kernel source tree access — could ship curated subset of common bindings.

## Kconfig Parser

Parse `.config` / `defconfig` / `prj.conf` files.
Universal: works for Linux kernel, Zephyr, U-Boot.
Simple `CONFIG_FOO=y/n/value` format.
Note: Claude Code can read these directly — value is in summarization.

## Hardware Relationship Inference

Vendor-specific logic to infer bus membership (APB1/APB2/AHB), DMA channel mappings, IRQ assignments from SVD base addresses and vendor memory maps.
Belongs in vendor plugins, not core — wrong inference is worse than no inference.

# hwcc — Hardware Context Compiler

AI coding tools already read everything in your repo — source code, Makefiles, configs. But they can't read the vendor PDF on your desk. They hallucinate register addresses, get init sequences wrong, and miss errata.

**hwcc** fixes this. It transforms hardware documentation (datasheets, SVD files, reference manuals, device trees) into AI-optimized context files that any coding tool can consume — Claude Code, Codex, Cursor, Gemini CLI, or Copilot.

## The Problem

Ask any AI coding tool to configure SPI on an STM32 without vendor docs:

```
You: "Configure SPI1 on STM32F407 for 8-bit mode at 10.5 MHz"

AI: *guesses register addresses, invents bit positions, misses clock divider constraints*
```

The AI has no access to the 1,700-page reference manual or the SVD register definitions on your desk. It fills gaps with plausible-looking hallucinations.

## The Fix

```bash
hwcc init --chip STM32F407
hwcc add docs/STM32F407.svd
```

Now your AI coding tool sees real hardware context — register maps, bit-field positions, reset values, access types — injected directly into the files it already reads (`CLAUDE.md`, `.cursor/rules/`, etc.).

## Install

```bash
pipx install hwcc
```

Or with pip (in a virtual environment):

```bash
pip install hwcc
```

Requires Python 3.11+. No API keys needed — runs 100% locally by default.

## Quick Start

```bash
# Initialize in your project
cd my-firmware-project
hwcc init --chip STM32F407

# Add hardware documentation
hwcc add docs/STM32F407.svd
hwcc add docs/reference-manual.pdf
hwcc add docs/errata.pdf

# Check what's indexed
hwcc status
```

That's it. `hwcc add` automatically compiles context into your `CLAUDE.md` (and other tool files) with hardware register maps, peripheral details, and coding conventions — all between safe `<!-- BEGIN/END HWCC CONTEXT -->` markers that never touch your existing content.

## Using with Claude Code

After running `hwcc init` and `hwcc add`, Claude Code automatically picks up hardware context from `CLAUDE.md`. No extra configuration needed.

### Static Context (default)

The compiled context in `CLAUDE.md` is loaded every time Claude Code starts a session in your project:

```markdown
<!-- What Claude Code sees in your CLAUDE.md -->
# Hardware Context — motor-controller
## Target Hardware
- **MCU**: STM32F407

## Peripherals
- **SPI1** (9 registers)
- **TIM1** (19 registers)
- **USART2** (7 registers)

## Hardware Reference
Before writing hardware-related code, read the relevant peripheral
context file in `.rag/context/peripherals/` (e.g., `spi1.md`, `tim1.md`).
```

When Claude Code needs register details, it reads the per-peripheral files in `.rag/context/peripherals/`. These contain full register maps:

```markdown
<!-- .rag/context/peripherals/spi1.md -->
# SPI1 — Serial Peripheral Interface
Base address: 0x40013000

## SPI_CR1 (offset 0x00, reset 0x0000)
| Bits  | Field    | Access | Description              |
|-------|----------|--------|--------------------------|
| 15    | BIDIMODE | RW     | Bidirectional data mode  |
| 14    | BIDIOE   | RW     | Output enable            |
| 11    | DFF      | RW     | Data frame format (0=8bit, 1=16bit) |
| 9:8   | SSM,SSI  | RW     | Software slave management |
| 5:3   | BR[2:0]  | RW     | Baud rate (fPCLK/2..256) |
| 2     | MSTR     | RW     | Master selection         |
| 0     | CPHA     | RW     | Clock phase              |
...
```

Now when you ask "configure SPI1 for 8-bit mode at 10.5 MHz", Claude Code reads the actual register map and writes correct code — no hallucinated addresses or made-up bit fields.

### MCP Server (dynamic context)

For real-time queries against the full vector store, run hwcc as an MCP server:

```bash
# Install MCP dependencies
pip install hwcc[mcp]

# Get the config snippet for Claude Code
hwcc mcp --config
```

Add the output to your Claude Code MCP settings (`.claude/settings.json` or `~/.claude.json`):

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

This gives Claude Code three live tools:

| Tool | What It Does |
|------|-------------|
| `hw_search` | Semantic search across all indexed docs |
| `hw_registers` | Get register maps for a specific peripheral |
| `hw_context` | Get compiled context for a peripheral |

And two resources: `hw://peripherals` (list all indexed peripherals) and `hw://documents` (list all indexed documents).

The MCP server is optional — static context in `CLAUDE.md` works without it. The server adds dynamic search for large projects with many peripherals where loading everything statically would be too much.

## What It Produces

After `hwcc add`, your project gets:

| File | Tool | Content |
|------|------|---------|
| `CLAUDE.md` | Claude Code | Hardware context section |
| `AGENTS.md` | Codex CLI | Same context, Codex format |
| `.cursor/rules/hardware.mdc` | Cursor | Cursor rules format |
| `.gemini/GEMINI.md` | Gemini CLI | Gemini format |
| `.github/copilot-instructions.md` | GitHub Copilot | Copilot format |

Plus internal context files in `.rag/context/`:
- **`hot.md`** — Concise hardware summary (~120 lines), always loaded
- **`peripherals/*.md`** — Per-peripheral deep context (registers, usage patterns, errata)

## Supported Documents

| Format | What It Extracts |
|--------|-----------------|
| `.svd` | Register maps with bit-fields, reset values, access types |
| `.pdf` | Text + tables from datasheets, reference manuals, errata |
| `.dts` / `.dtsi` | Device tree topology, peripheral nodes, pin configs |
| `.md` / `.txt` | Passthrough (application notes, custom docs) |

## Commands

```
hwcc init [--chip <mcu>]                Initialize project
hwcc add <file> [--type <type>]         Add document(s) to index
hwcc remove <doc_id>                    Remove a document
hwcc status                             Show project status
hwcc compile [--target <tool>]          Regenerate context files
hwcc search <query> [-k N]              Search indexed documentation
hwcc mcp [--config]                     Start MCP server / print config
hwcc catalog list [<query>]             Browse device SVD catalog
hwcc catalog add <device>               Download and add SVD from catalog
hwcc version                            Show version
```

### Useful Options

```bash
# Add with explicit chip tag (useful for multi-chip projects)
hwcc add power-ic.pdf --chip TPS65217

# Compile for a specific tool only
hwcc compile --target claude

# Skip auto-compile after adding (compile manually later)
hwcc add docs/*.svd --no-compile

# Search indexed docs from the command line
hwcc search "SPI clock configuration" -k 10

# Find and add an SVD from the built-in catalog
hwcc catalog list STM32F4
hwcc catalog add STM32F407
```

## Configuration

`hwcc init` creates `.rag/config.toml`:

```toml
[project]
name = "motor-controller"

[hardware]
mcu = "STM32F407VGT6"
mcu_family = "STM32F4"

[software]
rtos = "FreeRTOS 10.5.1"
hal = "STM32 HAL v1.27.1"

[conventions]
register_access = "HAL functions only, no direct register writes"

[embedding]
provider = "chromadb"  # Default: built-in, zero-config

[output]
targets = ["claude", "codex", "cursor", "gemini"]
```

Edit this file to tune what context gets generated.

## Example Output

See [`examples/stm32f407-motor/`](examples/stm32f407-motor/) for a complete sample project with pre-generated output. Key files:

- [`CLAUDE.md`](examples/stm32f407-motor/CLAUDE.md) — User content preserved, hardware context injected between markers
- [`peripherals/spi1.md`](examples/stm32f407-motor/.rag/context/peripherals/spi1.md) — Full SPI1 register map with bit-fields and reset values
- [`peripherals/tim1.md`](examples/stm32f407-motor/.rag/context/peripherals/tim1.md) — TIM1 advanced timer registers

## How It Works

```
Raw Docs → Parse → Chunk → Embed → Store → Compile → Output Files
             |        |       |       |         |
           SVD/PDF  512-tok  ONNX  ChromaDB  Jinja2 templates
           parser   splits   local  vectors   per-tool output
```

All processing is deterministic and local. No LLM calls in the core pipeline. Embedding uses ChromaDB's built-in ONNX model (`all-MiniLM-L6-v2`) — zero configuration needed.

## Benchmarking (HwBench)

hwcc includes a built-in benchmark suite that quantitatively measures how much compiled context improves LLM accuracy on hardware register questions. It compares "no context" (LLM guessing from training data) against "hwcc context" (LLM with compiled register maps).

### Workflow

```bash
# 1. Generate a Q&A dataset from an SVD file
hwcc bench generate docs/STM32F407.svd -o stm32f407_dataset.json

# 2. Run the benchmark using your Claude Code subscription (no API key needed)
hwcc bench run stm32f407_dataset.json --provider claude_code --model sonnet

# 3. View a saved report
hwcc bench report stm32f407_report.json
```

The `claude_code` provider runs questions through the `claude` CLI in print mode, using your existing Claude Code subscription. No API keys required.

### What It Measures

The dataset generator creates questions across five categories from SVD register data:

| Category | Example Question |
|----------|-----------------|
| `base_address` | "What is the base address of SPI1?" |
| `register_offset` | "What is the offset of the SPI_CR1 register?" |
| `bit_field` | "What bits does the BR field occupy in SPI_CR1?" |
| `reset_value` | "What is the reset value of SPI_CR1?" |
| `access_type` | "What is the access type of the MSTR field in SPI_CR1?" |

Each question has a deterministic ground-truth answer extracted from the SVD. Answers are scored by exact match with partial credit for close results.

### Conditions

The runner tests the same questions under different context conditions:

| Condition | Context Provided |
|-----------|-----------------|
| `no_context` | No hardware docs — LLM relies on training data only |
| `hwcc_hot` | Hot context summary (~120 lines) |
| `hwcc_full` | Hot context + per-peripheral register maps |

### Example Report

```
HwBench Report — STM32F407
Dataset: stm32f407_bench
Model: sonnet (claude_code)

┌─────────────┬──────────┬─────────────────┬─────────┬─────────┬───────┬────────────────────┬─────────────┐
│ Condition   │ Accuracy │ 95% CI          │ Partial │ Correct │ Total │ Hallucination Rate │ Avg Latency │
├─────────────┼──────────┼─────────────────┼─────────┼─────────┼───────┼────────────────────┼─────────────┤
│ no_context  │ 12.0%    │ [6.3%, 21.0%]   │ 18.5%   │ 6       │ 50    │ 88.0%              │ 820ms       │
│ hwcc_hot    │ 42.0%    │ [29.0%, 56.0%]  │ 55.2%   │ 21      │ 50    │ 58.0%              │ 950ms       │
│ hwcc_full   │ 94.0%    │ [83.8%, 98.7%]  │ 96.4%   │ 47      │ 50    │ 6.0%               │ 1100ms      │
└─────────────┴──────────┴─────────────────┴─────────┴─────────┴───────┴────────────────────┴─────────────┘

Impact Summary
  Accuracy:       12.0% → 94.0% (+82.0%)
  Hallucination:  88.0% → 6.0% (-82.0%)
```

### Options

```bash
# Run with multiple repetitions for statistical confidence
hwcc bench run dataset.json --provider claude_code --runs 3

# Test specific conditions only
hwcc bench run dataset.json --provider claude_code --conditions no_context,hwcc_full

# Generate markdown report alongside JSON
hwcc bench run dataset.json --provider claude_code --output-format markdown

# Control delay between questions (seconds)
hwcc bench run dataset.json --provider claude_code --delay 1.0

# Use API providers instead (requires API keys)
hwcc bench run dataset.json --provider anthropic --model claude-sonnet-4-20250514
hwcc bench run dataset.json --provider openai --model gpt-4o
hwcc bench run dataset.json --provider ollama --model llama3.1
```

Supported providers:

| Provider | Auth | Install |
|----------|------|---------|
| `claude_code` | Claude Code subscription (no key needed) | Just needs `claude` CLI |
| `anthropic` | `ANTHROPIC_API_KEY` | `pip install hwcc[bench]` |
| `openai` | `OPENAI_API_KEY` | `pip install hwcc[bench]` |
| `ollama` | None (local) | Ollama running locally |

## Why Not Just Give the AI the PDF?

- PDFs are huge (500+ pages). Context windows are expensive and lossy.
- SVD register data is structured — parsing it deterministically is more reliable than LLM extraction.
- Pre-compiled context survives context compaction (Claude Code's auto-compaction can drop raw PDFs).
- RAG is ~1,250x cheaper than stuffing full documents into every prompt.

## Development

```bash
git clone https://github.com/Ecro/hwcc.git
cd hwcc
pip install -e ".[dev]"

pytest tests/           # 675 tests
ruff check src/ tests/  # lint
mypy src/hwcc/          # type check
```

## License

MIT

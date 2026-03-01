# hwcc — Hardware Context Compiler

AI coding tools already read everything in your repo — source code, Makefiles, configs. But they can't read the vendor PDF on your desk. They hallucinate register addresses, get init sequences wrong, and miss errata.

**hwcc** fixes this. It transforms hardware documentation (datasheets, SVD files, reference manuals, device trees) into AI-optimized context files that any coding tool can consume — Claude Code, Codex, Cursor, Gemini CLI, or Copilot.

## Install

```bash
pip install git+https://github.com/Ecro/hwcc.git
```

Or install from source:

```bash
git clone https://github.com/Ecro/hwcc.git
cd hwcc
pip install -e .
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

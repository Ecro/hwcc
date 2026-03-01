# hwcc — Competitive Landscape & Strategy

> **Last Updated**: 2026-03-01
> **See also**: `TECH_SPEC.md` (technical blueprint), `PLAN.md` (implementation roadmap)

---

## Market Positioning

```
                        Hardware-Specific Knowledge
                        Low ◄──────────────────► High
                        │                         │
  Full IDE/Platform  ── │  Cursor / Codex         │  Embedder (YC S25)
                        │  (generic AI IDEs)      │  (closed, enterprise $$$)
                        │                         │
  Preprocessing /    ── │  Skill Seekers          │  ★ HWCC ★
  Context Compiler      │  CTX, RAG-CLI           │  (open source, tool-agnostic)
                        │  (no HW knowledge)      │
  Validation /       ── │                         │  RespCode
  Post-Processing       │                         │  (closed, post-gen fix)
                        │                         │
  Vendor Data        ── │                         │  Microchip MCP
  Server                │                         │  (free, single vendor)
```

## Direct Competitors

| Competitor | Type | Differentiator from Us |
|-----------|------|----------------------|
| **Embedder** (YC S25) | Closed IDE, enterprise + free maker tier | v0.2.0 shipped with unlimited maker plan, TUI, LSP integration. Nominated for embedded award 2026. We are open-source and tool-agnostic — they lock you into their IDE, but the free tier lowers their barrier for hobbyists. |
| **RespCode** | Closed SaaS | They fix wrong code *after* generation. We prevent it *before* by providing correct context. |
| **Skill Seekers** | Open-source preprocessor | General-purpose (React docs, Django). Zero hardware domain knowledge — no SVD, no register maps, no errata. |
| **CTX / RAG-CLI** | Open-source tools | Codebase context only. No PDF parsing, no hardware doc understanding. |
| **Microchip MCP** | Free vendor server | Single vendor, product selection data only. No register-level programming context. |

## Strategic Gaps (No Competition)

These are gaps where **no existing tool (open or closed) addresses the need**:

| ID | Gap | Why It Matters | Priority |
|----|-----|---------------|----------|
| **G1** | Open-source hardware context compiler | Nobody does this. Embedder is closed. Skill Seekers is generic. | **P0** |
| **G2** | SVD-first register context | RespCode proved LLMs get register addresses wrong. Pre-generation context > post-generation validation. | **P0** |
| **G3** | Tool-agnostic multi-format output | Embedder locks you into their IDE. Nobody outputs to ALL coding tools simultaneously. | **P1** |
| **G4** | Errata cross-referencing | No tool cross-references errata with register context. Inline warnings = prevented hardware bugs. | **P2** |
| **G5** | Multi-vendor in one project | Real projects use STM32 + TI power IC + NXP sensor. Nobody aggregates cross-vendor context. | **P1** |
| **G6** | Hardware llms.txt standard | No hardware variant of llms.txt exists. First mover defines the format. | **P2** |

## Complementary Ecosystem

Hardware MCP servers serve **different use cases** — interaction with hardware, not documentation preprocessing:

| Tool | What It Does | Relationship |
|------|-------------|-------------|
| `embedded-debugger-mcp` (probe-rs) | Debug ARM/RISC-V via MCP — flash, breakpoints, memory read | Complementary: our docs + their debugger = full workflow |
| `EmbedMCP` | C library to run MCP servers ON embedded devices | Different layer: they expose device APIs; we expose documentation |
| `serial-mcp-server` | Serial port comms via MCP for IoT/embedded | Complementary: hardware interaction, not documentation |

## Market Validation

- **RespCode benchmarks**: 3 of 4 flagship LLMs produce firmware with wrong register addresses without context
- **EmbedGenius (arXiv:2412.09058v2)**: 95.7% coding accuracy with structured pin assignments + relevance-scored retrieval (-26.2% tokens) + usage pattern tables (+7.1% accuracy)
- **Microchip MCP server**: Silicon vendor validating MCP-based approach (product selection, not programming context)
- **MCP ecosystem**: 425 servers (Aug 2025) → 1,412 (Feb 2026) — 232% growth in 6 months
- **SO Developer Survey 2025**: 84% of devs use AI tools, but only 29% trust output accuracy
- **llms.txt standard**: 844K+ websites adopted web variant. No hardware variant exists.

## Key Insight: What AI Tools Can't Get From Code

Claude Code, Codex, and Cursor already read everything in the repo. hwcc's value is providing what ISN'T there:

| hwcc Provides (NOT in repo) | AI Gets Wrong Without It |
|-----------------------------|--------------------------|
| Register bit-fields + reset values (SVD, ref manual PDF) | Invents addresses, wrong bit positions |
| Peripheral init sequences (ref manual PDF) | Wrong order, missing clock enable |
| Errata / silicon bugs (errata PDF) | No way to know from code alone |
| Pin alternate function tables (datasheet PDF) | Wrong AF number = hardware damage |
| Clock tree / bus assignments (ref manual PDF) | Wrong prescaler, peripheral on wrong bus |
| DMA channel/request mappings (ref manual PDF) | Wrong channel = silent data corruption |
| Hardware topology summary (DTS → concise table) | Must parse 500+ lines of DTS syntax |
| Project hardware constraints (engineer knowledge) | Guesses pin assignments, power budgets |

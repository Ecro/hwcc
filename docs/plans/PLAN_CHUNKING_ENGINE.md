# Plan: Chunking Engine (Task 1.5)

## Scope Declaration
- **Type:** feature
- **Single Concern:** Implement the recursive token-aware chunking engine that splits `ParseResult` content into `list[Chunk]`
- **Phase:** 1 (Document Ingestion)
- **Complexity:** Medium
- **Risk:** Low

### Concern Separation Rule
This change is ONLY about: Splitting parsed markdown content into token-bounded chunks with metadata
This change is NOT about: Embedding, storage, CLI commands, config file format changes beyond chunk settings

## Problem Statement
**What:** Implement a concrete `MarkdownChunker` that inherits from `BaseChunker` and splits parsed document content (markdown) into appropriately-sized chunks for embedding and retrieval.

**Why:** The chunker is the bridge between parsing (done) and embedding (next). Without it, the pipeline has no way to break documents into retrieval-friendly pieces. Quality chunking directly impacts retrieval accuracy — bad splits (mid-table, mid-code-block) produce garbage context.

**Success:** `MarkdownChunker.chunk()` produces well-formed `Chunk` objects with correct token counts, respects content boundaries (tables, code blocks, headings), and maintains metadata lineage from `ParseResult`.

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/chunk/markdown.py` | create | `MarkdownChunker` — the concrete chunker implementation |
| `src/hwcc/chunk/__init__.py` | modify | Re-export `MarkdownChunker` alongside `BaseChunker` |
| `src/hwcc/config.py` | modify | Add `ChunkConfig` dataclass with `max_tokens`, `overlap_tokens`, `min_tokens` |
| `pyproject.toml` | modify | Add `tiktoken>=0.7` dependency |
| `tests/test_chunk.py` | create | Full test suite for the chunker |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `MarkdownChunker.chunk()` | `Pipeline.process()` | `types.Chunk`, `types.ChunkMetadata`, `types.ParseResult` |
| `ChunkConfig` | `HwccConfig`, `MarkdownChunker` | None |
| `chunk/__init__.py` | External consumers | `MarkdownChunker`, `BaseChunker` |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| **Chunk** (this) | Receives `ParseResult` from parsers (SVD, PDF, Markdown, Text) | Produces `list[Chunk]` consumed by `BaseEmbedder.embed_chunks()` |

## NON-GOALS (Explicitly Out of Scope)
- [ ] Embedding engine — save for task 1.6
- [ ] ChromaDB storage — save for task 1.7
- [ ] `hwcc add` CLI command — save for task 1.8
- [ ] Hierarchical chunking (summary + detail) — future enhancement, not v1
- [ ] LLM-based section summarization — optional enrichment, not part of chunking
- [ ] Existing parser code — parsers are done and working
- [ ] Template files — compile stage concern

## Technical Approach

### Option A: Recursive Markdown-Aware Splitter (Recommended)

A single `MarkdownChunker` class that splits content using a hierarchy of separators, respecting markdown structure:

1. **Pre-processing**: Identify and protect atomic blocks (tables, fenced code blocks) from being split
2. **Recursive splitting**: Try separators in priority order:
   - `\n# ` (H1 headings)
   - `\n## ` (H2 headings)
   - `\n### ` (H3-H6 headings)
   - `\n\n` (paragraph boundaries)
   - `\n` (line breaks)
   - ` ` (word boundaries — last resort)
3. **Overlap**: When splitting, include `overlap_tokens` from the end of the previous chunk at the start of the next
4. **Token counting**: Use `tiktoken` with `cl100k_base` encoding (GPT-4/Claude compatible)
5. **Metadata propagation**: Each chunk inherits `doc_id`, `doc_type`, `chip` from the `ParseResult`, plus gets section path tracking from heading hierarchy

**Pros:**
- Deterministic, no LLM needed
- Respects markdown structure naturally
- Well-tested pattern (used by LangChain, LlamaIndex)
- tiktoken is fast and accurate

**Cons:**
- tiktoken adds ~2MB dependency
- Token counting may differ slightly from model-specific tokenizers (acceptable — we're estimating, not exact-matching)

### Token Counting

Use `tiktoken` with `cl100k_base` encoding. This is the standard for GPT-4 and close enough for Claude's tokenizer. The slight mismatch doesn't matter — we're setting chunk size budgets, not doing exact token billing.

Lazy-load the encoding to avoid import-time cost:

```python
import tiktoken

_encoding: tiktoken.Encoding | None = None

def _get_encoding() -> tiktoken.Encoding:
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding

def count_tokens(text: str) -> int:
    return len(_get_encoding().encode(text))
```

### Section Path Tracking

As the chunker encounters headings, it maintains a stack of heading levels to build `section_path`:

```
# SPI             → section_path = "SPI"
## Configuration  → section_path = "SPI > Configuration"
### DMA           → section_path = "SPI > Configuration > DMA"
## Registers      → section_path = "SPI > Registers"  (stack pops back)
```

### Atomic Block Protection

Before splitting, identify blocks that must not be split:
- **Markdown tables**: Lines starting with `|` between `|---` header separators
- **Fenced code blocks**: Content between ``` or ~~~ fences
- If an atomic block exceeds `max_tokens`, it becomes its own chunk (even if over-sized) — better to have one large chunk than to break a table

### Config Extension

Add `ChunkConfig` to `config.py`:

```python
@dataclass
class ChunkConfig:
    max_tokens: int = 512
    overlap_tokens: int = 50      # ~10% of max_tokens
    min_tokens: int = 50          # discard tiny chunks
```

Add to `HwccConfig`:
```python
chunk: ChunkConfig = field(default_factory=ChunkConfig)
```

Map from `[chunk]` section in config.toml.

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Add ChunkConfig to config | `src/hwcc/config.py` | Add `ChunkConfig` dataclass, add `chunk` field to `HwccConfig`, update `_config_to_dict` and section map |
| 2 | Add tiktoken dependency | `pyproject.toml` | Add `tiktoken>=0.7` to dependencies |
| 3 | Implement MarkdownChunker | `src/hwcc/chunk/markdown.py` | Core chunker: token counting, recursive splitting, table/code-block protection, section tracking, overlap, metadata |
| 4 | Update chunk __init__.py | `src/hwcc/chunk/__init__.py` | Re-export `MarkdownChunker` |
| 5 | Write tests | `tests/test_chunk.py` | Comprehensive test suite |
| 6 | Verify full pipeline | — | Run `pytest tests/` to confirm nothing broke |

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Short content returns single chunk | `tests/test_chunk.py` | unit |
| 2 | Long content splits into multiple chunks within token budget | `tests/test_chunk.py` | unit |
| 3 | Chunks have correct token_count field | `tests/test_chunk.py` | unit |
| 4 | Overlap tokens appear at start of subsequent chunks | `tests/test_chunk.py` | unit |
| 5 | Markdown tables are never split mid-table | `tests/test_chunk.py` | unit |
| 6 | Fenced code blocks are never split | `tests/test_chunk.py` | unit |
| 7 | Splits prefer heading boundaries over paragraph boundaries | `tests/test_chunk.py` | unit |
| 8 | Section path tracks heading hierarchy correctly | `tests/test_chunk.py` | unit |
| 9 | Metadata (doc_id, doc_type, chip) propagates from ParseResult | `tests/test_chunk.py` | unit |
| 10 | chunk_id is unique per chunk | `tests/test_chunk.py` | unit |
| 11 | Empty content returns empty list | `tests/test_chunk.py` | unit |
| 12 | Whitespace-only content returns empty list | `tests/test_chunk.py` | unit |
| 13 | Chunks below min_tokens are merged with neighbors | `tests/test_chunk.py` | unit |
| 14 | Oversized atomic blocks (large table) become single chunk | `tests/test_chunk.py` | unit |
| 15 | ChunkConfig default values are correct | `tests/test_chunk.py` | unit |
| 16 | Config round-trip preserves chunk settings | `tests/test_config.py` | unit |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Chunk SVD parser output (large register map markdown) | Tables preserved intact, each peripheral section is a coherent chunk | automated |
| 2 | Chunk PDF parser output (multi-page datasheet markdown) | Section boundaries respected, no mid-sentence splits | automated |
| 3 | Chunk small markdown file | Single chunk returned, no unnecessary splitting | automated |
| 4 | All chunks have `token_count <= max_tokens` (except atomic blocks) | Token budget respected | automated |
| 5 | All chunks have `token_count >= min_tokens` (except final chunk) | No tiny useless chunks | automated |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/config.py` | modify | Add `ChunkConfig` dataclass, add to `HwccConfig` |
| `src/hwcc/chunk/__init__.py` | modify | Re-export `MarkdownChunker` |
| `pyproject.toml` | modify | Add `tiktoken>=0.7` |

## Files to Create
| File | Purpose |
|------|---------|
| `src/hwcc/chunk/markdown.py` | `MarkdownChunker` concrete implementation |
| `tests/test_chunk.py` | Chunker test suite |

## Exit Criteria
```
[ ] MarkdownChunker implements BaseChunker contract
[ ] Token counting uses tiktoken cl100k_base
[ ] Tables never split mid-table
[ ] Code blocks never split mid-block
[ ] Heading boundaries preferred for splitting
[ ] Section path tracking works (h1 > h2 > h3)
[ ] Overlap works correctly between consecutive chunks
[ ] Metadata propagated from ParseResult to every Chunk
[ ] chunk_id is unique across chunks
[ ] min_tokens filtering prevents tiny chunks
[ ] ChunkConfig added to HwccConfig with sensible defaults
[ ] All tests pass
[ ] All changes within declared scope (no scope creep)
[ ] NON-GOALS remain untouched
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/test_chunk.py -v`
- [ ] Full suite passes: `pytest tests/`
- [ ] Lint passes: `ruff check src/hwcc/chunk/ tests/test_chunk.py`
- [ ] Types correct: `mypy src/hwcc/chunk/`
- [ ] No unintended side effects in: parsers, embed, store, compile, serve

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None (chunking strategy already documented in §5.3)
- [ ] **PLAN.md:** Mark task 1.5 as `[x]` after implementation

---

> **Last Updated:** 2026-02-28

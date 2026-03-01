# Plan: Task 2.7 — Relevance-Scored Chunk Selection

## Scope Declaration
- **Type:** feature
- **Single Concern:** Add deterministic keyword-overlap scoring to rank/filter non-SVD chunks during peripheral compilation, reducing output tokens
- **Phase:** v0.2 (Quality & Search)
- **Complexity:** Medium
- **Risk:** Low

## Problem Statement

**What:** `_gather_peripheral_details()` selects the first 5 non-SVD chunks by `chunk_id` order (positional). No relevance ranking — early low-value chunks crowd out later high-value ones.

**Why:** EmbedGenius research shows selective memory pick-up via TF-IDF reduces token consumption by ~26%. Deterministic keyword scoring achieves similar results without requiring an embedder at compile time.

**Success:** Non-SVD chunks in peripheral output are ranked by keyword relevance. Low-relevance chunks are filtered out. Token savings are logged.

## Current Flow

```python
# peripheral.py:295-302
relevant = [c for c in non_svd_chunks
            if self._section_path_mentions_peripheral(...)]
relevant.sort(key=lambda c: c.chunk_id)      # positional order
relevant = relevant[:_MAX_DETAIL_CHUNKS]      # first 5, regardless of quality
```

## Technical Approach: Keyword-Overlap Scoring (Deterministic)

PLAN.md explicitly says "deterministic" — no embedder/LLM dependency. Pure text-based scoring.

### Algorithm

1. **Build keyword set** from peripheral name + SVD register map + description:
   - Peripheral name tokens: `"SPI1"` → `{"spi1", "spi"}`
   - Register names from markdown tables: `{"cr1", "cr2", "sr", "dr"}`
   - Description words (filtered): `"Serial peripheral interface"` → `{"serial"}`
   - Skip stopwords, markdown syntax, numbers-only tokens
   - Typical keyword set: 5–20 terms

2. **Score each candidate chunk**: `overlap_count / len(keywords)`
   - Tokenize chunk content → lowercase word set
   - Count keyword hits in word set
   - Score range: 0.0 (no keywords found) to 1.0 (all keywords found)

3. **Filter and rank**: Sort by score descending (chunk_id for stability), apply minimum threshold, take top `_MAX_DETAIL_CHUNKS`.

### Example

Peripheral "SPI1", keywords = `{"spi1", "spi", "serial", "cr1", "cr2", "sr", "control", "status"}`

| Chunk | Keywords Found | Score | Include? |
|-------|---------------|-------|----------|
| "SPI1 clock configuration..." | spi1, spi, cr1, control | 4/8 = 0.50 | Yes |
| "DMA configuration for SPI..." | spi | 1/8 = 0.125 | Yes (above 0.1) |
| "General GPIO overview..." | — | 0/8 = 0.0 | No |

### Why Not Vector Search?

- `store.search()` requires an embedding vector → needs embedder at compile time
- Changes `BaseCompiler` interface (adds embedder dependency)
- Non-deterministic (embedding model choice affects results)
- Keyword overlap is simpler, faster, and sufficient for pre-filtered candidates

---

## Impact Analysis

### Direct Changes

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/compile/relevance.py` | create | Pure scoring functions: tokenize, build_keywords, score, rank |
| `src/hwcc/compile/peripheral.py` | modify | `_gather_peripheral_details()` uses `rank_chunks()` instead of positional sort |
| `src/hwcc/compile/__init__.py` | modify | Export `rank_chunks`, `score_chunk_relevance` |
| `tests/test_compile_relevance.py` | create | ~15 tests for all scoring functions |
| `tests/test_compile_peripheral.py` | modify | Add tests for relevance-scored selection |

### Dependency Chain

| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `relevance.score_chunk_relevance()` | `relevance.rank_chunks()` | `relevance._tokenize()` |
| `relevance.rank_chunks()` | `peripheral._gather_peripheral_details()` | `score_chunk_relevance()`, `build_peripheral_keywords()` |
| `peripheral._gather_peripheral_details()` | `peripheral.compile()` | `rank_chunks()`, `format_citation()` |

### Pipeline Impact

| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Compile | None (reads same store data) | Better quality peripheral context, fewer tokens |

## NON-GOALS (Explicitly Out of Scope)

- [ ] `BaseCompiler` ABC changes — no embedder parameter, no interface changes
- [ ] `HotContextCompiler` — uses metadata only, no chunk content to score
- [ ] Vector similarity search in compile stage — save for v0.3 MCP serve
- [ ] Config-tunable threshold — hardcoded default for now
- [ ] `store/` module — no changes to store interface or ChromaDB
- [ ] Template changes — scoring affects chunk selection, not rendering
- [ ] Usage pattern extraction (task 2.8) — separate concern
- [ ] CLI search (task 3.6) — separate concern

---

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Create relevance module | `src/hwcc/compile/relevance.py` | `_tokenize()`, `_STOPWORDS`, `build_peripheral_keywords()`, `score_chunk_relevance()`, `rank_chunks()` |
| 2 | Write relevance tests | `tests/test_compile_relevance.py` | ~15 tests: tokenization, keyword building, scoring, ranking, edge cases |
| 3 | Integrate into peripheral compiler | `src/hwcc/compile/peripheral.py` | Pass `register_map`+`description` to `_gather_peripheral_details()`, call `rank_chunks()` |
| 4 | Write peripheral integration tests | `tests/test_compile_peripheral.py` | Tests verifying scored selection, low-relevance filtering, token reduction |
| 5 | Update __init__.py exports | `src/hwcc/compile/__init__.py` | Export public functions |
| 6 | Full verification | — | pytest, ruff, mypy |

## Module Design: `src/hwcc/compile/relevance.py`

```python
"""Deterministic keyword-overlap scoring for chunk relevance."""

import re
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from hwcc.types import Chunk

# Minimum score to include a chunk (10% of keywords must appear)
_MIN_RELEVANCE_SCORE = 0.1

# Common English stopwords + markdown artifacts
_STOPWORDS: frozenset[str] = frozenset({...})

# Regex for extracting register names from markdown tables
_REGISTER_NAME_RE = re.compile(r"^\|\s*(\w+)\s*\|", re.MULTILINE)

def _tokenize(text: str) -> set[str]:
    """Extract unique lowercase word tokens, filtering stopwords."""

def build_peripheral_keywords(
    peripheral_name: str,
    register_map: str = "",
    description: str = "",
) -> set[str]:
    """Build keyword set from peripheral name + SVD content."""

def score_chunk_relevance(content: str, keywords: set[str]) -> float:
    """Score content by keyword overlap ratio. Returns 0.0–1.0."""

def rank_chunks(
    chunks: list[Chunk],
    keywords: set[str],
    max_chunks: int = 5,
    min_score: float = _MIN_RELEVANCE_SCORE,
) -> list[Chunk]:
    """Score, filter, and rank chunks by keyword relevance."""
```

## Integration Point: `peripheral.py`

```python
# In compile(), pass register_map and description to details gathering:
details = self._gather_peripheral_details(
    name, non_svd_chunks, chip,
    title_map=title_map,
    register_map=register_map,
    description=description,
)

# In _gather_peripheral_details(), replace positional sort with ranking:
from hwcc.compile.relevance import build_peripheral_keywords, rank_chunks

keywords = build_peripheral_keywords(peripheral_name, register_map, description)
relevant = rank_chunks(relevant, keywords, max_chunks=_MAX_DETAIL_CHUNKS)
```

---

## Test Plan

### Unit Tests (`tests/test_compile_relevance.py`)

| # | Test Description | Type |
|---|-----------------|------|
| 1 | `_tokenize` extracts lowercase words from plain text | unit |
| 2 | `_tokenize` strips markdown syntax (##, **, \|, backticks) | unit |
| 3 | `_tokenize` filters stopwords | unit |
| 4 | `_tokenize` handles empty/whitespace input | unit |
| 5 | `build_peripheral_keywords` extracts peripheral name tokens | unit |
| 6 | `build_peripheral_keywords` extracts register names from markdown table | unit |
| 7 | `build_peripheral_keywords` extracts description words | unit |
| 8 | `build_peripheral_keywords` with empty inputs returns name-only | unit |
| 9 | `score_chunk_relevance` returns 0.0 for no overlap | unit |
| 10 | `score_chunk_relevance` returns 1.0 for full overlap | unit |
| 11 | `score_chunk_relevance` returns correct ratio for partial overlap | unit |
| 12 | `score_chunk_relevance` handles empty keywords/content | unit |
| 13 | `rank_chunks` sorts by score descending | unit |
| 14 | `rank_chunks` filters below min_score | unit |
| 15 | `rank_chunks` respects max_chunks limit | unit |
| 16 | `rank_chunks` uses chunk_id for tiebreaking | unit |

### Integration Tests (`tests/test_compile_peripheral.py`)

| # | Test Description | Type |
|---|-----------------|------|
| 17 | Peripheral details prefer high-relevance chunks over positional order | integration |
| 18 | Low-relevance chunks are excluded from output | integration |
| 19 | Backward compat: chunks with section_path match still included | integration |

---

## Exit Criteria

```
□ New relevance.py module with all functions
□ 16+ unit tests for scoring functions
□ 3+ integration tests in peripheral test file
□ _gather_peripheral_details uses rank_chunks instead of positional sort
□ Token reduction logged at info level
□ All 740+ tests pass
□ ruff check clean
□ mypy clean
□ No changes to BaseCompiler ABC, HotContextCompiler, store, or templates
□ NON-GOALS remain untouched
```

## Verification Strategy

```bash
pytest tests/                       # All tests pass
ruff check src/ tests/              # No lint errors
mypy src/hwcc/                      # No type errors
# Manual: hwcc add some.pdf && hwcc compile → check peripheral .md files
# Verify: low-relevance chunks are filtered, output is more focused
```

## Document Updates Needed

- [ ] **TECH_SPEC.md:** None (no config/interface changes)
- [ ] **PLAN.md:** Check off task 2.7

---

> **Last Updated:** 2026-03-02

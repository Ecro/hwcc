# Plan: Implement Embedding Engine (Task 1.6)

## Scope Declaration

### Change Intent
- **Type:** feature
- **Single Concern:** Add concrete embedding providers (OllamaEmbedder, OpenAICompatEmbedder) that implement BaseEmbedder ABC, register them with ProviderRegistry, and add necessary config fields.

### Concern Separation Rule
This change is ONLY about: embedding provider implementations and their registration
This change is NOT about: ChromaDB storage (1.7), CLI commands (1.8-1.10), chunking changes, compile stage, serve stage

## Problem Statement
**What:** Implement two concrete embedding providers that satisfy the `BaseEmbedder` ABC contract: `OllamaEmbedder` (default, local) and `OpenAICompatEmbedder` (cloud/compatible endpoints). Register both with the `ProviderRegistry`.

**Why:** The pipeline requires embeddings to convert chunks into vectors for storage and retrieval. Without real embedders, `hwcc add` cannot index documents. This is a prerequisite for task 1.7 (ChromaDB storage) and the full ingestion pipeline.

**Success:** Both providers pass all unit tests with mocked HTTP. Registry-based creation works. Config round-trips correctly with new fields.

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/embed/ollama.py` | create | OllamaEmbedder implementation |
| `src/hwcc/embed/openai_compat.py` | create | OpenAICompatEmbedder implementation |
| `src/hwcc/embed/__init__.py` | modify | Re-export new providers, register with default_registry |
| `src/hwcc/config.py` | modify | Add `base_url` and `batch_size` fields to EmbeddingConfig |
| `tests/test_embed.py` | create | Unit tests for both providers |
| `tests/test_config.py` | modify | Add embedding config round-trip test |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `OllamaEmbedder` | `Pipeline.process()`, `ProviderRegistry.create()` | `urllib.request` (HTTP to Ollama) |
| `OpenAICompatEmbedder` | `Pipeline.process()`, `ProviderRegistry.create()` | `urllib.request` (HTTP to API) |
| `EmbeddingConfig` | `OllamaEmbedder.__init__()`, `OpenAICompatEmbedder.__init__()` | — |
| `ProviderRegistry` | `hwcc add` CLI (future) | Provider factories |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Embed | Receives `list[Chunk]` from MarkdownChunker | Produces `list[EmbeddedChunk]` for BaseStore (task 1.7) |

## NON-GOALS (Explicitly Out of Scope)
- [ ] ChromaDB storage — Task 1.7, separate concern
- [ ] CLI `hwcc add` command — Task 1.8, separate concern
- [ ] HuggingFace sentence-transformers provider — Future enhancement
- [ ] Auto-fallback chain between providers — Future enhancement
- [ ] LLM providers (LlmConfig) — Different pipeline concern
- [ ] Chunking engine changes — Already complete (task 1.5)
- [ ] Pipeline.py changes — Already correct, uses BaseEmbedder interface

## Technical Approach

### Option A: stdlib urllib.request (Recommended)
Use `urllib.request` for HTTP calls to avoid adding new dependencies. Both Ollama and OpenAI-compatible APIs use simple JSON POST endpoints.

- **Pros:** Zero new dependencies, stdlib is always available, simple JSON API
- **Cons:** Slightly more boilerplate than `httpx`/`requests`, no async support

### Option B: httpx
Use `httpx` for HTTP calls.

- **Pros:** Modern, clean API, async support
- **Cons:** New dependency, overkill for simple JSON POST calls

**Decision:** Option A — stdlib `urllib.request`. The Ollama `/api/embed` and OpenAI `/v1/embeddings` endpoints are simple JSON POST. No need for a dependency.

### Design Details

#### OllamaEmbedder
- Default `base_url`: `http://localhost:11434`
- Endpoint: `POST /api/embed` with `{"model": "<model>", "input": [<texts>]}`
- Ollama natively supports batch embedding via `input` array
- `nomic-embed-text` outputs 768-dim vectors
- Graceful error on connection refused (Ollama not running)

#### OpenAICompatEmbedder
- Configurable `base_url` (e.g., `https://api.openai.com/v1` or any compatible server)
- Endpoint: `POST /v1/embeddings` with `{"model": "<model>", "input": [<texts>]}`
- API key from environment variable specified in `api_key_env` config field
- Supports any OpenAI-compatible API (LiteLLM proxy, vLLM, etc.)

#### Batching Strategy
- `batch_size` config field (default 64) controls how many chunks per API call
- Both providers split `embed_chunks()` into batches internally
- Prevents OOM on large documents and respects API rate limits

#### Config Changes
```python
@dataclass
class EmbeddingConfig:
    model: str = "nomic-embed-text"
    provider: str = "ollama"
    api_key_env: str = ""
    base_url: str = ""        # NEW: empty = provider default
    batch_size: int = 64      # NEW: chunks per API call
```

#### Registry Integration
Register in `embed/__init__.py`:
```python
from hwcc.registry import default_registry
default_registry.register("embedding", "ollama", lambda cfg: OllamaEmbedder(cfg))
default_registry.register("embedding", "openai", lambda cfg: OpenAICompatEmbedder(cfg))
```

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Add config fields | `src/hwcc/config.py` | Add `base_url: str = ""` and `batch_size: int = 64` to `EmbeddingConfig` |
| 2 | Implement OllamaEmbedder | `src/hwcc/embed/ollama.py` | Concrete BaseEmbedder using Ollama `/api/embed` endpoint |
| 3 | Implement OpenAICompatEmbedder | `src/hwcc/embed/openai_compat.py` | Concrete BaseEmbedder using OpenAI `/v1/embeddings` endpoint |
| 4 | Update embed package exports | `src/hwcc/embed/__init__.py` | Re-export providers, register with default_registry |
| 5 | Write tests | `tests/test_embed.py` | Unit tests with mocked HTTP for both providers |
| 6 | Add config round-trip test | `tests/test_config.py` | Verify new EmbeddingConfig fields survive TOML save/load |
| 7 | Verify build | — | Run ruff, mypy, pytest |

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | OllamaEmbedder embeds a single chunk | `tests/test_embed.py` | unit |
| 2 | OllamaEmbedder embeds multiple chunks in batch | `tests/test_embed.py` | unit |
| 3 | OllamaEmbedder respects batch_size (splits large lists) | `tests/test_embed.py` | unit |
| 4 | OllamaEmbedder.embed_query returns vector | `tests/test_embed.py` | unit |
| 5 | OllamaEmbedder.dimension returns correct value | `tests/test_embed.py` | unit |
| 6 | OllamaEmbedder raises EmbeddingError on connection refused | `tests/test_embed.py` | unit |
| 7 | OllamaEmbedder raises EmbeddingError on HTTP error response | `tests/test_embed.py` | unit |
| 8 | OllamaEmbedder uses default base_url when not configured | `tests/test_embed.py` | unit |
| 9 | OllamaEmbedder uses custom base_url when configured | `tests/test_embed.py` | unit |
| 10 | OpenAICompatEmbedder embeds chunks with API key | `tests/test_embed.py` | unit |
| 11 | OpenAICompatEmbedder embeds query | `tests/test_embed.py` | unit |
| 12 | OpenAICompatEmbedder raises EmbeddingError on missing API key | `tests/test_embed.py` | unit |
| 13 | OpenAICompatEmbedder raises EmbeddingError on HTTP error | `tests/test_embed.py` | unit |
| 14 | OpenAICompatEmbedder respects batch_size | `tests/test_embed.py` | unit |
| 15 | EmbeddedChunk has correct embedding tuple type | `tests/test_embed.py` | unit |
| 16 | Registry creates OllamaEmbedder from config | `tests/test_embed.py` | unit |
| 17 | Registry creates OpenAICompatEmbedder from config | `tests/test_embed.py` | unit |
| 18 | Empty chunk list returns empty result | `tests/test_embed.py` | unit |
| 19 | EmbeddingConfig new fields round-trip through TOML | `tests/test_config.py` | unit |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Create OllamaEmbedder from config | Instance with correct model, base_url | automated |
| 2 | Embed 100 chunks with batch_size=32 | 4 HTTP calls (32+32+32+4), all chunks embedded | automated |
| 3 | Ollama not running | EmbeddingError with helpful message | automated |
| 4 | OpenAI API key not set | EmbeddingError with helpful message | automated |
| 5 | Registry lookup "ollama" | Returns OllamaEmbedder instance | automated |
| 6 | Registry lookup "openai" | Returns OpenAICompatEmbedder instance | automated |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/config.py` | modify | Add `base_url`, `batch_size` to EmbeddingConfig |
| `src/hwcc/embed/__init__.py` | modify | Add exports, register providers |
| `tests/test_config.py` | modify | Add embedding config round-trip test |

## Files to Create
| File | Purpose |
|------|---------|
| `src/hwcc/embed/ollama.py` | Ollama embedding provider |
| `src/hwcc/embed/openai_compat.py` | OpenAI-compatible embedding provider |
| `tests/test_embed.py` | Embedding engine tests |

## Exit Criteria
```
□ OllamaEmbedder implements BaseEmbedder ABC correctly
□ OpenAICompatEmbedder implements BaseEmbedder ABC correctly
□ Both providers registered in default_registry
□ EmbeddingConfig has base_url and batch_size fields
□ Config round-trips correctly with new fields
□ All HTTP calls are mocked in tests (no real Ollama/API needed)
□ EmbeddingError raised with helpful messages on failures
□ All changes within declared scope (no scope creep)
□ NON-GOALS remain untouched
□ ruff check passes
□ mypy passes
□ pytest passes
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No unintended side effects in: chunking, pipeline, store, compile, CLI

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None (embedding providers already documented)
- [ ] **PLAN.md:** Mark task 1.6 as [x] on completion

---

> **Last Updated:** 2026-02-28

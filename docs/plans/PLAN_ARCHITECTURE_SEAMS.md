# Plan: Architecture Seams — ABC Contracts, Data Types, Registry, Pipeline

## Scope Declaration
- **Type:** refactor (adding architectural interfaces to existing Phase 0 skeleton)
- **Single Concern:** Define abstract base classes, pipeline data contracts, and registry/composition patterns so every future Phase 1-5 module has a seam to implement against
- **Phase:** 0.5 (between Phase 0 Foundation and Phase 1 Ingest)
- **Complexity:** Medium
- **Risk:** Low (adding new files, no modification of existing passing code)

## Problem Statement
**What:** Phase 0 delivered config, manifest, project manager, and CLI — but zero architectural seams for the 6-stage pipeline (ingest → chunk → embed → store → compile → serve). Every future module will need interfaces to code against and data types to pass between stages.

**Why:** Without ABCs and data contracts now, Phase 1 implementors will create tightly-coupled, untestable code. Adding interfaces retroactively is harder and riskier than defining them up front.

**Success:** Every pipeline stage has an ABC, data flows through frozen dataclasses, providers are instantiated via config-driven registry, and the full pipeline is composable/testable with mock implementations.

## Research Summary

Architecture research evaluated patterns from ChromaDB (Protocol + decorator registry), LlamaIndex (ABC + Protocol dual), sentence-transformers (minimal), and Python ecosystem best practices. Conclusions:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Interface style | **ABC** (not Protocol) | Built-in providers share logic via base class; runtime enforcement via `@abstractmethod`; familiar to contributors |
| DI mechanism | **Constructor injection** | No framework needed for a CLI tool; Pipeline receives all dependencies via `__init__` |
| Provider selection | **Config-driven registry** | `[embedding] provider = "ollama"` → `Registry.get("embedding", "ollama")` → `OllamaEmbedder(config)` |
| Data contracts | **Frozen dataclasses** | `@dataclass(frozen=True)` for `ParseResult`, `Chunk`, `EmbeddedChunk` — immutable between stages |
| Plugin discovery | **Entry points** (`hwcc.plugins`) | Standard Python mechanism; plugins register parsers/providers without modifying core code |

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/types.py` | **create** | Pipeline data contracts (frozen dataclasses) |
| `src/hwcc/ingest/base.py` | **create** | `BaseParser` ABC |
| `src/hwcc/chunk/base.py` | **create** | `BaseChunker` ABC |
| `src/hwcc/embed/base.py` | **create** | `BaseEmbedder` ABC |
| `src/hwcc/store/base.py` | **create** | `BaseStore` ABC |
| `src/hwcc/compile/base.py` | **create** | `BaseCompiler` ABC |
| `src/hwcc/registry.py` | **create** | `ProviderRegistry` — config string → factory → instance |
| `src/hwcc/pipeline.py` | **create** | `Pipeline` class — composes stages via constructor injection |
| `src/hwcc/exceptions.py` | **modify** | Add `ParseError`, `ChunkError`, `EmbeddingError`, `StoreError`, `CompileError`, `PipelineError`, `PluginError` |
| `src/hwcc/__init__.py` | no change | — |
| `src/hwcc/ingest/__init__.py` | **modify** | Export `BaseParser` |
| `src/hwcc/chunk/__init__.py` | **modify** | Export `BaseChunker` |
| `src/hwcc/embed/__init__.py` | **modify** | Export `BaseEmbedder` |
| `src/hwcc/store/__init__.py` | **modify** | Export `BaseStore` |
| `src/hwcc/compile/__init__.py` | **modify** | Export `BaseCompiler` |

### Dependency Chain
| Modified Code | Callers (Future) | Callees |
|--------------|------------------|---------|
| `BaseParser` | SVD parser, PDF parser, markdown parser | `ParseResult` data type |
| `BaseChunker` | Recursive chunker, table-aware chunker | `Chunk` data type |
| `BaseEmbedder` | OllamaEmbedder, OpenAIEmbedder | `EmbeddedChunk` data type |
| `BaseStore` | ChromaDBStore | `Chunk`, `EmbeddedChunk` data types |
| `BaseCompiler` | HotContextCompiler, PeripheralCompiler | `HwccConfig`, store queries |
| `ProviderRegistry` | CLI commands, Pipeline | All ABCs |
| `Pipeline` | CLI `add` command | All ABCs via constructor injection |

### Pipeline Impact
| Pipeline Stage | Data In | Data Out |
|---------------|---------|----------|
| **Parse** (ingest) | `Path` + config | `ParseResult` (clean markdown + metadata) |
| **Chunk** | `ParseResult` | `list[Chunk]` (text + metadata) |
| **Embed** | `list[Chunk]` | `list[EmbeddedChunk]` (chunk + vector) |
| **Store** | `list[EmbeddedChunk]` | persisted (side effect) |
| **Compile** | Store queries + config | output files (side effect) |

## NON-GOALS (Explicitly Out of Scope)
- [ ] **Concrete parser implementations** (SVD, PDF, markdown) — Phase 1
- [ ] **Concrete embedder implementations** (Ollama, OpenAI) — Phase 1
- [ ] **ChromaDB store implementation** — Phase 1
- [ ] **Compile/template implementations** — Phase 2
- [ ] **MCP server** — Phase 3
- [ ] **CLI command changes** — existing stubs remain, no wiring yet
- [ ] **Config schema changes** — existing `config.toml` structure is sufficient
- [ ] **Plugin entry point loading** — Phase 5 (just define the interface now)

## Technical Approach

### Architecture: Ports & Adapters with Pipeline Composition

```
config.toml
    │
    ▼
┌─────────────────┐
│ ProviderRegistry │  maps "ollama" → OllamaEmbedder, etc.
└────────┬────────┘
         │ creates
         ▼
┌──────────────────────────────────────────────────────┐
│ Pipeline(parser, chunker, embedder, store, compiler) │
│                                                       │
│   Path ──▶ parser.parse() ──▶ ParseResult            │
│                ──▶ chunker.chunk() ──▶ list[Chunk]    │
│                ──▶ embedder.embed() ──▶ list[EmbChunk]│
│                ──▶ store.add()                        │
│                ──▶ compiler.compile()                 │
└──────────────────────────────────────────────────────┘
```

Each ABC defines **one** abstract method (the primary operation) plus optional hooks. Data flows through frozen dataclasses between stages.

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | Define pipeline data contracts | `src/hwcc/types.py` | `ParseResult`, `Chunk`, `ChunkMetadata`, `EmbeddedChunk` as `@dataclass(frozen=True)` |
| 2 | Add pipeline exception types | `src/hwcc/exceptions.py` | Add `ParseError`, `ChunkError`, `EmbeddingError`, `StoreError`, `CompileError`, `PipelineError`, `PluginError` |
| 3 | Create parser ABC | `src/hwcc/ingest/base.py` | `BaseParser` with `parse(path, config) -> ParseResult` and `supported_extensions() -> set[str]` |
| 4 | Create chunker ABC | `src/hwcc/chunk/base.py` | `BaseChunker` with `chunk(result: ParseResult) -> list[Chunk]` |
| 5 | Create embedder ABC | `src/hwcc/embed/base.py` | `BaseEmbedder` with `embed(chunks: list[Chunk]) -> list[EmbeddedChunk]` and `embed_query(text: str) -> list[float]` |
| 6 | Create store ABC | `src/hwcc/store/base.py` | `BaseStore` with `add(chunks)`, `search(query_embedding, k)`, `delete(doc_id)`, `count()` |
| 7 | Create compiler ABC | `src/hwcc/compile/base.py` | `BaseCompiler` with `compile(store, config) -> list[Path]` |
| 8 | Create provider registry | `src/hwcc/registry.py` | `ProviderRegistry` with `register(category, name, factory)` and `create(category, name, config)` |
| 9 | Create pipeline composer | `src/hwcc/pipeline.py` | `Pipeline` class with constructor injection; `process(path)` orchestrates parse → chunk → embed → store |
| 10 | Update subpackage `__init__.py` | 5 files | Export ABCs from each subpackage |
| 11 | Write tests | `tests/test_types.py`, `tests/test_registry.py`, `tests/test_pipeline.py` | Test data contracts, registry CRUD, pipeline with mock providers |

## Detailed Design

### 1. `src/hwcc/types.py` — Pipeline Data Contracts

```python
@dataclass(frozen=True)
class ChunkMetadata:
    doc_id: str
    doc_type: str = ""
    chip: str = ""
    section_path: str = ""
    page: int = 0
    chunk_level: str = "detail"  # "summary" | "detail"
    peripheral: str = ""
    content_type: str = ""  # "register_description" | "table" | "prose" | ...

@dataclass(frozen=True)
class ParseResult:
    doc_id: str
    content: str          # Clean markdown
    doc_type: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    title: str = ""
    source_path: str = ""

@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    content: str
    token_count: int
    metadata: ChunkMetadata

@dataclass(frozen=True)
class EmbeddedChunk:
    chunk: Chunk
    embedding: tuple[float, ...]  # tuple for hashability (frozen)

@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float
    distance: float = 0.0
```

### 2. ABC Signatures

**BaseParser:**
```python
class BaseParser(ABC):
    @abstractmethod
    def parse(self, path: Path, config: HwccConfig) -> ParseResult: ...

    @abstractmethod
    def supported_extensions(self) -> frozenset[str]: ...

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in self.supported_extensions()
```

**BaseChunker:**
```python
class BaseChunker(ABC):
    @abstractmethod
    def chunk(self, result: ParseResult, config: HwccConfig) -> list[Chunk]: ...
```

**BaseEmbedder:**
```python
class BaseEmbedder(ABC):
    @abstractmethod
    def embed_chunks(self, chunks: list[Chunk]) -> list[EmbeddedChunk]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...
```

**BaseStore:**
```python
class BaseStore(ABC):
    @abstractmethod
    def add(self, chunks: list[EmbeddedChunk], doc_id: str) -> int: ...

    @abstractmethod
    def search(self, query_embedding: list[float], k: int = 5, where: dict[str, str] | None = None) -> list[SearchResult]: ...

    @abstractmethod
    def delete(self, doc_id: str) -> int: ...

    @abstractmethod
    def count(self) -> int: ...
```

**BaseCompiler:**
```python
class BaseCompiler(ABC):
    @abstractmethod
    def compile(self, store: BaseStore, config: HwccConfig) -> list[Path]: ...
```

### 3. `ProviderRegistry`

```python
ProviderFactory = Callable[[HwccConfig], Any]

class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, dict[str, ProviderFactory]] = {}

    def register(self, category: str, name: str, factory: ProviderFactory) -> None: ...
    def create(self, category: str, name: str, config: HwccConfig) -> Any: ...
    def list_providers(self, category: str) -> list[str]: ...
    def has_provider(self, category: str, name: str) -> bool: ...

# Module-level default registry
default_registry = ProviderRegistry()
```

### 4. `Pipeline`

```python
class Pipeline:
    def __init__(
        self,
        parser: BaseParser,
        chunker: BaseChunker,
        embedder: BaseEmbedder,
        store: BaseStore,
        config: HwccConfig,
    ) -> None: ...

    def process(self, path: Path, doc_id: str, doc_type: str = "", chip: str = "") -> int:
        """Full pipeline: parse → chunk → embed → store. Returns chunk count."""
        ...

    def remove(self, doc_id: str) -> int:
        """Remove a document from the store. Returns chunks removed."""
        ...
```

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | Frozen dataclasses are immutable | `tests/test_types.py` | unit |
| 2 | ChunkMetadata defaults are correct | `tests/test_types.py` | unit |
| 3 | EmbeddedChunk uses tuple for embedding | `tests/test_types.py` | unit |
| 4 | SearchResult holds chunk and score | `tests/test_types.py` | unit |
| 5 | Registry register and create round-trip | `tests/test_registry.py` | unit |
| 6 | Registry create with unknown name raises error | `tests/test_registry.py` | unit |
| 7 | Registry create with unknown category raises error | `tests/test_registry.py` | unit |
| 8 | Registry list_providers returns registered names | `tests/test_registry.py` | unit |
| 9 | Registry has_provider returns correct boolean | `tests/test_registry.py` | unit |
| 10 | Pipeline.process calls all stages in order | `tests/test_pipeline.py` | unit |
| 11 | Pipeline.process returns chunk count from store | `tests/test_pipeline.py` | unit |
| 12 | Pipeline.remove delegates to store | `tests/test_pipeline.py` | unit |
| 13 | Pipeline works with mock providers (testability proof) | `tests/test_pipeline.py` | integration |
| 14 | BaseParser.can_parse checks extension correctly | `tests/test_pipeline.py` | unit |
| 15 | ABC raises TypeError on direct instantiation | `tests/test_pipeline.py` | unit |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | Create a mock parser, chunker, embedder, store | All instantiate without error | automated |
| 2 | Run Pipeline.process with mock providers | Returns chunk count, all stages called | automated |
| 3 | Registry register + create | Returns correct provider instance | automated |
| 4 | Attempt to instantiate ABC directly | TypeError raised | automated |
| 5 | Frozen dataclass mutation attempt | FrozenInstanceError raised | automated |

## Files to Create
| File | Purpose |
|------|---------|
| `src/hwcc/types.py` | Pipeline data contracts (ParseResult, Chunk, EmbeddedChunk, SearchResult) |
| `src/hwcc/ingest/base.py` | BaseParser ABC |
| `src/hwcc/chunk/base.py` | BaseChunker ABC |
| `src/hwcc/embed/base.py` | BaseEmbedder ABC |
| `src/hwcc/store/base.py` | BaseStore ABC |
| `src/hwcc/compile/base.py` | BaseCompiler ABC |
| `src/hwcc/registry.py` | ProviderRegistry (config string → factory → instance) |
| `src/hwcc/pipeline.py` | Pipeline class (composes stages via constructor injection) |
| `tests/test_types.py` | Tests for pipeline data contracts |
| `tests/test_registry.py` | Tests for provider registry |
| `tests/test_pipeline.py` | Tests for pipeline composition with mocks |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/exceptions.py` | modify | Add 7 new exception types |
| `src/hwcc/ingest/__init__.py` | modify | Export `BaseParser` |
| `src/hwcc/chunk/__init__.py` | modify | Export `BaseChunker` |
| `src/hwcc/embed/__init__.py` | modify | Export `BaseEmbedder` |
| `src/hwcc/store/__init__.py` | modify | Export `BaseStore` |
| `src/hwcc/compile/__init__.py` | modify | Export `BaseCompiler` |

## Exit Criteria
```
[ ] All 8 new source files created and pass lint/type checks
[ ] All 5 subpackage __init__.py files updated with ABC exports
[ ] exceptions.py extended with 7 new exception types
[ ] 15+ new tests pass
[ ] Existing 61 tests still pass (no regressions)
[ ] ruff check passes
[ ] mypy passes
[ ] Pipeline is composable with mock providers (testability proven)
[ ] All changes within declared scope (no scope creep)
[ ] NON-GOALS remain untouched (no concrete implementations)
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Format passes: `ruff format --check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No unintended side effects in: config.py, manifest.py, project.py, cli.py
- [ ] Manual test: `hwcc init` and `hwcc status` still work

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None (architecture already described there)
- [ ] **PLAN.md:** Mark as Phase 0.5 addendum if desired

---

> **Last Updated:** 2026-02-27

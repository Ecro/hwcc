# Plan: ChromaDB 내장 임베딩 제공자 추가 및 기본값 변경

## Scope Declaration
- **Type:** feature
- **Single Concern:** ChromaDB의 내장 임베딩 함수를 BaseEmbedder로 래핑하여 새 제공자로 추가하고, 기본값을 Ollama에서 ChromaDB로 변경
- **Phase:** Phase 1 (Ingest)
- **Complexity:** Low
- **Risk:** Low

## Problem Statement
**What:** Ollama 없이 임베딩을 생성할 수 있는 ChromaDB 내장 임베딩 제공자 추가
**Why:** 현재 기본 임베딩에 Ollama 설치(~4GB)가 필요하여 진입 장벽이 높음. ChromaDB는 이미 의존성이므로 추가 설치 없이 임베딩 가능
**Success:** `pip install hwcc` 후 Ollama 없이 `hwcc add` 동작. 기존 Ollama/OpenAI 제공자는 그대로 유지

## Impact Analysis

### Direct Changes
| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/hwcc/embed/chromadb_embed.py` | create | `ChromaDBEmbedder` 클래스 — ChromaDB DefaultEmbeddingFunction 래핑 |
| `src/hwcc/embed/__init__.py` | modify | import 추가 + registry에 `"chromadb"` 등록 |
| `src/hwcc/config.py` | modify | `EmbeddingConfig.provider` 기본값 `"ollama"` → `"chromadb"`, `model` 기본값 `"all-MiniLM-L6-v2"` |
| `tests/test_embed.py` | modify | `ChromaDBEmbedder` 테스트 추가 |

### Dependency Chain
| Modified Code | Callers | Callees |
|--------------|---------|---------|
| `ChromaDBEmbedder` | `cli.py:213` (registry.create) | `chromadb.utils.embedding_functions.DefaultEmbeddingFunction` |
| `EmbeddingConfig` defaults | `config.py`, `cli.py`, `project.py` | N/A (data only) |

### Pipeline Impact
| Pipeline Stage | Upstream Impact | Downstream Impact |
|---------------|-----------------|-------------------|
| Embed | 없음 (새 제공자 추가) | Store — 차원 384로 변경 (기존 768과 비호환, 재인덱싱 필요) |

## NON-GOALS (Explicitly Out of Scope)
- [ ] `src/hwcc/store/chroma.py` — Store 계층 변경 없음
- [ ] `src/hwcc/cli.py` — CLI 로직 변경 없음
- [ ] `src/hwcc/pipeline.py` — Pipeline 구조 변경 없음
- [ ] fastembed 제공자 추가 — 별도 PR
- [ ] 기존 Ollama/OpenAI 제공자 수정 또는 삭제 — 그대로 유지

## Technical Approach

### ChromaDB DefaultEmbeddingFunction 래핑

ChromaDB는 `DefaultEmbeddingFunction`을 제공함 (ONNX + all-MiniLM-L6-v2, 384차원). 이걸 `BaseEmbedder` ABC로 래핑:

```python
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

class ChromaDBEmbedder(BaseEmbedder):
    def __init__(self, config: HwccConfig) -> None:
        self._ef = DefaultEmbeddingFunction()
        self._dimension: int | None = None

    def embed_chunks(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        texts = [c.content for c in chunks]
        vectors = self._ef(texts)  # DefaultEmbeddingFunction is callable
        return [EmbeddedChunk(chunk=c, embedding=tuple(v)) for c, v in zip(chunks, vectors)]

    def embed_query(self, text: str) -> list[float]:
        vectors = self._ef([text])
        return list(vectors[0])

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            vec = self.embed_query("dimension probe")
            self._dimension = len(vec)
        return self._dimension
```

**장점:**
- 추가 의존성 0 (ChromaDB에 이미 포함)
- 네트워크 호출 없음 (ONNX 로컬 실행)
- 모델 자동 다운로드 (~80MB, 최초 1회)
- 파이프라인 아키텍처 변경 없음

**주의:**
- 기존 Ollama 임베딩(768차원)과 새 ChromaDB 임베딩(384차원) 비호환 → 기존 인덱스는 재인덱싱 필요
- 이는 운영 문제이며, 경고 로그로 안내

## Implementation Steps

| # | Task | File(s) | Description |
|---|------|---------|-------------|
| 1 | ChromaDBEmbedder 클래스 생성 | `src/hwcc/embed/chromadb_embed.py` | DefaultEmbeddingFunction을 BaseEmbedder로 래핑. 배치 처리, 에러 핸들링 포함 |
| 2 | Registry에 등록 | `src/hwcc/embed/__init__.py` | import 추가, `"chromadb"` 이름으로 등록, `__all__` 업데이트 |
| 3 | 기본값 변경 | `src/hwcc/config.py` | `EmbeddingConfig.provider` → `"chromadb"`, `EmbeddingConfig.model` → `"all-MiniLM-L6-v2"` |
| 4 | 테스트 작성 | `tests/test_embed.py` | init, embed_chunks, embed_query, dimension, empty input, error cases, registry 통합 |

## Test Plan

### Unit Tests
| # | Test Description | File | Type |
|---|-----------------|------|------|
| 1 | ChromaDBEmbedder가 BaseEmbedder 인스턴스인지 | `tests/test_embed.py` | unit |
| 2 | 단일 청크 임베딩 반환값 검증 (EmbeddedChunk, tuple embedding) | `tests/test_embed.py` | unit |
| 3 | 다수 청크 임베딩 — 입력과 출력 길이 일치 | `tests/test_embed.py` | unit |
| 4 | 빈 입력 시 빈 리스트 반환 | `tests/test_embed.py` | unit |
| 5 | embed_query가 list[float] 반환 | `tests/test_embed.py` | unit |
| 6 | dimension 프로퍼티 정확성 (384) | `tests/test_embed.py` | unit |
| 7 | DefaultEmbeddingFunction 실패 시 EmbeddingError 발생 | `tests/test_embed.py` | unit |
| 8 | Registry에서 "chromadb" 이름으로 생성 가능 | `tests/test_embed.py` | integration |
| 9 | 기본 config로 생성 시 ChromaDBEmbedder 반환 | `tests/test_embed.py` | integration |

### Acceptance Criteria (Testable)
| # | Scenario | Expected Result | Test Type |
|---|----------|----------------|-----------|
| 1 | `HwccConfig()` 생성 | `config.embedding.provider == "chromadb"` | automated |
| 2 | `default_registry.create("embedding", "chromadb", config)` | `ChromaDBEmbedder` 인스턴스 반환 | automated |
| 3 | `embedder.embed_chunks([chunk])` | 384차원 벡터가 포함된 EmbeddedChunk 반환 | automated |
| 4 | 기존 "ollama" 제공자 | 여전히 registry에서 생성 가능 | automated |

## Files to Modify
| File | Change Type | Description |
|------|-------------|-------------|
| `src/hwcc/embed/__init__.py` | modify | ChromaDBEmbedder import + registry 등록 |
| `src/hwcc/config.py` | modify | EmbeddingConfig 기본값 변경 |
| `tests/test_embed.py` | modify | ChromaDBEmbedder 테스트 추가 |

## Files to Create
| File | Purpose |
|------|---------|
| `src/hwcc/embed/chromadb_embed.py` | ChromaDB 내장 임베딩 제공자 |

## Exit Criteria
```
□ ChromaDBEmbedder가 BaseEmbedder ABC를 구현
□ config 기본값이 provider="chromadb"
□ 기존 ollama/openai 제공자 그대로 동작
□ 모든 테스트 통과
□ ruff check / ruff format 통과
□ mypy 통과
□ NON-GOALS 영역 변경 없음
```

## Verification Strategy
- [ ] Tests pass: `pytest tests/test_embed.py -v`
- [ ] All tests pass: `pytest tests/`
- [ ] Lint passes: `ruff check src/ tests/`
- [ ] Format correct: `ruff format --check src/ tests/`
- [ ] Types correct: `mypy src/hwcc/`
- [ ] No unintended side effects in: store, CLI, pipeline

## Document Updates Needed
- [ ] **TECH_SPEC.md:** None (provider 추가는 설계대로)
- [ ] **PLAN.md:** None

---

> **Last Updated:** 2026-02-28

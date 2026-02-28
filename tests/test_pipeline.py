"""Tests for hwcc.pipeline module — pipeline orchestration with mocks."""

from __future__ import annotations

from pathlib import Path

import pytest

from hwcc.chunk.base import BaseChunker
from hwcc.compile.base import BaseCompiler
from hwcc.config import HwccConfig
from hwcc.embed.base import BaseEmbedder
from hwcc.exceptions import PipelineError
from hwcc.ingest.base import BaseParser
from hwcc.pipeline import Pipeline
from hwcc.store.base import BaseStore
from hwcc.types import Chunk, ChunkMetadata, EmbeddedChunk, ParseResult, SearchResult

# --- Mock implementations ---


class MockParser(BaseParser):
    def __init__(self) -> None:
        self.parse_calls: list[Path] = []

    def parse(self, path: Path, config: HwccConfig) -> ParseResult:
        self.parse_calls.append(path)
        return ParseResult(
            doc_id="test_doc",
            content="# Parsed content",
            doc_type="datasheet",
            source_path=str(path),
        )

    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".pdf", ".svd"})


class MockChunker(BaseChunker):
    def __init__(self) -> None:
        self.chunk_calls: list[str] = []

    def chunk(self, result: ParseResult, config: HwccConfig) -> list[Chunk]:
        self.chunk_calls.append(result.doc_id)
        meta = ChunkMetadata(doc_id=result.doc_id, doc_type=result.doc_type, chip=result.chip)
        return [
            Chunk(chunk_id="c1", content="chunk 1", token_count=10, metadata=meta),
            Chunk(chunk_id="c2", content="chunk 2", token_count=15, metadata=meta),
        ]


class MockEmbedder(BaseEmbedder):
    def __init__(self) -> None:
        self.embed_calls: list[int] = []

    def embed_chunks(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        self.embed_calls.append(len(chunks))
        return [EmbeddedChunk(chunk=c, embedding=(0.1, 0.2, 0.3)) for c in chunks]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    @property
    def dimension(self) -> int:
        return 3


class MockStore(BaseStore):
    def __init__(self) -> None:
        self.stored: dict[str, list[EmbeddedChunk]] = {}
        self.add_calls: list[str] = []

    def add(self, chunks: list[EmbeddedChunk], doc_id: str) -> int:
        self.add_calls.append(doc_id)
        self.stored[doc_id] = chunks
        return len(chunks)

    def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        where: dict[str, str] | None = None,
    ) -> list[SearchResult]:
        return []

    def delete(self, doc_id: str) -> int:
        if doc_id in self.stored:
            count = len(self.stored.pop(doc_id))
            return count
        return 0

    def get_chunk_metadata(
        self,
        where: dict[str, str] | None = None,
    ) -> list[ChunkMetadata]:
        return []

    def get_chunks(
        self,
        where: dict[str, str] | None = None,
    ) -> list[Chunk]:
        return []

    def count(self) -> int:
        return sum(len(v) for v in self.stored.values())


class MockCompiler(BaseCompiler):
    def compile(self, store: BaseStore, config: HwccConfig) -> list[Path]:
        return [Path(".rag/context/hot.md")]


# --- Fixture ---


def _make_pipeline() -> tuple[Pipeline, MockParser, MockChunker, MockEmbedder, MockStore]:
    parser = MockParser()
    chunker = MockChunker()
    embedder = MockEmbedder()
    store = MockStore()
    config = HwccConfig()
    pipeline = Pipeline(
        parser=parser,
        chunker=chunker,
        embedder=embedder,
        store=store,
        config=config,
    )
    return pipeline, parser, chunker, embedder, store


# --- Tests ---


class TestPipelineProcess:
    def test_process_calls_all_stages(self, tmp_path: Path):
        pipeline, parser, chunker, embedder, store = _make_pipeline()
        doc_path = tmp_path / "test.pdf"
        doc_path.write_text("dummy", encoding="utf-8")

        count = pipeline.process(doc_path, doc_id="test_doc")

        assert count == 2
        assert len(parser.parse_calls) == 1
        assert len(chunker.chunk_calls) == 1
        assert len(embedder.embed_calls) == 1
        assert len(store.add_calls) == 1

    def test_process_returns_chunk_count(self, tmp_path: Path):
        pipeline, _, _, _, _ = _make_pipeline()
        doc_path = tmp_path / "test.svd"
        doc_path.write_text("dummy", encoding="utf-8")

        count = pipeline.process(doc_path, doc_id="test_doc")
        assert count == 2

    def test_process_wraps_exceptions_in_pipeline_error(self, tmp_path: Path):
        parser = MockParser()
        chunker = MockChunker()
        embedder = MockEmbedder()
        store = MockStore()
        config = HwccConfig()

        # Make parser raise
        def broken_parse(path: Path, config: HwccConfig) -> ParseResult:
            msg = "parse failed"
            raise ValueError(msg)

        parser.parse = broken_parse  # type: ignore[assignment]

        pipeline = Pipeline(
            parser=parser,
            chunker=chunker,
            embedder=embedder,
            store=store,
            config=config,
        )
        doc_path = tmp_path / "test.pdf"
        doc_path.write_text("dummy", encoding="utf-8")

        with pytest.raises(PipelineError, match="parse failed"):
            pipeline.process(doc_path, doc_id="test_doc")

    def test_process_applies_doc_type_and_chip_overrides(self, tmp_path: Path):
        """Pipeline.process() should forward doc_type/chip to ParseResult before chunking."""
        pipeline, _, chunker, _, store = _make_pipeline()
        doc_path = tmp_path / "test.pdf"
        doc_path.write_text("dummy", encoding="utf-8")

        pipeline.process(doc_path, doc_id="test_doc", doc_type="errata", chip="NRF52840")

        # Verify the chunks in the store have the overridden metadata
        stored_chunks = store.stored["test_doc"]
        for ec in stored_chunks:
            assert ec.chunk.metadata.doc_type == "errata"
            assert ec.chunk.metadata.chip == "NRF52840"


class TestPipelineRemove:
    def test_remove_delegates_to_store(self):
        pipeline, _, _, _, store = _make_pipeline()
        # Pre-populate store
        meta = ChunkMetadata(doc_id="doc1")
        chunk = Chunk(chunk_id="c1", content="text", token_count=10, metadata=meta)
        embedded = EmbeddedChunk(chunk=chunk, embedding=(0.1,))
        store.stored["doc1"] = [embedded]

        count = pipeline.remove("doc1")
        assert count == 1
        assert "doc1" not in store.stored

    def test_remove_nonexistent_returns_zero(self):
        pipeline, _, _, _, _ = _make_pipeline()
        count = pipeline.remove("nonexistent")
        assert count == 0


class TestABCEnforcement:
    def test_cannot_instantiate_base_parser(self):
        with pytest.raises(TypeError):
            BaseParser()  # type: ignore[abstract]

    def test_cannot_instantiate_base_chunker(self):
        with pytest.raises(TypeError):
            BaseChunker()  # type: ignore[abstract]

    def test_cannot_instantiate_base_embedder(self):
        with pytest.raises(TypeError):
            BaseEmbedder()  # type: ignore[abstract]

    def test_cannot_instantiate_base_store(self):
        with pytest.raises(TypeError):
            BaseStore()  # type: ignore[abstract]

    def test_cannot_instantiate_base_compiler(self):
        with pytest.raises(TypeError):
            BaseCompiler()  # type: ignore[abstract]


class TestBaseParserCanParse:
    def test_can_parse_matching_extension(self):
        parser = MockParser()
        assert parser.can_parse(Path("board.pdf")) is True
        assert parser.can_parse(Path("chip.svd")) is True

    def test_can_parse_case_insensitive(self):
        parser = MockParser()
        assert parser.can_parse(Path("BOARD.PDF")) is True

    def test_cannot_parse_wrong_extension(self):
        parser = MockParser()
        assert parser.can_parse(Path("readme.md")) is False


class TestMockProviderTestability:
    """Prove that the architecture is testable with mock providers."""

    def test_full_pipeline_with_mocks(self, tmp_path: Path):
        pipeline, _parser, _chunker, _embedder, store = _make_pipeline()
        doc_path = tmp_path / "test.svd"
        doc_path.write_text("<device/>", encoding="utf-8")

        count = pipeline.process(doc_path, doc_id="board_svd")
        assert count == 2
        assert store.count() == 2

        # Now remove
        removed = pipeline.remove("board_svd")
        assert removed == 2
        assert store.count() == 0

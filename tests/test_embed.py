"""Tests for hwcc.embed — ChromaDBEmbedder, OllamaEmbedder, and OpenAICompatEmbedder."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from hwcc.config import HwccConfig
from hwcc.embed.base import BaseEmbedder
from hwcc.embed.chromadb_embed import ChromaDBEmbedder
from hwcc.embed.ollama import OllamaEmbedder
from hwcc.embed.openai_compat import OpenAICompatEmbedder
from hwcc.exceptions import EmbeddingError
from hwcc.types import Chunk, ChunkMetadata, EmbeddedChunk

# --- Helpers ---

_FAKE_VECTOR = [0.1, 0.2, 0.3, 0.4, 0.5]


def _make_chunk(content: str = "test content", doc_id: str = "doc1") -> Chunk:
    """Create a minimal Chunk for testing."""
    meta = ChunkMetadata(doc_id=doc_id)
    return Chunk(chunk_id=f"{doc_id}_c1", content=content, token_count=5, metadata=meta)


def _make_chunks(n: int) -> list[Chunk]:
    """Create n chunks for batching tests."""
    return [
        Chunk(
            chunk_id=f"doc_c{i}",
            content=f"chunk {i}",
            token_count=5,
            metadata=ChunkMetadata(doc_id="doc"),
        )
        for i in range(n)
    ]


def _ollama_response(embeddings: list[list[float]]) -> bytes:
    """Build a mock Ollama /api/embed response body."""
    return json.dumps({"embeddings": embeddings}).encode("utf-8")


def _openai_response(embeddings: list[list[float]]) -> bytes:
    """Build a mock OpenAI /v1/embeddings response body."""
    data = [{"object": "embedding", "index": i, "embedding": e} for i, e in enumerate(embeddings)]
    return json.dumps({"object": "list", "data": data, "model": "test"}).encode("utf-8")


class _FakeResponse:
    """Minimal mock for urllib.request.urlopen return value."""

    def __init__(self, data: bytes, status: int = 200) -> None:
        self._data = data
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


# --- ChromaDBEmbedder Tests ---


def _mock_ef(texts):
    """Mock ChromaDB DefaultEmbeddingFunction returning 384-dim vectors."""
    return [[0.1] * 384 for _ in texts]


class TestChromaDBEmbedderInit:
    def test_is_base_embedder(self):
        config = HwccConfig()
        with patch(
            "hwcc.embed.chromadb_embed.DefaultEmbeddingFunction",
            return_value=MagicMock(side_effect=_mock_ef),
        ):
            embedder = ChromaDBEmbedder(config)
        assert isinstance(embedder, BaseEmbedder)

    def test_warns_on_unsupported_model(self, caplog):
        config = HwccConfig()
        config.embedding.model = "bge-large-en"
        with patch(
            "hwcc.embed.chromadb_embed.DefaultEmbeddingFunction",
            return_value=MagicMock(side_effect=_mock_ef),
        ):
            ChromaDBEmbedder(config)
        assert "ignoring model='bge-large-en'" in caplog.text

    def test_no_warning_on_default_model(self, caplog):
        config = HwccConfig()
        with patch(
            "hwcc.embed.chromadb_embed.DefaultEmbeddingFunction",
            return_value=MagicMock(side_effect=_mock_ef),
        ):
            ChromaDBEmbedder(config)
        assert "ignoring model" not in caplog.text

    def test_raises_on_init_failure(self):
        config = HwccConfig()
        with (
            patch(
                "hwcc.embed.chromadb_embed.DefaultEmbeddingFunction",
                side_effect=RuntimeError("ONNX not available"),
            ),
            pytest.raises(EmbeddingError, match="Failed to initialize"),
        ):
            ChromaDBEmbedder(config)


class TestChromaDBEmbedChunks:
    def _make_embedder(self):
        config = HwccConfig()
        mock_ef = MagicMock(side_effect=_mock_ef)
        with patch(
            "hwcc.embed.chromadb_embed.DefaultEmbeddingFunction",
            return_value=mock_ef,
        ):
            return ChromaDBEmbedder(config)

    def test_embeds_single_chunk(self):
        embedder = self._make_embedder()
        chunk = _make_chunk()
        result = embedder.embed_chunks([chunk])

        assert len(result) == 1
        assert isinstance(result[0], EmbeddedChunk)
        assert result[0].chunk is chunk
        assert len(result[0].embedding) == 384
        assert isinstance(result[0].embedding, tuple)

    def test_embeds_multiple_chunks(self):
        embedder = self._make_embedder()
        chunks = _make_chunks(5)
        result = embedder.embed_chunks(chunks)

        assert len(result) == 5
        for i, ec in enumerate(result):
            assert ec.chunk is chunks[i]

    def test_empty_chunks_returns_empty(self):
        embedder = self._make_embedder()
        result = embedder.embed_chunks([])
        assert result == []

    def test_raises_on_embedding_failure(self):
        config = HwccConfig()
        mock_ef = MagicMock(side_effect=RuntimeError("ONNX error"))
        with patch(
            "hwcc.embed.chromadb_embed.DefaultEmbeddingFunction",
            return_value=mock_ef,
        ):
            embedder = ChromaDBEmbedder(config)

        chunk = _make_chunk()
        with pytest.raises(EmbeddingError, match="ChromaDB embedding failed"):
            embedder.embed_chunks([chunk])

    def test_raises_on_count_mismatch(self):
        config = HwccConfig()
        # Return wrong number of embeddings
        mock_ef = MagicMock(return_value=[[0.1] * 384, [0.2] * 384])
        with patch(
            "hwcc.embed.chromadb_embed.DefaultEmbeddingFunction",
            return_value=mock_ef,
        ):
            embedder = ChromaDBEmbedder(config)

        chunks = _make_chunks(3)
        with pytest.raises(EmbeddingError, match="3 inputs"):
            embedder.embed_chunks(chunks)


class TestChromaDBEmbedQuery:
    def test_returns_vector(self):
        config = HwccConfig()
        mock_ef = MagicMock(side_effect=_mock_ef)
        with patch(
            "hwcc.embed.chromadb_embed.DefaultEmbeddingFunction",
            return_value=mock_ef,
        ):
            embedder = ChromaDBEmbedder(config)

        result = embedder.embed_query("SPI configuration")
        assert isinstance(result, list)
        assert len(result) == 384

    def test_raises_on_error(self):
        config = HwccConfig()
        mock_ef = MagicMock(side_effect=RuntimeError("fail"))
        with patch(
            "hwcc.embed.chromadb_embed.DefaultEmbeddingFunction",
            return_value=mock_ef,
        ):
            embedder = ChromaDBEmbedder(config)

        with pytest.raises(EmbeddingError, match="query embedding failed"):
            embedder.embed_query("test")


class TestChromaDBDimension:
    def test_returns_384(self):
        config = HwccConfig()
        mock_ef = MagicMock(side_effect=_mock_ef)
        with patch(
            "hwcc.embed.chromadb_embed.DefaultEmbeddingFunction",
            return_value=mock_ef,
        ):
            embedder = ChromaDBEmbedder(config)

        assert embedder.dimension == 384

    def test_caches_dimension_after_embed(self):
        config = HwccConfig()
        mock_ef = MagicMock(side_effect=_mock_ef)
        with patch(
            "hwcc.embed.chromadb_embed.DefaultEmbeddingFunction",
            return_value=mock_ef,
        ):
            embedder = ChromaDBEmbedder(config)

        embedder.embed_chunks([_make_chunk()])
        # Second call should use cached value, not call embed_query
        assert embedder.dimension == 384


# --- OllamaEmbedder Tests ---


class TestOllamaEmbedderInit:
    def test_uses_default_base_url(self):
        config = HwccConfig()
        embedder = OllamaEmbedder(config)
        assert embedder._base_url == "http://localhost:11434"

    def test_uses_custom_base_url(self):
        config = HwccConfig()
        config.embedding.base_url = "http://gpu-server:11434"
        embedder = OllamaEmbedder(config)
        assert embedder._base_url == "http://gpu-server:11434"

    def test_strips_trailing_slash(self):
        config = HwccConfig()
        config.embedding.base_url = "http://gpu-server:11434/"
        embedder = OllamaEmbedder(config)
        assert embedder._base_url == "http://gpu-server:11434"

    def test_is_base_embedder(self):
        config = HwccConfig()
        embedder = OllamaEmbedder(config)
        assert isinstance(embedder, BaseEmbedder)


class TestOllamaEmbedChunks:
    def test_embeds_single_chunk(self):
        config = HwccConfig()
        embedder = OllamaEmbedder(config)
        chunk = _make_chunk()
        response = _FakeResponse(_ollama_response([_FAKE_VECTOR]))

        with patch("hwcc.embed.ollama.urlopen", return_value=response):
            result = embedder.embed_chunks([chunk])

        assert len(result) == 1
        assert isinstance(result[0], EmbeddedChunk)
        assert result[0].chunk is chunk
        assert result[0].embedding == tuple(_FAKE_VECTOR)

    def test_embeds_multiple_chunks(self):
        config = HwccConfig()
        config.embedding.batch_size = 10
        embedder = OllamaEmbedder(config)
        chunks = _make_chunks(3)
        vecs = [_FAKE_VECTOR] * 3
        response = _FakeResponse(_ollama_response(vecs))

        with patch("hwcc.embed.ollama.urlopen", return_value=response):
            result = embedder.embed_chunks(chunks)

        assert len(result) == 3
        for i, ec in enumerate(result):
            assert ec.chunk is chunks[i]

    def test_respects_batch_size(self):
        config = HwccConfig()
        config.embedding.batch_size = 2
        embedder = OllamaEmbedder(config)
        chunks = _make_chunks(5)

        call_count = 0
        batch_sizes: list[int] = []

        def mock_urlopen(req, **kwargs):
            nonlocal call_count
            call_count += 1
            body = json.loads(req.data)
            n = len(body["input"])
            batch_sizes.append(n)
            return _FakeResponse(_ollama_response([_FAKE_VECTOR] * n))

        with patch("hwcc.embed.ollama.urlopen", side_effect=mock_urlopen):
            result = embedder.embed_chunks(chunks)

        assert len(result) == 5
        assert call_count == 3  # 2 + 2 + 1
        assert batch_sizes == [2, 2, 1]

    def test_empty_chunks_returns_empty(self):
        config = HwccConfig()
        embedder = OllamaEmbedder(config)
        result = embedder.embed_chunks([])
        assert result == []

    def test_raises_on_connection_error(self):
        config = HwccConfig()
        embedder = OllamaEmbedder(config)
        chunk = _make_chunk()

        with (
            patch("hwcc.embed.ollama.urlopen", side_effect=ConnectionError("Connection refused")),
            pytest.raises(EmbeddingError, match="Ollama"),
        ):
            embedder.embed_chunks([chunk])

    def test_raises_on_http_error(self):
        from urllib.error import HTTPError

        config = HwccConfig()
        embedder = OllamaEmbedder(config)
        chunk = _make_chunk()

        err = HTTPError("http://localhost:11434/api/embed", 500, "Server Error", {}, None)
        with (
            patch("hwcc.embed.ollama.urlopen", side_effect=err),
            pytest.raises(EmbeddingError, match="500"),
        ):
            embedder.embed_chunks([chunk])


class TestOllamaEmbedQuery:
    def test_returns_vector(self):
        config = HwccConfig()
        embedder = OllamaEmbedder(config)
        response = _FakeResponse(_ollama_response([_FAKE_VECTOR]))

        with patch("hwcc.embed.ollama.urlopen", return_value=response):
            result = embedder.embed_query("test query")

        assert result == _FAKE_VECTOR

    def test_raises_on_error(self):
        config = HwccConfig()
        embedder = OllamaEmbedder(config)

        with (
            patch("hwcc.embed.ollama.urlopen", side_effect=ConnectionError("refused")),
            pytest.raises(EmbeddingError),
        ):
            embedder.embed_query("test")


class TestOllamaDimension:
    def test_returns_dimension_after_embed(self):
        config = HwccConfig()
        embedder = OllamaEmbedder(config)
        response = _FakeResponse(_ollama_response([_FAKE_VECTOR]))

        with patch("hwcc.embed.ollama.urlopen", return_value=response):
            embedder.embed_query("probe")

        assert embedder.dimension == 5

    def test_probes_dimension_if_unknown(self):
        config = HwccConfig()
        embedder = OllamaEmbedder(config)
        response = _FakeResponse(_ollama_response([_FAKE_VECTOR]))

        with patch("hwcc.embed.ollama.urlopen", return_value=response):
            dim = embedder.dimension

        assert dim == 5


# --- OpenAICompatEmbedder Tests ---


class TestOpenAICompatInit:
    def test_uses_default_base_url(self):
        config = HwccConfig()
        config.embedding.provider = "openai"
        config.embedding.api_key_env = "TEST_KEY"
        with patch.dict(os.environ, {"TEST_KEY": "sk-test"}):
            embedder = OpenAICompatEmbedder(config)
        assert embedder._base_url == "https://api.openai.com/v1"

    def test_uses_custom_base_url(self):
        config = HwccConfig()
        config.embedding.base_url = "http://localhost:8080/v1"
        config.embedding.api_key_env = ""
        embedder = OpenAICompatEmbedder(config)
        assert embedder._base_url == "http://localhost:8080/v1"

    def test_is_base_embedder(self):
        config = HwccConfig()
        config.embedding.api_key_env = ""
        embedder = OpenAICompatEmbedder(config)
        assert isinstance(embedder, BaseEmbedder)


class TestOpenAICompatEmbedChunks:
    def test_embeds_chunks_with_api_key(self):
        config = HwccConfig()
        config.embedding.api_key_env = "TEST_KEY"
        config.embedding.model = "text-embedding-3-small"

        with patch.dict(os.environ, {"TEST_KEY": "sk-test"}):
            embedder = OpenAICompatEmbedder(config)

        chunk = _make_chunk()
        response = _FakeResponse(_openai_response([_FAKE_VECTOR]))

        def mock_urlopen(req, **kwargs):
            # Verify auth header is set
            assert req.get_header("Authorization") == "Bearer sk-test"
            return response

        with patch("hwcc.embed.openai_compat.urlopen", side_effect=mock_urlopen):
            result = embedder.embed_chunks([chunk])

        assert len(result) == 1
        assert result[0].embedding == tuple(_FAKE_VECTOR)

    def test_works_without_api_key(self):
        """Some OpenAI-compat servers (vLLM, LiteLLM) don't need API keys."""
        config = HwccConfig()
        config.embedding.api_key_env = ""
        config.embedding.base_url = "http://localhost:8080/v1"

        embedder = OpenAICompatEmbedder(config)
        chunk = _make_chunk()
        response = _FakeResponse(_openai_response([_FAKE_VECTOR]))

        def mock_urlopen(req, **kwargs):
            assert req.get_header("Authorization") is None
            return response

        with patch("hwcc.embed.openai_compat.urlopen", side_effect=mock_urlopen):
            result = embedder.embed_chunks([chunk])

        assert len(result) == 1

    def test_respects_batch_size(self):
        config = HwccConfig()
        config.embedding.batch_size = 3
        config.embedding.api_key_env = ""
        config.embedding.base_url = "http://localhost:8080/v1"
        embedder = OpenAICompatEmbedder(config)
        chunks = _make_chunks(7)

        call_count = 0
        batch_sizes: list[int] = []

        def mock_urlopen(req, **kwargs):
            nonlocal call_count
            call_count += 1
            body = json.loads(req.data)
            n = len(body["input"])
            batch_sizes.append(n)
            return _FakeResponse(_openai_response([_FAKE_VECTOR] * n))

        with patch("hwcc.embed.openai_compat.urlopen", side_effect=mock_urlopen):
            result = embedder.embed_chunks(chunks)

        assert len(result) == 7
        assert call_count == 3  # 3 + 3 + 1
        assert batch_sizes == [3, 3, 1]

    def test_empty_chunks_returns_empty(self):
        config = HwccConfig()
        config.embedding.api_key_env = ""
        embedder = OpenAICompatEmbedder(config)
        result = embedder.embed_chunks([])
        assert result == []

    def test_raises_on_http_error(self):
        from urllib.error import HTTPError

        config = HwccConfig()
        config.embedding.api_key_env = ""
        config.embedding.base_url = "http://localhost:8080/v1"
        embedder = OpenAICompatEmbedder(config)
        chunk = _make_chunk()

        err = HTTPError("http://localhost:8080/v1/embeddings", 401, "Unauthorized", {}, None)
        with (
            patch("hwcc.embed.openai_compat.urlopen", side_effect=err),
            pytest.raises(EmbeddingError, match="401"),
        ):
            embedder.embed_chunks([chunk])


class TestOpenAICompatEmbedQuery:
    def test_returns_vector(self):
        config = HwccConfig()
        config.embedding.api_key_env = ""
        config.embedding.base_url = "http://localhost:8080/v1"
        embedder = OpenAICompatEmbedder(config)
        response = _FakeResponse(_openai_response([_FAKE_VECTOR]))

        with patch("hwcc.embed.openai_compat.urlopen", return_value=response):
            result = embedder.embed_query("SPI DMA channels")

        assert result == _FAKE_VECTOR


class TestOpenAICompatDimension:
    def test_returns_dimension_after_embed(self):
        config = HwccConfig()
        config.embedding.api_key_env = ""
        config.embedding.base_url = "http://localhost:8080/v1"
        embedder = OpenAICompatEmbedder(config)
        response = _FakeResponse(_openai_response([_FAKE_VECTOR]))

        with patch("hwcc.embed.openai_compat.urlopen", return_value=response):
            embedder.embed_query("probe")

        assert embedder.dimension == 5


# --- EmbeddedChunk Contract Tests ---


class TestEmbeddedChunkContract:
    def test_embedding_is_tuple(self):
        """EmbeddedChunk.embedding must be a tuple of floats (frozen dataclass)."""
        chunk = _make_chunk()
        ec = EmbeddedChunk(chunk=chunk, embedding=tuple(_FAKE_VECTOR))
        assert isinstance(ec.embedding, tuple)
        assert all(isinstance(v, float) for v in ec.embedding)

    def test_chunk_preserved(self):
        chunk = _make_chunk()
        ec = EmbeddedChunk(chunk=chunk, embedding=(0.1, 0.2))
        assert ec.chunk.chunk_id == chunk.chunk_id
        assert ec.chunk.content == chunk.content


# --- Registry Integration Tests ---


# --- Error Handling Edge Cases ---


class TestOllamaErrorHandling:
    def test_raises_on_invalid_json_response(self):
        config = HwccConfig()
        embedder = OllamaEmbedder(config)
        chunk = _make_chunk()
        response = _FakeResponse(b"<html>Not JSON</html>")

        with (
            patch("hwcc.embed.ollama.urlopen", return_value=response),
            pytest.raises(EmbeddingError, match="invalid JSON"),
        ):
            embedder.embed_chunks([chunk])

    def test_raises_on_count_mismatch(self):
        config = HwccConfig()
        embedder = OllamaEmbedder(config)
        chunks = _make_chunks(3)
        response = _FakeResponse(_ollama_response([_FAKE_VECTOR] * 2))

        with (
            patch("hwcc.embed.ollama.urlopen", return_value=response),
            pytest.raises(EmbeddingError, match="3 inputs"),
        ):
            embedder.embed_chunks(chunks)


class TestOpenAICompatErrorHandling:
    def test_raises_on_invalid_json_response(self):
        config = HwccConfig()
        config.embedding.api_key_env = ""
        config.embedding.base_url = "http://localhost:8080/v1"
        embedder = OpenAICompatEmbedder(config)
        chunk = _make_chunk()
        response = _FakeResponse(b"502 Bad Gateway")

        with (
            patch("hwcc.embed.openai_compat.urlopen", return_value=response),
            pytest.raises(EmbeddingError, match="invalid JSON"),
        ):
            embedder.embed_chunks([chunk])

    def test_raises_on_missing_embedding_field(self):
        config = HwccConfig()
        config.embedding.api_key_env = ""
        config.embedding.base_url = "http://localhost:8080/v1"
        embedder = OpenAICompatEmbedder(config)
        chunk = _make_chunk()
        # Response with data items missing "embedding" key
        bad_data = json.dumps({"data": [{"index": 0, "object": "embedding"}]}).encode()
        response = _FakeResponse(bad_data)

        with (
            patch("hwcc.embed.openai_compat.urlopen", return_value=response),
            pytest.raises(EmbeddingError, match="embedding"),
        ):
            embedder.embed_chunks([chunk])

    def test_raises_on_count_mismatch(self):
        config = HwccConfig()
        config.embedding.api_key_env = ""
        config.embedding.base_url = "http://localhost:8080/v1"
        embedder = OpenAICompatEmbedder(config)
        chunks = _make_chunks(3)
        response = _FakeResponse(_openai_response([_FAKE_VECTOR] * 2))

        with (
            patch("hwcc.embed.openai_compat.urlopen", return_value=response),
            pytest.raises(EmbeddingError, match="3 inputs"),
        ):
            embedder.embed_chunks(chunks)


class TestBatchSizeValidation:
    def test_ollama_rejects_zero_batch_size(self):
        config = HwccConfig()
        config.embedding.batch_size = 0
        with pytest.raises(EmbeddingError, match="batch_size"):
            OllamaEmbedder(config)

    def test_ollama_rejects_negative_batch_size(self):
        config = HwccConfig()
        config.embedding.batch_size = -1
        with pytest.raises(EmbeddingError, match="batch_size"):
            OllamaEmbedder(config)

    def test_openai_rejects_zero_batch_size(self):
        config = HwccConfig()
        config.embedding.batch_size = 0
        config.embedding.api_key_env = ""
        with pytest.raises(EmbeddingError, match="batch_size"):
            OpenAICompatEmbedder(config)

    def test_batch_size_one_works(self):
        config = HwccConfig()
        config.embedding.batch_size = 1
        embedder = OllamaEmbedder(config)
        chunks = _make_chunks(3)

        call_count = 0

        def mock_urlopen(req, **kwargs):
            nonlocal call_count
            call_count += 1
            body = json.loads(req.data)
            n = len(body["input"])
            return _FakeResponse(_ollama_response([_FAKE_VECTOR] * n))

        with patch("hwcc.embed.ollama.urlopen", side_effect=mock_urlopen):
            result = embedder.embed_chunks(chunks)

        assert len(result) == 3
        assert call_count == 3  # one chunk per call


# --- Registry Integration Tests ---


class TestRegistryIntegration:
    def test_registry_creates_chromadb_embedder(self):
        from hwcc.registry import default_registry

        config = HwccConfig()
        with patch(
            "hwcc.embed.chromadb_embed.DefaultEmbeddingFunction",
            return_value=MagicMock(side_effect=_mock_ef),
        ):
            embedder = default_registry.create("embedding", "chromadb", config)
        assert isinstance(embedder, ChromaDBEmbedder)
        assert isinstance(embedder, BaseEmbedder)

    def test_default_config_uses_chromadb(self):
        config = HwccConfig()
        assert config.embedding.provider == "chromadb"

    def test_registry_creates_ollama_embedder(self):
        from hwcc.registry import default_registry

        config = HwccConfig()
        embedder = default_registry.create("embedding", "ollama", config)
        assert isinstance(embedder, OllamaEmbedder)
        assert isinstance(embedder, BaseEmbedder)

    def test_registry_creates_openai_embedder(self):
        from hwcc.registry import default_registry

        config = HwccConfig()
        config.embedding.api_key_env = ""
        embedder = default_registry.create("embedding", "openai", config)
        assert isinstance(embedder, OpenAICompatEmbedder)
        assert isinstance(embedder, BaseEmbedder)

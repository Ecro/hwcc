"""Pipeline data contracts for hwcc.

Frozen dataclasses that flow between pipeline stages:
  Path → ParseResult → list[Chunk] → list[EmbeddedChunk] → stored
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "Chunk",
    "ChunkMetadata",
    "EmbeddedChunk",
    "ParseResult",
    "SearchResult",
]


@dataclass(frozen=True)
class ChunkMetadata:
    """Metadata attached to every chunk flowing through the pipeline."""

    doc_id: str
    doc_type: str = ""
    chip: str = ""
    section_path: str = ""
    page: int = 0
    chunk_level: str = "detail"
    peripheral: str = ""
    content_type: str = ""


@dataclass(frozen=True)
class ParseResult:
    """Output of a parser — clean markdown with metadata."""

    doc_id: str
    content: str
    doc_type: str = ""
    title: str = ""
    source_path: str = ""
    chip: str = ""
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Chunk:
    """A single chunk of text with metadata, ready for embedding."""

    chunk_id: str
    content: str
    token_count: int
    metadata: ChunkMetadata


@dataclass(frozen=True)
class EmbeddedChunk:
    """A chunk with its embedding vector attached."""

    chunk: Chunk
    embedding: tuple[float, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SearchResult:
    """A search result: chunk + relevance score."""

    chunk: Chunk
    score: float
    distance: float = 0.0

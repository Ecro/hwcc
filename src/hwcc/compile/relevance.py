"""Deterministic keyword-overlap scoring for chunk relevance.

Scores chunks by counting how many peripheral-related keywords appear
in the chunk's content.  No embedder or LLM needed — fully deterministic.

Inspired by EmbedGenius "Selective Memory Pick-up" (TF-IDF scoring).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hwcc.types import Chunk

__all__ = ["build_peripheral_keywords", "rank_chunks", "score_chunk_relevance"]

logger = logging.getLogger(__name__)

# Minimum keyword-overlap score to include a chunk (10% of keywords).
_MIN_RELEVANCE_SCORE = 0.1

# Regex to split text into word tokens.
_WORD_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9]{1,}\b")

# Extract register names from markdown table first column: "| CR1 | ..."
_REGISTER_NAME_RE = re.compile(r"^\|\s*([A-Z][A-Z0-9_]{1,})\s*\|", re.MULTILINE)

# Common English stopwords + markdown/table noise to exclude from tokens.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "had",
        "her",
        "was",
        "one",
        "our",
        "out",
        "has",
        "his",
        "how",
        "its",
        "may",
        "new",
        "now",
        "old",
        "see",
        "way",
        "who",
        "did",
        "get",
        "let",
        "say",
        "she",
        "too",
        "use",
        "with",
        "this",
        "that",
        "from",
        "they",
        "been",
        "have",
        "will",
        "each",
        "make",
        "like",
        "long",
        "look",
        "many",
        "some",
        "them",
        "than",
        "into",
        "only",
        "when",
        "also",
        "after",
        "should",
        "could",
        "would",
        "there",
        "their",
        "what",
        "about",
        "which",
        "other",
        "these",
        "then",
        "just",
        "more",
        "over",
        "such",
        "where",
        "most",
        "very",
        "does",
        "must",
        "being",
        "before",
        "between",
        "through",
        # Table/markdown noise
        "register",
        "offset",
        "size",
        "access",
        "reset",
        "description",
        "field",
        "bits",
        "value",
        "name",
        "type",
        "table",
        "note",
        "reserved",
    }
)


def _tokenize(text: str) -> set[str]:
    """Extract unique lowercase word tokens from text.

    Splits on word boundaries, lowercases, filters stopwords and
    very short tokens (< 2 chars).  Strips markdown syntax implicitly
    because ``_WORD_RE`` only matches letter-starting sequences.

    Args:
        text: Raw text or markdown content.

    Returns:
        Set of lowercase word tokens.
    """
    if not text:
        return set()
    words = _WORD_RE.findall(text.lower())
    return {w for w in words if w not in _STOPWORDS}


def build_peripheral_keywords(
    peripheral_name: str,
    register_map: str = "",
    description: str = "",
) -> set[str]:
    """Build keyword set from peripheral name + SVD content.

    Extracts:
        - Peripheral name tokens (e.g. ``"SPI1"`` → ``{"spi1", "spi"}``)
        - Register names from markdown table first column
        - Description words (stopword-filtered)

    Args:
        peripheral_name: Peripheral name (e.g. ``"SPI1"``).
        register_map: SVD register map markdown content.
        description: Peripheral description text.

    Returns:
        Set of lowercase keyword strings.
    """
    keywords: set[str] = set()

    # Peripheral name tokens
    name_lower = peripheral_name.lower()
    keywords.add(name_lower)
    # Strip trailing digits to get base name: "spi1" → "spi"
    base = re.sub(r"\d+$", "", name_lower)
    if base and base != name_lower:
        keywords.add(base)

    # Register names from markdown tables
    if register_map:
        for match in _REGISTER_NAME_RE.finditer(register_map):
            reg_name = match.group(1).lower()
            if reg_name not in _STOPWORDS and len(reg_name) >= 2:
                keywords.add(reg_name)

    # Description words
    if description:
        keywords |= _tokenize(description)

    return keywords


def score_chunk_relevance(content: str, keywords: set[str]) -> float:
    """Score chunk content by keyword overlap ratio.

    Counts how many keywords from the keyword set appear in the
    chunk's word tokens.  Returns the ratio of found keywords to
    total keywords.

    Args:
        content: Chunk text content.
        keywords: Set of target keywords.

    Returns:
        Score between 0.0 (no overlap) and 1.0 (all keywords found).
    """
    if not keywords or not content:
        return 0.0
    words = _tokenize(content)
    overlap = keywords & words
    return len(overlap) / len(keywords)


def rank_chunks(
    chunks: list[Chunk],
    keywords: set[str],
    max_chunks: int = 5,
    min_score: float = _MIN_RELEVANCE_SCORE,
) -> list[Chunk]:
    """Score, filter, and rank chunks by keyword relevance.

    Scores each chunk against the keyword set, filters out chunks
    below ``min_score``, sorts by score descending (chunk_id for
    tiebreaking), and returns the top ``max_chunks``.

    When ``keywords`` is empty, falls back to positional order
    (sorted by chunk_id) for backward compatibility.

    Args:
        chunks: Candidate chunks to rank.
        keywords: Target keyword set from ``build_peripheral_keywords``.
        max_chunks: Maximum number of chunks to return.
        min_score: Minimum score threshold (0.0-1.0).

    Returns:
        Ranked list of relevant chunks.
    """
    if not chunks:
        return []

    # Fallback: no keywords → positional order (backward compat)
    if not keywords:
        return sorted(chunks, key=lambda c: c.chunk_id)[:max_chunks]

    scored = [(c, score_chunk_relevance(c.content, keywords)) for c in chunks]
    # Sort by score descending, then chunk_id ascending for stability
    scored.sort(key=lambda x: (-x[1], x[0].chunk_id))

    result = [c for c, s in scored if s >= min_score][:max_chunks]

    # Log filtering stats
    if len(result) < len(chunks):
        filtered_count = len(chunks) - len(result)
        logger.debug(
            "Relevance scoring: kept %d/%d chunks (filtered %d below %.2f)",
            len(result),
            len(chunks),
            filtered_count,
            min_score,
        )

    return result

"""Recursive markdown-aware chunker with token counting.

Splits ParseResult content into Chunk objects respecting markdown structure:
- Never splits mid-table or mid-code-block
- Prefers splitting at heading boundaries
- Maintains section path tracking through heading hierarchy
- Configurable token budget with overlap between consecutive chunks
"""

from __future__ import annotations

import functools
import hashlib
import logging
import re
from typing import TYPE_CHECKING, ClassVar

import tiktoken

from hwcc.chunk.base import BaseChunker
from hwcc.exceptions import ChunkError
from hwcc.types import Chunk, ChunkMetadata

if TYPE_CHECKING:
    from hwcc.config import HwccConfig
    from hwcc.types import ParseResult

__all__ = ["MarkdownChunker"]

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _get_encoding() -> tiktoken.Encoding:
    """Get the tiktoken encoding, lazily initialized and thread-safe."""
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in text using cl100k_base encoding."""
    if not text:
        return 0
    return len(_get_encoding().encode(text))


# Page marker injected by PDF parser: <!-- PAGE:N -->
_PAGE_MARKER_RE = re.compile(r"<!-- PAGE:(\d+) -->")
_PAGE_MARKER_STRIP_RE = re.compile(r"<!-- PAGE:\d+ -->\n?")

# Heading pattern: matches lines like "# Heading", "## Heading", etc.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Fenced code block: ``` or ~~~ with optional language
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})", re.MULTILINE)

# Table row: line starting with |
_TABLE_ROW_RE = re.compile(r"^\|.+\|$", re.MULTILINE)

# Table separator: | --- | --- | pattern
_TABLE_SEP_RE = re.compile(r"^\|[\s:]*-+[\s:]*\|", re.MULTILINE)

# --- Hardware-domain content type taxonomy (TECH_SPEC.md §5.4) ---

CONTENT_TYPES: frozenset[str] = frozenset({
    "code",
    "register_table",
    "register_description",
    "timing_spec",
    "config_procedure",
    "errata",
    "pin_mapping",
    "electrical_spec",
    "api_reference",  # Phase 5 — requires C header parsing
    "table",
    "section",
    "prose",
})

# --- Hardware-domain content type detection patterns ---

# Register-related keywords (tables and prose)
_REGISTER_KW_RE = re.compile(
    r"\b(?:register|offset|reset\s*value|bit\s*field|"
    r"read[/\s-]write|read[/\s-]only|write[/\s-]only|base\s*address)\b"
    r"|0x[0-9A-Fa-f]{8}",
    re.IGNORECASE,
)

# Timing specification keywords
_TIMING_KW_RE = re.compile(
    r"\b\d+\s*(?:ns|µs|us|ms|MHz|kHz|GHz)\b"
    r"|\b(?:setup\s*time|hold\s*time|propagation\s*delay|"
    r"clock\s*(?:speed|frequency|period)|baud\s*rate)\b",
    re.IGNORECASE,
)

# Configuration/initialization procedure keywords
_CONFIG_PROC_KW_RE = re.compile(
    r"\b(?:step\s*\d|initialization\s*sequence|"
    r"programming\s*procedure|following\s*steps|"
    r"must\s*be\s*set|should\s*be\s*configured)\b",
    re.IGNORECASE,
)

# Errata keywords
_ERRATA_KW_RE = re.compile(
    r"\b(?:errat(?:a|um)|workaround|limitation|silicon\s*bug|"
    r"advisory|known\s*issue)\b"
    r"|ES\d{4}",
    re.IGNORECASE,
)

# Pin mapping keywords
_PIN_MAP_KW_RE = re.compile(
    r"\b(?:alternate\s*function|AF\d+|"
    r"pin\s*(?:mapping|assignment|configuration)|remap)\b"
    r"|\bGPIO[A-Z]\d*\b",
    re.IGNORECASE,
)

# Electrical specification keywords
_ELECTRICAL_KW_RE = re.compile(
    r"\b\d+\.?\d*\s*(?:mA|µA|uA|kΩ)\b"
    r"|\b(?:power\s*supply|current\s*consumption|"
    r"voltage\s*(?:range|level))\b"
    r"|\bV(?:DD|CC|SS|DDA|BAT|REF)\b",
    re.IGNORECASE,
)


def _extract_atomic_blocks(text: str) -> list[tuple[str, bool]]:
    """Split text into segments, marking code blocks and tables as atomic.

    Returns a list of (content, is_atomic) tuples. Atomic blocks must not
    be split by the recursive splitter.
    """
    segments: list[tuple[str, bool]] = []
    lines = text.split("\n")
    i = 0
    current_text: list[str] = []

    while i < len(lines):
        line = lines[i]

        # Check for fenced code block start
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            # Flush accumulated text
            if current_text:
                segments.append(("\n".join(current_text), False))
                current_text = []

            fence_marker = fence_match.group(1)
            fence_char = fence_marker[0]
            fence_len = len(fence_marker)
            code_lines = [line]
            i += 1

            # Find matching closing fence
            while i < len(lines):
                code_lines.append(lines[i])
                close_match = re.match(rf"^{re.escape(fence_char)}{{{fence_len},}}$", lines[i])
                if close_match:
                    i += 1
                    break
                i += 1

            segments.append(("\n".join(code_lines), True))
            continue

        # Check for table block (consecutive lines starting with |)
        if _TABLE_ROW_RE.match(line):
            # Flush accumulated text
            if current_text:
                segments.append(("\n".join(current_text), False))
                current_text = []

            table_lines = [line]
            i += 1
            while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
                table_lines.append(lines[i])
                i += 1

            # Only treat as atomic table if it has a separator row (real table)
            table_text = "\n".join(table_lines)
            if _TABLE_SEP_RE.search(table_text):
                segments.append((table_text, True))
            else:
                # Not a real table, treat as normal text
                current_text.extend(table_lines)
            continue

        current_text.append(line)
        i += 1

    # Flush remaining text
    if current_text:
        segments.append(("\n".join(current_text), False))

    return segments


class _SectionTracker:
    """Tracks heading hierarchy across chunks to maintain section_path."""

    def __init__(self) -> None:
        self._stack: list[tuple[int, str]] = []

    @property
    def path(self) -> str:
        """Current section path as 'H1 > H2 > H3'."""
        return " > ".join(h[1] for h in self._stack)

    def update(self, text: str) -> None:
        """Update the heading stack based on headings found in text."""
        for match in _HEADING_RE.finditer(text):
            level = len(match.group(1))
            title = match.group(2).strip()

            # Pop headings at same or deeper level
            while self._stack and self._stack[-1][0] >= level:
                self._stack.pop()

            self._stack.append((level, title))


def _generate_chunk_id(doc_id: str, index: int, content: str) -> str:
    """Generate a deterministic unique chunk ID."""
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    return f"{doc_id}_chunk_{index:04d}_{content_hash}"


def _recursive_split(
    text: str,
    max_tokens: int,
    separators: list[str],
) -> list[str]:
    """Recursively split text to fit within max_tokens.

    Tries each separator in order, falling back to the next if chunks
    are still too large.
    """
    if count_tokens(text) <= max_tokens:
        return [text]

    if not separators:
        # Last resort: hard split by tokens
        return _hard_split(text, max_tokens)

    separator = separators[0]
    remaining_separators = separators[1:]

    # Split on the separator
    if separator == "\n# ":
        # Special handling for headings: keep the heading with its content
        # Also match headings at start of text (no preceding newline)
        parts = re.split(r"(?=(?:^|\n)# )", text)
    elif separator == "\n## ":
        parts = re.split(r"(?=(?:^|\n)## )", text)
    elif separator == "\n### ":
        parts = re.split(r"(?=(?:^|\n)###+ )", text)
    else:
        parts = text.split(separator)

    # Filter empty parts
    parts = [p for p in parts if p.strip()]

    if len(parts) <= 1:
        # Separator didn't help, try next one
        return _recursive_split(text, max_tokens, remaining_separators)

    # Merge small adjacent parts and recursively split large ones
    result: list[str] = []
    current = ""

    # For heading separators, the heading is preserved in the split part
    # (thanks to lookahead), so use newline to rejoin instead of the separator
    rejoin = "\n" if separator.startswith("\n#") else separator

    for part in parts:
        candidate = current + rejoin + part if current else part
        if count_tokens(candidate) <= max_tokens:
            current = candidate
        else:
            if current:
                result.append(current)
            # Check if this single part needs further splitting
            if count_tokens(part) > max_tokens:
                result.extend(_recursive_split(part, max_tokens, remaining_separators))
            else:
                current = part
                continue
            current = ""

    if current:
        result.append(current)

    return result


def _hard_split(text: str, max_tokens: int) -> list[str]:
    """Hard-split text by token count when all separators are exhausted."""
    enc = _get_encoding()
    tokens = enc.encode(text)
    result: list[str] = []

    for i in range(0, len(tokens), max_tokens):
        chunk_tokens = tokens[i : i + max_tokens]
        result.append(enc.decode(chunk_tokens))

    return result


def _add_overlap(
    chunks: list[str],
    overlap_tokens: int,
    atomic_indices: set[int] | None = None,
) -> list[str]:
    """Add overlap from the end of each chunk to the start of the next.

    Atomic blocks (tables, code fences) are skipped — they should not
    receive overlap prefixes since they are already self-contained and
    may already be at or over the max_tokens budget.
    """
    if overlap_tokens <= 0 or len(chunks) <= 1:
        return chunks

    atomic = atomic_indices or set()
    enc = _get_encoding()
    result = [chunks[0]]

    for i in range(1, len(chunks)):
        if i in atomic:
            # Don't prepend overlap to atomic blocks
            result.append(chunks[i])
            continue

        prev_tokens = enc.encode(chunks[i - 1])
        overlap_text = ""
        if len(prev_tokens) > overlap_tokens:
            overlap_tokens_slice = prev_tokens[-overlap_tokens:]
            overlap_text = enc.decode(overlap_tokens_slice)

        if overlap_text:
            result.append(overlap_text + chunks[i])
        else:
            result.append(chunks[i])

    return result


class MarkdownChunker(BaseChunker):
    """Recursive markdown-aware chunker with token counting.

    Splits content respecting markdown structure:
    - Tables and fenced code blocks are never split
    - Heading boundaries are preferred split points
    - Configurable token budget with overlap
    - Section path tracking through heading hierarchy
    """

    # Separators in priority order (try first separator first)
    SEPARATORS: ClassVar[list[str]] = [
        "\n# ",  # H1 headings
        "\n## ",  # H2 headings
        "\n### ",  # H3+ headings
        "\n\n",  # Paragraph boundaries
        "\n",  # Line breaks
        " ",  # Word boundaries
    ]

    def chunk(self, result: ParseResult, config: HwccConfig) -> list[Chunk]:
        """Split a ParseResult into chunks respecting markdown structure.

        Args:
            result: Parsed document content.
            config: Project config with chunk settings.

        Returns:
            List of Chunk objects with metadata.

        Raises:
            ChunkError: If chunking fails.
        """
        try:
            return self._do_chunk(result, config)
        except ChunkError:
            raise
        except Exception as e:
            logger.error("Failed to chunk document %s: %s", result.doc_id, e)
            raise ChunkError(f"Failed to chunk document {result.doc_id}: {e}") from e

    def _do_chunk(self, result: ParseResult, config: HwccConfig) -> list[Chunk]:
        """Internal chunking implementation."""
        content = result.content.strip()
        if not content:
            return []

        max_tokens = config.chunk.max_tokens
        overlap_tokens = config.chunk.overlap_tokens
        min_tokens = config.chunk.min_tokens

        # Reserve room for overlap so chunks stay within max_tokens after overlap
        split_budget = max(max_tokens - overlap_tokens, 1) if overlap_tokens > 0 else max_tokens

        # Step 1: Extract atomic blocks (tables, code blocks)
        segments = _extract_atomic_blocks(content)

        # Step 2: Split non-atomic segments, pass through atomic ones
        raw_chunks: list[str] = []
        atomic_indices: set[int] = set()
        for segment_text, is_atomic in segments:
            text = segment_text.strip()
            if not text:
                continue

            if is_atomic:
                # Atomic blocks go through as-is (even if oversized)
                atomic_indices.add(len(raw_chunks))
                raw_chunks.append(text)
            else:
                # Recursively split non-atomic text (budget accounts for overlap)
                splits = _recursive_split(text, split_budget, self.SEPARATORS)
                raw_chunks.extend(splits)

        # Step 3: Add overlap between consecutive non-atomic chunks
        raw_chunks = _add_overlap(raw_chunks, overlap_tokens, atomic_indices)

        # Step 4: Filter out chunks below min_tokens (merge with neighbors)
        raw_chunks = self._merge_small_chunks(raw_chunks, min_tokens, max_tokens)

        # Step 5: Build Chunk objects with metadata
        section_tracker = _SectionTracker()
        chunks: list[Chunk] = []

        for i, chunk_text in enumerate(raw_chunks):
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue

            # Extract page number from first PAGE marker (PDF-only)
            page_match = _PAGE_MARKER_RE.search(chunk_text)
            page_num = int(page_match.group(1)) if page_match else 0

            # Strip all page markers from content before storage
            chunk_text = _PAGE_MARKER_STRIP_RE.sub("", chunk_text).strip()
            if not chunk_text:
                continue

            # Update section tracking
            section_tracker.update(chunk_text)

            token_count = count_tokens(chunk_text)
            chunk_id = _generate_chunk_id(result.doc_id, i, chunk_text)

            metadata = ChunkMetadata(
                doc_id=result.doc_id,
                doc_type=result.doc_type,
                chip=result.chip,
                section_path=section_tracker.path,
                page=page_num,
                content_type=self._detect_content_type(chunk_text),
            )

            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    content=chunk_text,
                    token_count=token_count,
                    metadata=metadata,
                )
            )

        logger.info(
            "Chunked %s into %d chunks (max_tokens=%d, overlap=%d)",
            result.doc_id,
            len(chunks),
            max_tokens,
            overlap_tokens,
        )

        return chunks

    def _merge_small_chunks(
        self,
        chunks: list[str],
        min_tokens: int,
        max_tokens: int,
    ) -> list[str]:
        """Merge chunks smaller than min_tokens with their neighbors."""
        if not chunks or min_tokens <= 0:
            return chunks

        result: list[str] = []
        current = ""

        for chunk_text in chunks:
            if not current:
                current = chunk_text
                continue

            current_tokens = count_tokens(current)

            # If current chunk is too small, try to merge
            if current_tokens < min_tokens:
                merged = current + "\n\n" + chunk_text
                if count_tokens(merged) <= max_tokens:
                    current = merged
                    continue
                # Can't merge (would exceed max), keep current as-is
                result.append(current)
                current = chunk_text
            else:
                result.append(current)
                current = chunk_text

        if current:
            # If the last chunk is too small, merge with previous if possible
            if result and count_tokens(current) < min_tokens:
                merged = result[-1] + "\n\n" + current
                if count_tokens(merged) <= max_tokens:
                    result[-1] = merged
                else:
                    result.append(current)
            else:
                result.append(current)

        return result

    def _detect_content_type(self, text: str) -> str:
        """Detect the primary content type of a chunk.

        Priority order: structural types first (code, table subtypes),
        then domain-specific prose types, then generic fallbacks.
        See TECH_SPEC.md §5.4 for the full taxonomy.
        """
        # 1. Code blocks (unambiguous structural marker)
        if _FENCE_RE.search(text):
            return "code"

        # 2. Table-based types (structural + keyword refinement)
        if _TABLE_SEP_RE.search(text):
            if _REGISTER_KW_RE.search(text):
                return "register_table"
            if _PIN_MAP_KW_RE.search(text):
                return "pin_mapping"
            if _ELECTRICAL_KW_RE.search(text):
                return "electrical_spec"
            if _TIMING_KW_RE.search(text):
                return "timing_spec"
            return "table"

        # 3. Domain-specific prose types (keyword-based)
        if _ERRATA_KW_RE.search(text):
            return "errata"
        if _CONFIG_PROC_KW_RE.search(text):
            return "config_procedure"
        if _REGISTER_KW_RE.search(text):
            return "register_description"
        if _TIMING_KW_RE.search(text):
            return "timing_spec"
        if _PIN_MAP_KW_RE.search(text):
            return "pin_mapping"
        if _ELECTRICAL_KW_RE.search(text):
            return "electrical_spec"

        # 4. Generic structural fallbacks
        if _HEADING_RE.search(text):
            return "section"
        return "prose"

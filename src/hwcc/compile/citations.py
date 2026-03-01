"""Citation formatting for compiled output.

Generates inline source citations like:
  *Source: RM0090, §SPI1 > Configuration, p.868*
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hwcc.manifest import Manifest
    from hwcc.types import ChunkMetadata

__all__ = ["build_title_map", "format_citation"]

logger = logging.getLogger(__name__)


def build_title_map(manifest: Manifest) -> dict[str, str]:
    """Build a doc_id to human-readable title mapping from the manifest.

    Falls back to deriving title from the document path.
    """
    title_map: dict[str, str] = {}
    for entry in manifest.documents:
        name = PurePosixPath(entry.path).stem
        title = name.replace("_", " ").replace("-", " ") if name else entry.id
        title_map[entry.id] = title
    return title_map


def format_citation(
    meta: ChunkMetadata,
    title_map: dict[str, str],
) -> str:
    """Format an inline citation string for a chunk.

    Format varies by doc_type:
      - PDF:   *Source: RM0090, §Section Path, p.868*
      - SVD:   *Source: STM32F407*
      - Other: *Source: Title, §Section Path*

    Args:
        meta: Chunk metadata with doc_id, doc_type, section_path, page.
        title_map: Mapping of doc_id to human-readable title.

    Returns:
        Formatted citation string in markdown italic.
    """
    title = title_map.get(meta.doc_id, meta.doc_id)
    parts: list[str] = [title]

    if meta.section_path:
        # Truncate to last 2 path elements for brevity
        elements = meta.section_path.split(" > ")
        brief = " > ".join(elements[-2:]) if len(elements) > 2 else meta.section_path
        parts.append(f"§{brief}")

    if meta.doc_type == "pdf" and meta.page > 0:
        parts.append(f"p.{meta.page}")

    return f"*Source: {', '.join(parts)}*"

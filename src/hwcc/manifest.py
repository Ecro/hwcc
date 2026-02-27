"""Manifest system for hwcc.

Tracks indexed documents with SHA-256 content hashing for incremental updates.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hwcc.exceptions import ManifestError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "DocumentEntry",
    "Manifest",
    "compute_hash",
    "load_manifest",
    "make_doc_id",
    "make_entry",
    "save_manifest",
]

logger = logging.getLogger(__name__)

HASH_CHUNK_SIZE = 65536


@dataclass(frozen=True)
class DocumentEntry:
    """Immutable record of an indexed document."""

    id: str
    path: str
    doc_type: str
    hash: str
    added: str
    chunks: int = 0
    chip: str = ""


@dataclass
class Manifest:
    """Tracks all indexed documents in a project.

    Uses a dict internally for O(1) lookups by document ID.
    Serializes to/from a list in JSON for readability.
    """

    schema_version: str = "1"
    _documents: dict[str, DocumentEntry] = field(default_factory=dict)
    last_compiled: str = ""

    @property
    def documents(self) -> list[DocumentEntry]:
        """Return documents as a list (for iteration and serialization)."""
        return list(self._documents.values())

    def add_document(self, entry: DocumentEntry) -> None:
        """Add or replace a document entry."""
        self._documents[entry.id] = entry

    def remove_document(self, doc_id: str) -> bool:
        """Remove a document by ID. Returns True if found and removed."""
        if doc_id in self._documents:
            del self._documents[doc_id]
            return True
        return False

    def get_document(self, doc_id: str) -> DocumentEntry | None:
        """Get a document entry by ID."""
        return self._documents.get(doc_id)

    def is_changed(self, doc_id: str, current_hash: str) -> bool:
        """Check if a document has changed since last indexing.

        Returns True if the document is new or its hash differs.
        """
        existing = self.get_document(doc_id)
        if existing is None:
            return True
        return existing.hash != current_hash


def compute_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            while True:
                chunk = f.read(HASH_CHUNK_SIZE)
                if not chunk:
                    break
                h.update(chunk)
    except OSError as e:
        raise ManifestError(f"Failed to hash file {path}: {e}") from e
    return f"sha256:{h.hexdigest()}"


def _entry_to_dict(entry: DocumentEntry) -> dict[str, object]:
    """Serialize a DocumentEntry to a dict."""
    d: dict[str, object] = {
        "id": entry.id,
        "path": entry.path,
        "type": entry.doc_type,
        "hash": entry.hash,
        "added": entry.added,
        "chunks": entry.chunks,
    }
    if entry.chip:
        d["chip"] = entry.chip
    return d


def _entry_from_dict(data: dict[str, object]) -> DocumentEntry:
    """Deserialize a DocumentEntry from a dict."""
    required = ("id", "path", "hash", "added")
    missing = [k for k in required if k not in data]
    if missing:
        raise ManifestError(f"Document entry missing required fields: {missing}")
    return DocumentEntry(
        id=str(data["id"]),
        path=str(data["path"]),
        doc_type=str(data.get("type", "unknown")),
        hash=str(data["hash"]),
        added=str(data["added"]),
        chunks=int(str(data.get("chunks", 0))),
        chip=str(data.get("chip", "")),
    )


def save_manifest(manifest: Manifest, path: Path) -> None:
    """Save manifest to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": manifest.schema_version,
        "documents": [_entry_to_dict(d) for d in manifest.documents],
        "last_compiled": manifest.last_compiled,
    }
    try:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        logger.info("Saved manifest to %s", path)
    except OSError as e:
        logger.error("Failed to save manifest to %s: %s", path, e)
        raise ManifestError(f"Failed to save manifest to {path}: {e}") from e


def load_manifest(path: Path) -> Manifest:
    """Load manifest from a JSON file."""
    if not path.exists():
        raise ManifestError(f"Manifest file not found: {path}")

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to load manifest from %s: %s", path, e)
        raise ManifestError(f"Failed to load manifest from {path}: {e}") from e

    manifest = Manifest(
        schema_version=str(data.get("schema_version", data.get("version", "1"))),
        last_compiled=str(data.get("last_compiled", "")),
    )
    for doc_data in data.get("documents", []):
        entry = _entry_from_dict(doc_data)
        manifest.add_document(entry)

    logger.info("Loaded manifest from %s (%d documents)", path, len(manifest.documents))
    return manifest


def make_doc_id(path: Path) -> str:
    """Generate a document ID from a file path.

    Includes the file extension to avoid collisions between same-name files
    of different types (e.g., STM32F407.svd vs STM32F407.pdf).
    """
    stem = path.stem.lower().replace(" ", "_").replace("-", "_")
    suffix = path.suffix.lstrip(".").lower()
    return f"{stem}_{suffix}" if suffix else stem


def make_entry(path: Path, doc_type: str = "auto", chip: str = "") -> DocumentEntry:
    """Create a DocumentEntry for a file."""
    return DocumentEntry(
        id=make_doc_id(path),
        path=str(path),
        doc_type=doc_type,
        hash=compute_hash(path),
        added=datetime.now(UTC).isoformat(),
        chunks=0,
        chip=chip,
    )

"""Vector store — ChromaDB persistent storage."""

from hwcc.store.base import BaseStore
from hwcc.store.chroma import ChromaStore

__all__ = ["BaseStore", "ChromaStore"]

# Registry registration deferred to task 1.8 (CLI integration).
# ChromaStore needs persist_path which is derived at runtime from project root.

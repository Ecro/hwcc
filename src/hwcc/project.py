"""Project manager for hwcc.

Handles project initialization, status reporting, and project root discovery.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from hwcc.config import HwccConfig, default_config, load_config, save_config
from hwcc.manifest import Manifest, load_manifest, save_manifest

__all__ = [
    "CONFIG_FILE",
    "MANIFEST_FILE",
    "RAG_DIR",
    "ProjectManager",
    "ProjectStatus",
]

logger = logging.getLogger(__name__)

RAG_DIR = ".rag"
CONFIG_FILE = "config.toml"
MANIFEST_FILE = "manifest.json"

SUBDIRS = [
    "index",
    "processed",
    "context",
    "context/peripherals",
    "context/registers",
]


@dataclass
class ProjectStatus:
    """Summary of the current project state."""

    initialized: bool
    root: Path
    document_count: int
    chunk_count: int
    config: HwccConfig | None


class ProjectManager:
    """Manages hwcc project lifecycle."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()

    @property
    def rag_dir(self) -> Path:
        return self.root / RAG_DIR

    @property
    def config_path(self) -> Path:
        return self.rag_dir / CONFIG_FILE

    @property
    def manifest_path(self) -> Path:
        return self.rag_dir / MANIFEST_FILE

    @property
    def is_initialized(self) -> bool:
        return self.rag_dir.is_dir() and self.config_path.exists() and self.manifest_path.exists()

    def init(
        self,
        chip: str = "",
        rtos: str = "",
        name: str = "",
    ) -> Path:
        """Initialize a new hwcc project.

        Creates .rag/ directory structure, default config, and empty manifest.
        Safe to call on an already-initialized project (idempotent).

        Returns the .rag/ directory path.
        """
        # Create directory structure
        self.rag_dir.mkdir(parents=True, exist_ok=True)
        for subdir in SUBDIRS:
            (self.rag_dir / subdir).mkdir(parents=True, exist_ok=True)

        # Create or load config
        if self.config_path.exists():
            config = load_config(self.config_path)
            logger.info("Existing config found at %s", self.config_path)
        else:
            config = default_config()

        # Apply overrides
        if chip:
            config.hardware.mcu = chip
        if rtos:
            config.software.rtos = rtos
        if name:
            config.project.name = name
        elif not config.project.name:
            config.project.name = self.root.name

        # Auto-detect SVD files
        svd_files = self._find_svd_files()
        if svd_files:
            logger.info("Found %d SVD file(s): %s", len(svd_files), svd_files)

        # Detect existing CLAUDE.md
        claude_md = self.root / "CLAUDE.md"
        if claude_md.exists():
            logger.info("Existing CLAUDE.md detected (will preserve user content)")

        save_config(config, self.config_path)

        # Create or preserve manifest
        if not self.manifest_path.exists():
            save_manifest(Manifest(), self.manifest_path)

        logger.info("Initialized hwcc project at %s", self.rag_dir)
        return self.rag_dir

    def status(self) -> ProjectStatus:
        """Get current project status."""
        if not self.is_initialized:
            return ProjectStatus(
                initialized=False,
                root=self.root,
                document_count=0,
                chunk_count=0,
                config=None,
            )

        config = load_config(self.config_path)
        manifest = load_manifest(self.manifest_path)

        total_chunks = sum(d.chunks for d in manifest.documents)

        return ProjectStatus(
            initialized=True,
            root=self.root,
            document_count=len(manifest.documents),
            chunk_count=total_chunks,
            config=config,
        )

    def _find_svd_files(self) -> list[Path]:
        """Find SVD files in the project directory."""
        svd_files: list[Path] = []
        for pattern in ("*.svd", "*.SVD"):
            svd_files.extend(self.root.rglob(pattern))
        # Exclude .rag/ directory
        return [f for f in svd_files if RAG_DIR not in f.parts]

    @staticmethod
    def find_project_root(start: Path | None = None) -> Path | None:
        """Walk up from start directory to find a .rag/ directory.

        Returns the project root (parent of .rag/) or None if not found.
        """
        current = (start or Path.cwd()).resolve()
        while True:
            if (current / RAG_DIR).is_dir():
                return current
            parent = current.parent
            if parent == current:
                return None
            current = parent

"""Tests for hwcc.project module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hwcc.config import load_config
from hwcc.manifest import load_manifest
from hwcc.project import (
    CONFIG_FILE,
    MANIFEST_FILE,
    RAG_DIR,
    ProjectManager,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestProjectInit:
    def test_creates_rag_directory(self, project_dir: Path):
        pm = ProjectManager(project_dir)
        rag_dir = pm.init()
        assert rag_dir.is_dir()
        assert (rag_dir / "index").is_dir()
        assert (rag_dir / "processed").is_dir()
        assert (rag_dir / "context").is_dir()
        assert (rag_dir / "context" / "peripherals").is_dir()
        assert (rag_dir / "context" / "registers").is_dir()

    def test_creates_valid_config(self, project_dir: Path):
        pm = ProjectManager(project_dir)
        pm.init()
        config = load_config(project_dir / RAG_DIR / CONFIG_FILE)
        assert config.embedding.model == "all-MiniLM-L6-v2"

    def test_creates_empty_manifest(self, project_dir: Path):
        pm = ProjectManager(project_dir)
        pm.init()
        manifest = load_manifest(project_dir / RAG_DIR / MANIFEST_FILE)
        assert len(manifest.documents) == 0

    def test_init_with_chip(self, project_dir: Path):
        pm = ProjectManager(project_dir)
        pm.init(chip="STM32F407")
        config = load_config(project_dir / RAG_DIR / CONFIG_FILE)
        assert config.hardware.mcu == "STM32F407"

    def test_init_with_rtos(self, project_dir: Path):
        pm = ProjectManager(project_dir)
        pm.init(rtos="FreeRTOS 10.5.1")
        config = load_config(project_dir / RAG_DIR / CONFIG_FILE)
        assert config.software.rtos == "FreeRTOS 10.5.1"

    def test_init_sets_project_name_from_directory(self, project_dir: Path):
        pm = ProjectManager(project_dir)
        pm.init()
        config = load_config(project_dir / RAG_DIR / CONFIG_FILE)
        assert config.project.name == project_dir.name

    def test_init_idempotent(self, project_dir: Path):
        pm = ProjectManager(project_dir)
        pm.init(chip="STM32F407")
        pm.init(chip="STM32F407")  # Second call should not fail
        config = load_config(project_dir / RAG_DIR / CONFIG_FILE)
        assert config.hardware.mcu == "STM32F407"

    def test_init_preserves_existing_config_values(self, initialized_project: Path):
        pm = ProjectManager(initialized_project)
        pm.init()  # Re-init without chip arg
        config = load_config(initialized_project / RAG_DIR / CONFIG_FILE)
        assert config.hardware.mcu == "STM32F407"  # Preserved from fixture


class TestProjectStatus:
    def test_status_uninitialized(self, project_dir: Path):
        pm = ProjectManager(project_dir)
        st = pm.status()
        assert st.initialized is False
        assert st.document_count == 0
        assert st.chunk_count == 0
        assert st.config is None

    def test_status_missing_manifest_is_uninitialized(self, initialized_project: Path):
        """Regression test for W5: missing manifest should not crash."""
        (initialized_project / RAG_DIR / MANIFEST_FILE).unlink()
        pm = ProjectManager(initialized_project)
        st = pm.status()
        assert st.initialized is False

    def test_status_initialized_empty(self, initialized_project: Path):
        pm = ProjectManager(initialized_project)
        st = pm.status()
        assert st.initialized is True
        assert st.document_count == 0
        assert st.chunk_count == 0
        assert st.config is not None
        assert st.config.hardware.mcu == "STM32F407"


class TestFindProjectRoot:
    def test_finds_root_in_current_dir(self, initialized_project: Path):
        result = ProjectManager.find_project_root(initialized_project)
        assert result == initialized_project

    def test_finds_root_from_subdirectory(self, initialized_project: Path):
        subdir = initialized_project / "src" / "drivers"
        subdir.mkdir(parents=True)
        result = ProjectManager.find_project_root(subdir)
        assert result == initialized_project

    def test_returns_none_when_no_project(self, tmp_path: Path):
        result = ProjectManager.find_project_root(tmp_path)
        assert result is None

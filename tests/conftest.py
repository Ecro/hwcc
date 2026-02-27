"""Shared fixtures for hwcc tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hwcc.config import HwccConfig, save_config
from hwcc.manifest import Manifest, save_manifest
from hwcc.project import CONFIG_FILE, MANIFEST_FILE, RAG_DIR

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """A temporary directory simulating a project root."""
    return tmp_path


@pytest.fixture
def initialized_project(tmp_path: Path) -> Path:
    """A temporary project with .rag/ already initialized."""
    rag = tmp_path / RAG_DIR
    rag.mkdir()
    for subdir in ("index", "processed", "context", "context/peripherals", "context/registers"):
        (rag / subdir).mkdir(parents=True)

    config = HwccConfig()
    config.project.name = "test-project"
    config.hardware.mcu = "STM32F407"
    save_config(config, rag / CONFIG_FILE)
    save_manifest(Manifest(), rag / MANIFEST_FILE)

    return tmp_path


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    """A small sample file for hash testing."""
    f = tmp_path / "sample.txt"
    f.write_text("Hello, hardware world!", encoding="utf-8")
    return f

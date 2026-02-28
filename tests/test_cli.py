"""Tests for hwcc.cli module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from hwcc import __version__
from hwcc.cli import app
from hwcc.config import load_config
from hwcc.project import CONFIG_FILE, RAG_DIR

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


class TestVersion:
    def test_prints_version(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.output


class TestInit:
    def test_init_creates_rag_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / RAG_DIR).is_dir()
        assert "Initialized" in result.output

    def test_init_with_chip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init", "--chip", "STM32F407"])
        assert result.exit_code == 0
        config = load_config(tmp_path / RAG_DIR / CONFIG_FILE)
        assert config.hardware.mcu == "STM32F407"
        assert "STM32F407" in result.output

    def test_init_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init", "--chip", "STM32F407"])
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0


class TestStatus:
    def test_status_uninitialized(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "No hwcc project found" in result.output

    def test_status_initialized(self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(initialized_project)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "0" in result.output  # 0 documents


class TestStubCommands:
    def test_compile_not_implemented(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["compile"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.output

    def test_search_not_implemented(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["search", "SPI"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.output

    def test_mcp_not_implemented(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["mcp"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.output

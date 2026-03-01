"""Tests for hwcc.cli module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from hwcc import __version__
from hwcc.cli import app
from hwcc.config import load_config
from hwcc.manifest import DocumentEntry, Manifest, save_manifest
from hwcc.project import CONFIG_FILE, MANIFEST_FILE, RAG_DIR

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

    def test_init_error_shows_friendly_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        def _fail_init(*_a: object, **_kw: object) -> None:
            raise OSError("Permission denied")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("hwcc.cli.ProjectManager.init", _fail_init)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1
        assert "Permission denied" in result.output


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

    def test_status_shows_no_docs_hint(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(initialized_project)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "hwcc add" in result.output


class TestStatusWithDocuments:
    """Tests for enhanced status output with indexed documents."""

    @staticmethod
    def _add_docs_to_manifest(project: Path) -> None:
        """Helper to add sample documents to the manifest."""
        manifest = Manifest()
        manifest.add_document(
            DocumentEntry(
                id="board_svd",
                path="/tmp/board.svd",
                doc_type="svd",
                hash="sha256:abc123",
                added="2026-02-28T10:00:00+00:00",
                chunks=42,
                chip="STM32F407",
            )
        )
        manifest.add_document(
            DocumentEntry(
                id="datasheet_pdf",
                path="/tmp/datasheet.pdf",
                doc_type="datasheet",
                hash="sha256:def456",
                added="2026-02-28T11:00:00+00:00",
                chunks=95,
                chip="STM32F407",
            )
        )
        save_manifest(manifest, project / RAG_DIR / MANIFEST_FILE)

    def test_status_shows_document_count(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(initialized_project)
        self._add_docs_to_manifest(initialized_project)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "2" in result.output  # 2 documents

    def test_status_shows_chunk_count(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(initialized_project)
        self._add_docs_to_manifest(initialized_project)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "137" in result.output  # 42 + 95 chunks

    def test_status_shows_per_document_table(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(initialized_project)
        self._add_docs_to_manifest(initialized_project)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        # Document IDs should appear
        assert "board_svd" in result.output
        assert "datasheet_pdf" in result.output
        # Doc types should appear
        assert "svd" in result.output
        assert "datasheet" in result.output
        # Chip should appear
        assert "STM32F407" in result.output

    def test_status_shows_embedding_info(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(initialized_project)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        # Default config: all-MiniLM-L6-v2, chromadb
        assert "all-MiniLM-L6-v2" in result.output
        assert "chromadb" in result.output

    def test_status_shows_store_size(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(initialized_project)
        # Create some files in the index directory to give it size
        index_dir = initialized_project / RAG_DIR / "index"
        (index_dir / "test.bin").write_bytes(b"\x00" * 4096)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        # Should show "Index" with a size value
        assert "Index" in result.output


class TestCompile:
    def test_compile_uninitialized_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["compile"])
        assert result.exit_code == 1
        assert "No hwcc project found" in result.output

    def test_compile_empty_project(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(initialized_project)
        result = runner.invoke(app, ["compile"])
        assert result.exit_code == 0
        # Should produce hot.md even with empty store (just config data)
        hot_md = initialized_project / ".rag" / "context" / "hot.md"
        assert hot_md.exists()

    def test_compile_produces_output_files(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(initialized_project)
        result = runner.invoke(app, ["compile"])
        assert result.exit_code == 0
        # Output files for default targets should exist
        assert (initialized_project / "CLAUDE.md").exists()
        assert "Compiled" in result.output

    def test_compile_single_target(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(initialized_project)
        result = runner.invoke(app, ["compile", "--target", "claude"])
        assert result.exit_code == 0
        # CLAUDE.md should exist
        assert (initialized_project / "CLAUDE.md").exists()

    def test_compile_output_has_markers(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(initialized_project)
        runner.invoke(app, ["compile"])
        claude_md = initialized_project / "CLAUDE.md"
        content = claude_md.read_text(encoding="utf-8")
        assert "<!-- BEGIN HWCC CONTEXT" in content
        assert "<!-- END HWCC CONTEXT -->" in content

    def test_compile_non_destructive(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(initialized_project)
        # Write existing CLAUDE.md with user content
        claude_md = initialized_project / "CLAUDE.md"
        claude_md.write_text("# My Project\n\nUser content here.\n", encoding="utf-8")
        runner.invoke(app, ["compile"])
        content = claude_md.read_text(encoding="utf-8")
        # User content preserved
        assert "User content here." in content
        # hwcc content appended
        assert "<!-- BEGIN HWCC CONTEXT" in content

    def test_compile_reports_generated_files(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(initialized_project)
        result = runner.invoke(app, ["compile"])
        assert result.exit_code == 0
        assert "hot.md" in result.output


class TestStubCommands:
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

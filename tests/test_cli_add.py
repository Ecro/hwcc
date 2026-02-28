"""Tests for the hwcc add CLI command."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from hwcc.cli import app
from hwcc.manifest import load_manifest
from hwcc.project import MANIFEST_FILE, RAG_DIR

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


@pytest.fixture()
def txt_file(initialized_project: Path) -> Path:
    """Create a simple .txt file inside the initialized project."""
    f = initialized_project / "notes.txt"
    f.write_text("GPIO pin configuration notes for STM32F407.", encoding="utf-8")
    return f


@pytest.fixture()
def _mock_pipeline(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock heavy pipeline components so add doesn't need Ollama/ChromaDB/tiktoken.

    Patches Pipeline, MarkdownChunker, ChromaStore, and default_registry
    as they will be imported in hwcc.cli.
    """
    mock_process = MagicMock(return_value=10)
    mock_pipeline_cls = MagicMock()
    mock_pipeline_cls.return_value.process = mock_process

    monkeypatch.setattr("hwcc.cli.Pipeline", mock_pipeline_cls)
    monkeypatch.setattr("hwcc.cli.MarkdownChunker", MagicMock())
    monkeypatch.setattr("hwcc.cli.ChromaStore", MagicMock())
    monkeypatch.setattr("hwcc.cli.default_registry", MagicMock())

    return mock_process


# --- No Args / Project Not Initialized ---


class TestAddNoArgs:
    def test_no_args_prints_hint(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(initialized_project)
        result = runner.invoke(app, ["add"])
        assert result.exit_code == 1
        assert "No file" in result.output or "no file" in result.output.lower()

    def test_not_initialized_prints_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["add", "foo.txt"])
        assert result.exit_code == 1
        assert "init" in result.output.lower()


# --- File Not Found ---


class TestAddFileNotFound:
    @pytest.mark.usefixtures("_mock_pipeline")
    def test_nonexistent_file_prints_error(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(initialized_project)
        result = runner.invoke(app, ["add", "nonexistent.pdf"])
        assert "not found" in result.output.lower() or "does not exist" in result.output.lower()


# --- Unsupported Format ---


class TestAddUnsupportedFormat:
    @pytest.mark.usefixtures("_mock_pipeline")
    def test_unsupported_format_prints_warning(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(initialized_project)
        # Create a file with an unrecognized extension
        unknown_file = initialized_project / "data.xyz"
        unknown_file.write_text("some data", encoding="utf-8")
        result = runner.invoke(app, ["add", "data.xyz"])
        assert "unsupported" in result.output.lower() or "no parser" in result.output.lower()


# --- Successful Add ---


class TestAddSuccess:
    @pytest.mark.usefixtures("_mock_pipeline")
    def test_successful_add_updates_manifest(
        self,
        initialized_project: Path,
        txt_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(initialized_project)
        result = runner.invoke(app, ["add", str(txt_file)])
        assert result.exit_code == 0

        # Manifest should now have 1 document
        manifest = load_manifest(initialized_project / RAG_DIR / MANIFEST_FILE)
        assert len(manifest.documents) == 1
        assert manifest.documents[0].id == "notes_txt"

    @pytest.mark.usefixtures("_mock_pipeline")
    def test_successful_add_prints_summary(
        self,
        initialized_project: Path,
        txt_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(initialized_project)
        result = runner.invoke(app, ["add", str(txt_file)])
        assert result.exit_code == 0
        # Should mention the file or chunk count
        assert "notes.txt" in result.output or "1 document" in result.output.lower()

    @pytest.mark.usefixtures("_mock_pipeline")
    def test_add_stores_chunk_count_in_manifest(
        self,
        initialized_project: Path,
        txt_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(initialized_project)
        runner.invoke(app, ["add", str(txt_file)])

        manifest = load_manifest(initialized_project / RAG_DIR / MANIFEST_FILE)
        entry = manifest.get_document("notes_txt")
        assert entry is not None
        assert entry.chunks == 10  # Mock returns 10


# --- Incremental Skip ---


class TestAddIncremental:
    @pytest.mark.usefixtures("_mock_pipeline")
    def test_unchanged_file_is_skipped(
        self,
        initialized_project: Path,
        txt_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(initialized_project)
        # First add
        runner.invoke(app, ["add", str(txt_file)])
        # Second add — same file, unchanged
        result = runner.invoke(app, ["add", str(txt_file)])
        assert result.exit_code == 0
        assert "skip" in result.output.lower() or "unchanged" in result.output.lower()


# --- --chip Flag ---


class TestAddChipFlag:
    def test_chip_flag_stored_in_manifest(
        self,
        initialized_project: Path,
        txt_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(initialized_project)

        mock_process = MagicMock(return_value=5)
        mock_pipeline_cls = MagicMock()
        mock_pipeline_cls.return_value.process = mock_process
        monkeypatch.setattr("hwcc.cli.Pipeline", mock_pipeline_cls)
        monkeypatch.setattr("hwcc.cli.MarkdownChunker", MagicMock())
        monkeypatch.setattr("hwcc.cli.ChromaStore", MagicMock())
        monkeypatch.setattr("hwcc.cli.default_registry", MagicMock())

        result = runner.invoke(app, ["add", "--chip", "NRF52840", str(txt_file)])
        assert result.exit_code == 0

        manifest = load_manifest(initialized_project / RAG_DIR / MANIFEST_FILE)
        entry = manifest.get_document("notes_txt")
        assert entry is not None
        assert entry.chip == "NRF52840"


# --- --type Flag ---


class TestAddTypeFlag:
    def test_type_flag_stored_in_manifest(
        self,
        initialized_project: Path,
        txt_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(initialized_project)

        mock_process = MagicMock(return_value=5)
        mock_pipeline_cls = MagicMock()
        mock_pipeline_cls.return_value.process = mock_process
        monkeypatch.setattr("hwcc.cli.Pipeline", mock_pipeline_cls)
        monkeypatch.setattr("hwcc.cli.MarkdownChunker", MagicMock())
        monkeypatch.setattr("hwcc.cli.ChromaStore", MagicMock())
        monkeypatch.setattr("hwcc.cli.default_registry", MagicMock())

        result = runner.invoke(app, ["add", "--type", "errata", str(txt_file)])
        assert result.exit_code == 0

        manifest = load_manifest(initialized_project / RAG_DIR / MANIFEST_FILE)
        entry = manifest.get_document("notes_txt")
        assert entry is not None
        assert entry.doc_type == "errata"


# --- Multiple Files ---


class TestAddMultipleFiles:
    @pytest.mark.usefixtures("_mock_pipeline")
    def test_multiple_files_processed(
        self,
        initialized_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(initialized_project)
        f1 = initialized_project / "file1.txt"
        f2 = initialized_project / "file2.txt"
        f1.write_text("Content one", encoding="utf-8")
        f2.write_text("Content two", encoding="utf-8")

        result = runner.invoke(app, ["add", str(f1), str(f2)])
        assert result.exit_code == 0

        manifest = load_manifest(initialized_project / RAG_DIR / MANIFEST_FILE)
        assert len(manifest.documents) == 2


# --- Pipeline Error ---


class TestAddPipelineError:
    def test_pipeline_error_continues_to_next_file(
        self,
        initialized_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(initialized_project)

        from hwcc.exceptions import PipelineError

        # First file fails, second succeeds
        mock_process = MagicMock(side_effect=[PipelineError("Embedding failed"), 5])
        mock_pipeline_cls = MagicMock()
        mock_pipeline_cls.return_value.process = mock_process
        monkeypatch.setattr("hwcc.cli.Pipeline", mock_pipeline_cls)
        monkeypatch.setattr("hwcc.cli.MarkdownChunker", MagicMock())
        mock_store = MagicMock()
        monkeypatch.setattr("hwcc.cli.ChromaStore", mock_store)
        monkeypatch.setattr("hwcc.cli.default_registry", MagicMock())

        f1 = initialized_project / "file1.txt"
        f2 = initialized_project / "file2.txt"
        f1.write_text("Content one", encoding="utf-8")
        f2.write_text("Content two", encoding="utf-8")

        result = runner.invoke(app, ["add", str(f1), str(f2)])
        # Should print error for first file
        assert "error" in result.output.lower() or "failed" in result.output.lower()
        # Second file should succeed and appear in manifest
        manifest = load_manifest(initialized_project / RAG_DIR / MANIFEST_FILE)
        assert len(manifest.documents) == 1
        assert manifest.documents[0].id == "file2_txt"

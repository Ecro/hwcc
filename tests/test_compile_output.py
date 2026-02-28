"""Tests for hwcc.compile.output — OutputCompiler with non-destructive injection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hwcc.compile.output import OutputCompiler
from hwcc.config import (
    HardwareConfig,
    HwccConfig,
    OutputConfig,
    ProjectConfig,
)
from hwcc.exceptions import CompileError
from hwcc.store.base import BaseStore

if TYPE_CHECKING:
    from pathlib import Path

    from hwcc.types import Chunk, ChunkMetadata, EmbeddedChunk, SearchResult


# ---------------------------------------------------------------------------
# Fake store for unit testing (avoids ChromaDB dependency)
# ---------------------------------------------------------------------------


class FakeStore(BaseStore):
    """Minimal BaseStore stand-in for unit tests."""

    def add(self, chunks: list[EmbeddedChunk], doc_id: str) -> int:
        return 0

    def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        where: dict[str, str] | None = None,
    ) -> list[SearchResult]:
        return []

    def delete(self, doc_id: str) -> int:
        return 0

    def get_chunk_metadata(
        self,
        where: dict[str, str] | None = None,
    ) -> list[ChunkMetadata]:
        return []

    def get_chunks(
        self,
        where: dict[str, str] | None = None,
    ) -> list[Chunk]:
        return []

    def count(self) -> int:
        return 0


# ---------------------------------------------------------------------------
# Markers (must match templates.py)
# ---------------------------------------------------------------------------

_BEGIN = "<!-- BEGIN HWCC CONTEXT (auto-generated, do not edit) -->"
_END = "<!-- END HWCC CONTEXT -->"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory with .rag/ structure."""
    rag_dir = tmp_path / ".rag"
    rag_dir.mkdir()
    return tmp_path


@pytest.fixture
def config() -> HwccConfig:
    """Config with default output targets."""
    return HwccConfig(
        project=ProjectConfig(name="TestProject"),
        hardware=HardwareConfig(mcu="STM32F407"),
    )


@pytest.fixture
def single_target_config() -> HwccConfig:
    """Config with only claude target."""
    return HwccConfig(
        project=ProjectConfig(name="TestProject"),
        hardware=HardwareConfig(mcu="STM32F407"),
        output=OutputConfig(targets=["claude"]),
    )


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


# ---------------------------------------------------------------------------
# Tests: Basic compilation
# ---------------------------------------------------------------------------


class TestOutputCompilerBasic:
    def test_generates_output_files_for_all_configured_targets(
        self, project_dir: Path, config: HwccConfig, store: FakeStore
    ):
        compiler = OutputCompiler(project_dir)
        paths = compiler.compile(store, config)

        # Default targets: claude, codex, cursor, gemini
        assert len(paths) == 4
        filenames = {p.name for p in paths}
        assert "CLAUDE.md" in filenames
        assert "AGENTS.md" in filenames
        assert "hardware.mdc" in filenames
        assert "GEMINI.md" in filenames

    def test_returns_list_of_written_paths(
        self, project_dir: Path, config: HwccConfig, store: FakeStore
    ):
        compiler = OutputCompiler(project_dir)
        paths = compiler.compile(store, config)

        for p in paths:
            assert p.exists()
            assert p.stat().st_size > 0

    def test_creates_parent_directories(
        self, project_dir: Path, config: HwccConfig, store: FakeStore
    ):
        compiler = OutputCompiler(project_dir)
        compiler.compile(store, config)

        # .cursor/rules/ and .gemini/ should be created
        assert (project_dir / ".cursor" / "rules").is_dir()
        assert (project_dir / ".gemini").is_dir()

    def test_single_target_config_generates_only_that_target(
        self,
        project_dir: Path,
        single_target_config: HwccConfig,
        store: FakeStore,
    ):
        compiler = OutputCompiler(project_dir)
        paths = compiler.compile(store, single_target_config)

        assert len(paths) == 1
        assert paths[0].name == "CLAUDE.md"
        # Others should not exist
        assert not (project_dir / "AGENTS.md").exists()

    def test_skips_unknown_targets_with_warning(
        self, project_dir: Path, store: FakeStore, caplog: pytest.LogCaptureFixture
    ):
        config = HwccConfig(
            output=OutputConfig(targets=["claude", "nonexistent"]),
        )
        compiler = OutputCompiler(project_dir)
        paths = compiler.compile(store, config)

        # Should still produce claude output
        assert len(paths) == 1
        assert paths[0].name == "CLAUDE.md"
        assert "nonexistent" in caplog.text

    def test_wraps_exceptions_in_compile_error(
        self, project_dir: Path, config: HwccConfig, store: FakeStore
    ):
        compiler = OutputCompiler(project_dir)
        # Make project_dir read-only to trigger write failure
        target = project_dir / "CLAUDE.md"
        target.write_text("existing", encoding="utf-8")
        target.chmod(0o000)

        try:
            with pytest.raises(CompileError, match="Failed to compile"):
                compiler.compile(store, config)
        finally:
            target.chmod(0o644)

    def test_empty_store_produces_valid_output(self, project_dir: Path, store: FakeStore):
        config = HwccConfig(
            output=OutputConfig(targets=["claude"]),
        )
        compiler = OutputCompiler(project_dir)
        paths = compiler.compile(store, config)

        assert len(paths) == 1
        content = paths[0].read_text(encoding="utf-8")
        assert _BEGIN in content
        assert _END in content


# ---------------------------------------------------------------------------
# Tests: Hot context embedding
# ---------------------------------------------------------------------------


class TestOutputCompilerHotContext:
    def test_reads_hot_context_from_file(self, project_dir: Path, store: FakeStore):
        # Write a pre-rendered hot context
        context_dir = project_dir / ".rag" / "context"
        context_dir.mkdir(parents=True, exist_ok=True)
        hot_md = context_dir / "hot.md"
        hot_md.write_text("# Hardware Summary\n\n- MCU: STM32F407\n", encoding="utf-8")

        config = HwccConfig(output=OutputConfig(targets=["claude"]))
        compiler = OutputCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        assert "Hardware Summary" in content
        assert "STM32F407" in content

    def test_works_without_hot_context_file(self, project_dir: Path, store: FakeStore):
        config = HwccConfig(
            hardware=HardwareConfig(mcu="NRF52840"),
            output=OutputConfig(targets=["claude"]),
        )
        compiler = OutputCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        # Should render inline fallback with MCU info
        assert "NRF52840" in content
        assert _BEGIN in content


# ---------------------------------------------------------------------------
# Tests: Non-destructive injection
# ---------------------------------------------------------------------------


class TestOutputCompilerInjection:
    def test_creates_new_file_when_none_exists(self, project_dir: Path, store: FakeStore):
        config = HwccConfig(output=OutputConfig(targets=["claude"]))
        compiler = OutputCompiler(project_dir)

        assert not (project_dir / "CLAUDE.md").exists()
        paths = compiler.compile(store, config)

        assert (project_dir / "CLAUDE.md").exists()
        content = paths[0].read_text(encoding="utf-8")
        assert _BEGIN in content
        assert _END in content

    def test_preserves_content_before_markers(self, project_dir: Path, store: FakeStore):
        # Write existing file with user content + markers
        existing = f"# My Project\n\nUser content here.\n\n{_BEGIN}\nold hwcc content\n{_END}\n"
        claude_md = project_dir / "CLAUDE.md"
        claude_md.write_text(existing, encoding="utf-8")

        config = HwccConfig(output=OutputConfig(targets=["claude"]))
        compiler = OutputCompiler(project_dir)
        compiler.compile(store, config)

        content = claude_md.read_text(encoding="utf-8")
        assert content.startswith("# My Project\n\nUser content here.\n\n")
        assert "old hwcc content" not in content
        assert _BEGIN in content
        assert _END in content

    def test_preserves_content_after_markers(self, project_dir: Path, store: FakeStore):
        existing = (
            f"{_BEGIN}\nold hwcc content\n{_END}\n\n## My Custom Section\n\nDo not delete this.\n"
        )
        claude_md = project_dir / "CLAUDE.md"
        claude_md.write_text(existing, encoding="utf-8")

        config = HwccConfig(output=OutputConfig(targets=["claude"]))
        compiler = OutputCompiler(project_dir)
        compiler.compile(store, config)

        content = claude_md.read_text(encoding="utf-8")
        assert "My Custom Section" in content
        assert "Do not delete this." in content
        assert "old hwcc content" not in content

    def test_replaces_marker_section_on_recompile(self, project_dir: Path, store: FakeStore):
        config = HwccConfig(
            hardware=HardwareConfig(mcu="STM32F407"),
            output=OutputConfig(targets=["claude"]),
        )
        compiler = OutputCompiler(project_dir)

        # First compile
        compiler.compile(store, config)
        first_content = (project_dir / "CLAUDE.md").read_text(encoding="utf-8")
        assert "STM32F407" in first_content

        # Second compile with different MCU
        config2 = HwccConfig(
            hardware=HardwareConfig(mcu="NRF52840"),
            output=OutputConfig(targets=["claude"]),
        )
        compiler.compile(store, config2)
        second_content = (project_dir / "CLAUDE.md").read_text(encoding="utf-8")

        assert "NRF52840" in second_content
        assert "STM32F407" not in second_content
        # Should have exactly one pair of markers
        assert second_content.count(_BEGIN) == 1
        assert second_content.count(_END) == 1

    def test_appends_when_no_markers_exist(self, project_dir: Path, store: FakeStore):
        existing = "# My Project\n\nSome user content.\n"
        claude_md = project_dir / "CLAUDE.md"
        claude_md.write_text(existing, encoding="utf-8")

        config = HwccConfig(output=OutputConfig(targets=["claude"]))
        compiler = OutputCompiler(project_dir)
        compiler.compile(store, config)

        content = claude_md.read_text(encoding="utf-8")
        # User content preserved at start
        assert content.startswith("# My Project\n\nSome user content.")
        # Markers appended
        assert _BEGIN in content
        assert _END in content

    def test_handles_malformed_markers_begin_without_end(
        self, project_dir: Path, store: FakeStore
    ):
        existing = f"# My Project\n\n{_BEGIN}\nbroken content without end\n"
        claude_md = project_dir / "CLAUDE.md"
        claude_md.write_text(existing, encoding="utf-8")

        config = HwccConfig(output=OutputConfig(targets=["claude"]))
        compiler = OutputCompiler(project_dir)
        compiler.compile(store, config)

        content = claude_md.read_text(encoding="utf-8")
        # Should still have valid markers
        assert _BEGIN in content
        assert _END in content

    def test_idempotent_rerun_produces_same_result(self, project_dir: Path, store: FakeStore):
        """Running compile twice with same inputs produces identical output."""
        # Add user content around markers
        existing = "# My Project\n\nUser notes.\n"
        claude_md = project_dir / "CLAUDE.md"
        claude_md.write_text(existing, encoding="utf-8")

        config = HwccConfig(
            hardware=HardwareConfig(mcu="STM32F407"),
            output=OutputConfig(targets=["claude"]),
        )
        compiler = OutputCompiler(project_dir)

        compiler.compile(store, config)
        first = claude_md.read_text(encoding="utf-8")

        compiler.compile(store, config)
        second = claude_md.read_text(encoding="utf-8")

        # Content should be identical (modulo generated_at timestamp)
        # Strip timestamps for comparison
        first_stripped = "\n".join(
            line for line in first.splitlines() if "Generated by hwcc" not in line
        )
        second_stripped = "\n".join(
            line for line in second.splitlines() if "Generated by hwcc" not in line
        )
        assert first_stripped == second_stripped

    def test_cursor_recompile_does_not_duplicate_frontmatter(
        self, project_dir: Path, store: FakeStore
    ):
        """Cursor YAML frontmatter must not duplicate on re-compile."""
        config = HwccConfig(output=OutputConfig(targets=["cursor"]))
        compiler = OutputCompiler(project_dir)

        compiler.compile(store, config)
        mdc_path = project_dir / ".cursor" / "rules" / "hardware.mdc"
        first = mdc_path.read_text(encoding="utf-8")

        compiler.compile(store, config)
        second = mdc_path.read_text(encoding="utf-8")

        # Frontmatter should appear exactly once
        assert second.count("description:") == 1
        # Markers should appear exactly once
        assert second.count(_BEGIN) == 1
        assert second.count(_END) == 1
        # File should not grow
        assert first.count("---") == second.count("---")

    def test_malformed_markers_cleaned_on_recompile(self, project_dir: Path, store: FakeStore):
        """After fixing a malformed-marker file, subsequent re-compile should be clean."""
        # Write file with orphan BEGIN marker (no END)
        existing = f"# My Project\n\n{_BEGIN}\nbroken content\n"
        claude_md = project_dir / "CLAUDE.md"
        claude_md.write_text(existing, encoding="utf-8")

        config = HwccConfig(output=OutputConfig(targets=["claude"]))
        compiler = OutputCompiler(project_dir)

        # First compile fixes the malformed state
        compiler.compile(store, config)
        first = claude_md.read_text(encoding="utf-8")
        assert first.count(_BEGIN) == 1
        assert first.count(_END) == 1

        # Second compile should be idempotent
        compiler.compile(store, config)
        second = claude_md.read_text(encoding="utf-8")
        assert second.count(_BEGIN) == 1
        assert second.count(_END) == 1


# ---------------------------------------------------------------------------
# Tests: Rendered content
# ---------------------------------------------------------------------------


class TestOutputCompilerContent:
    def test_claude_output_contains_markers(self, project_dir: Path, store: FakeStore):
        config = HwccConfig(output=OutputConfig(targets=["claude"]))
        compiler = OutputCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        assert content.strip().startswith(_BEGIN) or _BEGIN in content
        assert _END in content

    def test_cursor_output_has_mdc_frontmatter(self, project_dir: Path, store: FakeStore):
        config = HwccConfig(output=OutputConfig(targets=["cursor"]))
        compiler = OutputCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "description:" in content
        assert "globs:" in content

    def test_output_contains_hwcc_version(self, project_dir: Path, store: FakeStore):
        config = HwccConfig(output=OutputConfig(targets=["claude"]))
        compiler = OutputCompiler(project_dir)
        paths = compiler.compile(store, config)

        content = paths[0].read_text(encoding="utf-8")
        assert "hwcc v" in content

    def test_all_five_targets_render_successfully(self, project_dir: Path, store: FakeStore):
        config = HwccConfig(
            output=OutputConfig(targets=["claude", "codex", "cursor", "gemini", "copilot"]),
        )
        compiler = OutputCompiler(project_dir)
        paths = compiler.compile(store, config)

        assert len(paths) == 5
        for p in paths:
            content = p.read_text(encoding="utf-8")
            assert _BEGIN in content
            assert _END in content

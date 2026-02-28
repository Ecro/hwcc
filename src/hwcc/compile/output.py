"""Output file compiler — generates tool-specific context files.

Renders target templates (CLAUDE.md, AGENTS.md, .cursorrules, etc.) and
injects the rendered content into existing files using marker-based
non-destructive injection.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from hwcc.compile.base import BaseCompiler
from hwcc.compile.context import CompileContext
from hwcc.compile.templates import TARGET_REGISTRY, TemplateEngine
from hwcc.exceptions import CompileError

if TYPE_CHECKING:
    from pathlib import Path

    from hwcc.config import HwccConfig
    from hwcc.store.base import BaseStore

__all__ = ["OutputCompiler"]

logger = logging.getLogger(__name__)


class OutputCompiler(BaseCompiler):
    """Compiles tool-specific output files with non-destructive injection.

    For each configured target (claude, codex, cursor, gemini, copilot),
    renders the corresponding Jinja2 template and injects the result
    into the target file using ``<!-- BEGIN/END HWCC CONTEXT -->`` markers.

    Existing user content outside the markers is preserved.

    Must be invoked after ``HotContextCompiler`` has generated
    ``.rag/context/hot.md`` — the hot context is embedded into each
    output file. If ``hot.md`` is absent, output files will contain
    a minimal fallback with only MCU/config data.
    """

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._rag_dir = project_root / ".rag"
        self._engine = TemplateEngine(project_root)

    def compile(self, store: BaseStore, config: HwccConfig) -> list[Path]:
        """Compile output files for all configured targets.

        Args:
            store: Vector store (unused directly, but required by ABC).
            config: Project configuration with output targets.

        Returns:
            List of paths to generated/updated output files.

        Raises:
            CompileError: If compilation fails.
        """
        try:
            context = self._build_context(config)
            output_paths: list[Path] = []

            for target in config.output.targets:
                if target not in TARGET_REGISTRY:
                    logger.warning(
                        "Unknown output target %r, skipping (supported: %s)",
                        target,
                        ", ".join(sorted(TARGET_REGISTRY)),
                    )
                    continue

                info = TARGET_REGISTRY[target]
                rendered = self._engine.render_target(target, context)
                output_path = self._project_root / info.output_path

                # Ensure parent directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Non-destructive injection
                self._inject_content(output_path, rendered, info.begin_marker, info.end_marker)
                output_paths.append(output_path)

                logger.info("Compiled output: %s", info.output_path)

            logger.info("Compiled %d output files", len(output_paths))

        except CompileError:
            raise
        except Exception as e:
            raise CompileError(f"Failed to compile output files: {e}") from e

        return output_paths

    def _build_context(self, config: HwccConfig) -> CompileContext:
        """Build CompileContext from config and pre-rendered hot context."""
        context = CompileContext.from_config(config)

        # Read pre-rendered hot context if available
        hot_context = self._read_hot_context()
        if hot_context:
            context = replace(context, hot_context=hot_context)

        return context

    def _read_hot_context(self) -> str:
        """Read pre-rendered hot context from .rag/context/hot.md.

        Returns:
            Hot context content, or empty string if not available.
        """
        hot_path = self._rag_dir / "context" / "hot.md"
        if not hot_path.exists():
            return ""

        try:
            return hot_path.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("Could not read hot context from %s", hot_path)
            return ""

    @staticmethod
    def _inject_content(
        path: Path,
        rendered: str,
        begin_marker: str,
        end_marker: str,
    ) -> None:
        """Write rendered content to file with non-destructive injection.

        If the file exists and contains both markers, the section between
        (and including) the markers is replaced. If the file exists but
        has no markers, the rendered content is appended. If the file
        does not exist, it is created with just the rendered content.

        Args:
            path: Output file path.
            rendered: Rendered template content (includes markers).
            begin_marker: Begin marker string.
            end_marker: End marker string.
        """
        if not path.exists():
            path.write_text(rendered, encoding="utf-8")
            return

        existing = path.read_text(encoding="utf-8")
        begin_idx = existing.find(begin_marker)
        end_idx = existing.find(end_marker)

        if begin_idx >= 0 and end_idx >= 0 and end_idx > begin_idx:
            # Extract only the marker-bounded section from rendered content
            # (prevents duplication of pre-marker content like cursor frontmatter)
            rendered_begin = rendered.find(begin_marker)
            rendered_section = rendered[rendered_begin:] if rendered_begin >= 0 else rendered

            # Replace existing marker section, consuming trailing newline
            after_end = end_idx + len(end_marker)
            trailing = existing[after_end:]
            if trailing.startswith("\n"):
                trailing = trailing[1:]
            new_content = existing[:begin_idx] + rendered_section + trailing
        elif begin_idx >= 0:
            # Malformed: begin marker without matching end marker
            logger.warning(
                "Found BEGIN marker without END marker in %s, appending fresh section",
                path.name,
            )
            # Remove orphan begin marker to prevent future mis-replacement
            cleaned = existing[:begin_idx] + existing[begin_idx + len(begin_marker) :]
            new_content = cleaned.rstrip() + "\n\n" + rendered
        else:
            # No markers found — append
            new_content = existing.rstrip() + "\n\n" + rendered

        path.write_text(new_content, encoding="utf-8")

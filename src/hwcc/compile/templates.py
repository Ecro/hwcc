"""Jinja2 template engine for context compilation.

Loads templates from built-in and user-override directories, renders them
with typed CompileContext data. User overrides in .rag/templates/ take
precedence over built-in templates in src/hwcc/templates/.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path, PurePosixPath

import jinja2

from hwcc.compile.context import CompileContext, TargetInfo
from hwcc.exceptions import CompileError

__all__ = [
    "TARGET_REGISTRY",
    "TemplateEngine",
]

logger = logging.getLogger(__name__)

_BEGIN_MARKER = "<!-- BEGIN HWCC CONTEXT (auto-generated, do not edit) -->"
_END_MARKER = "<!-- END HWCC CONTEXT -->"

TARGET_REGISTRY: dict[str, TargetInfo] = {
    "claude": TargetInfo(
        template="claude.md.j2",
        output_path=PurePosixPath("CLAUDE.md"),
        begin_marker=_BEGIN_MARKER,
        end_marker=_END_MARKER,
        description="Claude Code context file",
    ),
    "codex": TargetInfo(
        template="agents.md.j2",
        output_path=PurePosixPath("AGENTS.md"),
        begin_marker=_BEGIN_MARKER,
        end_marker=_END_MARKER,
        description="OpenAI Codex agent instructions",
    ),
    "cursor": TargetInfo(
        template="cursor.mdc.j2",
        output_path=PurePosixPath(".cursor/rules/hardware.mdc"),
        begin_marker=_BEGIN_MARKER,
        end_marker=_END_MARKER,
        description="Cursor IDE rules file",
    ),
    "gemini": TargetInfo(
        template="gemini.md.j2",
        output_path=PurePosixPath(".gemini/GEMINI.md"),
        begin_marker=_BEGIN_MARKER,
        end_marker=_END_MARKER,
        description="Google Gemini CLI context file",
    ),
    "copilot": TargetInfo(
        template="copilot.md.j2",
        output_path=PurePosixPath(".github/copilot-instructions.md"),
        begin_marker=_BEGIN_MARKER,
        end_marker=_END_MARKER,
        description="GitHub Copilot instructions",
    ),
}


class TemplateEngine:
    """Jinja2 template engine with built-in and user-override support.

    Template search order:
      1. .rag/templates/ (user overrides, optional)
      2. src/hwcc/templates/ (built-in, always present)

    Args:
        project_root: Project root directory. If provided, enables user
            template overrides from ``project_root/.rag/templates/``.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        from importlib.resources import files

        search_paths: list[str] = []
        self._user_template_dir: Path | None = None

        # User override directory (checked first)
        if project_root is not None:
            user_dir = project_root / ".rag" / "templates"
            self._user_template_dir = user_dir
            if user_dir.is_dir():
                search_paths.append(str(user_dir))
                logger.info("User template overrides enabled: %s", user_dir)

        # Built-in templates (fallback)
        builtin_dir = Path(str(files("hwcc") / "templates"))
        if not builtin_dir.is_dir():
            logger.debug("Expected template dir at: %s", builtin_dir)
            raise CompileError(
                "Built-in template directory not found — installation may be corrupted"
            )
        search_paths.append(str(builtin_dir))

        self._loader = jinja2.FileSystemLoader(search_paths)
        self._env = jinja2.Environment(
            loader=self._loader,
            autoescape=False,
            undefined=jinja2.StrictUndefined,
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        logger.info("TemplateEngine initialized with %d search path(s)", len(search_paths))

    def render(self, template_name: str, context: CompileContext) -> str:
        """Render a template with the given compile context.

        Context is flattened via ``dataclasses.asdict()`` before passing
        to Jinja2. Nested dataclasses become dicts; tuples become lists.

        Args:
            template_name: Template filename (e.g., ``"hot_context.md.j2"``).
            context: Typed compile context data.

        Returns:
            Rendered template content as a string.

        Raises:
            CompileError: If the template is not found or rendering fails.
        """
        try:
            template = self._env.get_template(template_name)
        except jinja2.TemplateNotFound as e:
            raise CompileError(f"Template not found: {template_name}") from e

        try:
            return template.render(**asdict(context))
        except jinja2.TemplateError as e:
            raise CompileError(f"Failed to render template {template_name}: {e}") from e

    def render_target(self, target: str, context: CompileContext) -> str:
        """Render the template for a specific output target.

        Args:
            target: Config target name (e.g., ``"claude"``, ``"codex"``).
            context: Typed compile context data.

        Returns:
            Rendered template content as a string.

        Raises:
            CompileError: If the target is unknown or rendering fails.
        """
        info = self.get_target_info(target)
        return self.render(info.template, context)

    def list_templates(self) -> list[str]:
        """List all available template names (built-in + overrides)."""
        return sorted(self._loader.list_templates())

    def is_overridden(self, template_name: str) -> bool:
        """Check if a template has a user override in .rag/templates/.

        Returns False if no project root was provided or the user
        override directory does not exist.
        """
        if self._user_template_dir is None:
            return False
        return (self._user_template_dir / template_name).is_file()

    @staticmethod
    def get_target_info(target: str) -> TargetInfo:
        """Get the TargetInfo for a config target name.

        Args:
            target: Config target name (e.g., ``"claude"``).

        Raises:
            CompileError: If the target is not in the registry.
        """
        if target not in TARGET_REGISTRY:
            supported = ", ".join(sorted(TARGET_REGISTRY))
            raise CompileError(
                f"Unknown output target: {target!r}. Supported targets: {supported}"
            )
        return TARGET_REGISTRY[target]

    @staticmethod
    def supported_targets() -> list[str]:
        """List all supported output target names."""
        return sorted(TARGET_REGISTRY)

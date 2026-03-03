"""Vision provider that captions figures using the Claude CLI (claude -p).

Requires ``claude`` to be in PATH. Uses the user's existing Claude subscription —
no API key or additional billing required.

Limitation: blocked when run inside a Claude Code session (CLAUDECODE env var).
In that case, ``is_available()`` returns False and a warning is logged.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from hwcc.vision.base import HARDWARE_CAPTION_PROMPT, BaseVisionProvider

__all__ = ["ClaudeCliVisionProvider"]

logger = logging.getLogger(__name__)

_SUBPROCESS_TIMEOUT = 120  # seconds per figure


class ClaudeCliVisionProvider(BaseVisionProvider):
    """Caption figures by calling ``claude -p`` as a subprocess.

    Uses the user's existing Claude subscription. Full Claude quality.

    Not available when:
    - ``CLAUDECODE`` env var is set (nested session prevention)
    - ``claude`` is not found in PATH
    """

    def is_available(self) -> bool:
        """Return True if claude CLI is usable in this context."""
        if os.environ.get("CLAUDECODE"):
            logger.warning(
                "claude_cli vision provider unavailable: running inside a Claude Code "
                "session. Run 'hwcc add' from a standalone terminal to enable figure "
                "captioning. Using layout detection only (figure placeholders without "
                "captions)."
            )
            return False
        if shutil.which("claude") is None:
            logger.warning(
                "claude_cli vision provider unavailable: 'claude' not found in PATH. "
                "Install Claude Code CLI or choose a different vision provider."
            )
            return False
        return True

    def caption_image(self, image_bytes: bytes, context: str = "") -> str:
        """Caption an image using ``claude -p``.

        Writes image to a temp file, calls ``claude -p "Read {path} and describe..."``
        with ``--allowedTools Read``, and returns the stdout.

        Args:
            image_bytes: Raw PNG or JPEG image data.
            context: Surrounding text context (e.g. PDF caption near the figure).

        Returns:
            Text caption from Claude, or empty string on failure.
        """
        if not image_bytes:
            return ""

        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".png", delete=False, prefix="hwcc_figure_"
            ) as tmp:
                tmp.write(image_bytes)
                tmp_path = Path(tmp.name)

            prompt = _build_prompt(tmp_path, context)

            result = subprocess.run(
                ["claude", "-p", prompt, "--allowedTools", "Read"],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )

            if result.returncode != 0:
                logger.warning(
                    "claude -p exited with code %d: %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                return ""

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            logger.warning("claude -p timed out after %ds captioning figure", _SUBPROCESS_TIMEOUT)
            return ""
        except OSError as e:
            logger.warning("claude -p failed: %s", e)
            return ""
        finally:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink()


def _build_prompt(image_path: Path, context: str) -> str:
    """Build the prompt string for claude -p."""
    parts = [f"Read {image_path} and describe the hardware diagram."]
    if context:
        parts.append(f"Context from the document: {context}")
    parts.append(HARDWARE_CAPTION_PROMPT)
    return " ".join(parts)

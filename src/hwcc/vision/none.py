"""Null vision provider — no-op captioning (default)."""

from __future__ import annotations

from hwcc.vision.base import BaseVisionProvider

__all__ = ["NullVisionProvider"]


class NullVisionProvider(BaseVisionProvider):
    """No-op provider that returns empty captions.

    Used when ``[vision] provider = "none"`` (the default). Figures get
    type-classified placeholders without AI-generated descriptions.
    """

    def caption_image(self, image_bytes: bytes, context: str = "") -> str:
        """Return empty string — no captioning performed."""
        return ""

    def is_available(self) -> bool:
        """Always available — no dependencies required."""
        return True

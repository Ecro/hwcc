"""Abstract base class for vision providers (figure captioning)."""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["HARDWARE_CAPTION_PROMPT", "BaseVisionProvider"]

HARDWARE_CAPTION_PROMPT = (
    "Describe this hardware diagram for an embedded systems engineer. "
    "Focus on: signal names, timing parameters (setup/hold times, frequencies), "
    "register addresses, pin numbers, bus topology, and any labeled values. "
    "Be concise and technical."
)


class BaseVisionProvider(ABC):
    """Base class for all vision captioning providers.

    Subclasses must implement ``caption_image`` and ``is_available``.
    """

    @abstractmethod
    def caption_image(self, image_bytes: bytes, context: str = "") -> str:
        """Caption an image.

        Args:
            image_bytes: Raw image data (PNG or JPEG).
            context: Surrounding text context (e.g. nearby caption from PDF).

        Returns:
            Text description of the image, or empty string if captioning fails.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider's dependencies are installed and usable."""

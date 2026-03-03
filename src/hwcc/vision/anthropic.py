"""Vision provider that captions figures using the Anthropic API."""

from __future__ import annotations

import base64
import logging
import os

from hwcc.vision.base import HARDWARE_CAPTION_PROMPT, BaseVisionProvider

__all__ = ["AnthropicVisionProvider"]

logger = logging.getLogger(__name__)


class AnthropicVisionProvider(BaseVisionProvider):
    """Caption figures using the Anthropic messages API.

    Requires the ``anthropic`` Python package and an API key.

    Args:
        model: Anthropic model to use (e.g. ``"claude-haiku-4-5-20251001"``).
        api_key: API key string. If empty, read from ``api_key_env`` env var.
        api_key_env: Name of env var holding the API key (default: ``ANTHROPIC_API_KEY``).
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        api_key: str = "",
        api_key_env: str = "ANTHROPIC_API_KEY",
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._api_key_env = api_key_env

    def is_available(self) -> bool:
        """Return True if the ``anthropic`` package is importable."""
        try:
            import anthropic  # noqa: F401

            return True
        except ImportError:
            logger.warning(
                "anthropic vision provider unavailable: 'anthropic' package not installed. "
                "Install with: pip install hwcc[vision-anthropic]"
            )
            return False

    def caption_image(self, image_bytes: bytes, context: str = "") -> str:
        """Caption an image using the Anthropic messages API.

        Args:
            image_bytes: Raw PNG or JPEG image data.
            context: Surrounding text context.

        Returns:
            Text caption, or empty string on failure.
        """
        if not image_bytes:
            return ""

        try:
            import anthropic as anthropic_mod
        except ImportError:
            return ""

        api_key = self._api_key or os.environ.get(self._api_key_env, "")
        if not api_key:
            logger.warning(
                "anthropic vision provider: no API key found. "
                "Set %s environment variable.",
                self._api_key_env,
            )
            return ""

        prompt = HARDWARE_CAPTION_PROMPT
        if context:
            prompt = f"Context from document: {context}\n\n{prompt}"

        media_type = "image/jpeg" if image_bytes[:2] == b"\xff\xd8" else "image/png"

        try:
            client = anthropic_mod.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64.b64encode(image_bytes).decode(),
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            return str(message.content[0].text).strip()
        except anthropic_mod.APIError as e:
            logger.warning("Anthropic API error during captioning: %s", e)
            return ""
        except (IndexError, AttributeError) as e:
            logger.warning("Unexpected Anthropic response format: %s", e)
            return ""

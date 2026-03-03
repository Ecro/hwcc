"""Vision providers for multimodal PDF figure captioning.

Providers caption extracted figure images from hardware datasheets.
All providers are optional — the default ``NullVisionProvider`` returns
empty strings so figures get type-classified placeholders without AI captions.

Usage::

    from hwcc.vision import get_vision_provider
    from hwcc.config import VisionConfig

    cfg = VisionConfig(provider="claude_cli")
    provider = get_vision_provider(cfg)
    caption = provider.caption_image(image_bytes, context="Figure 8. SPI timing")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hwcc.vision.anthropic import AnthropicVisionProvider
from hwcc.vision.base import HARDWARE_CAPTION_PROMPT, BaseVisionProvider
from hwcc.vision.claude_cli import ClaudeCliVisionProvider
from hwcc.vision.none import NullVisionProvider
from hwcc.vision.ollama import OllamaVisionProvider

if TYPE_CHECKING:
    from hwcc.config import VisionConfig

__all__ = [
    "HARDWARE_CAPTION_PROMPT",
    "AnthropicVisionProvider",
    "BaseVisionProvider",
    "ClaudeCliVisionProvider",
    "NullVisionProvider",
    "OllamaVisionProvider",
    "get_vision_provider",
]


def get_vision_provider(config: VisionConfig) -> BaseVisionProvider:
    """Create a vision provider from config.

    Args:
        config: VisionConfig with provider name and optional model/key settings.

    Returns:
        A BaseVisionProvider instance.

    Raises:
        ValueError: If the provider name is not recognised.
    """
    provider_name = config.provider

    if provider_name == "none":
        return NullVisionProvider()

    if provider_name == "claude_cli":
        return ClaudeCliVisionProvider()

    if provider_name == "ollama":
        return OllamaVisionProvider(model=config.model or "llama3.2-vision")

    if provider_name == "anthropic":
        return AnthropicVisionProvider(
            model=config.model or "claude-haiku-4-5-20251001",
            api_key_env=config.api_key_env or "ANTHROPIC_API_KEY",
        )

    raise ValueError(
        f"Unknown vision provider: {provider_name!r}. "
        f"Available: none, claude_cli, ollama, anthropic"
    )

"""Vision provider that captions figures using a local Ollama vision model."""

from __future__ import annotations

import base64
import json
import logging
import urllib.request

from hwcc.vision.base import HARDWARE_CAPTION_PROMPT, BaseVisionProvider

__all__ = ["OllamaVisionProvider"]

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_REQUEST_TIMEOUT = 120  # seconds


class OllamaVisionProvider(BaseVisionProvider):
    """Caption figures using a local Ollama vision model.

    Requires Ollama to be running and a vision-capable model installed.
    Recommended models: ``llama3.2-vision``, ``llava``, ``qwen2.5vl``.

    Uses only stdlib ``urllib`` — no extra dependencies.
    """

    def __init__(self, model: str = "llama3.2-vision", base_url: str = _DEFAULT_BASE_URL) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        """Return True if Ollama is reachable at the configured URL."""
        try:
            urllib.request.urlopen(
                f"{self.base_url}/api/tags", timeout=3
            )
            return True
        except OSError:
            logger.warning(
                "ollama vision provider unavailable: cannot reach %s. "
                "Is Ollama running? Start it with: ollama serve",
                self.base_url,
            )
            return False

    def caption_image(self, image_bytes: bytes, context: str = "") -> str:
        """Caption an image using Ollama's generate API with base64-encoded image.

        Args:
            image_bytes: Raw PNG or JPEG image data.
            context: Surrounding text context.

        Returns:
            Text caption, or empty string on failure.
        """
        if not image_bytes:
            return ""

        prompt = HARDWARE_CAPTION_PROMPT
        if context:
            prompt = f"Context: {context}\n\n{prompt}"

        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "images": [base64.b64encode(image_bytes).decode()],
                "stream": False,
            }
        ).encode()

        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read())
            return str(data.get("response", "")).strip()
        except OSError as e:
            logger.warning("Ollama captioning failed: %s", e)
            return ""
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Ollama response parse error: %s", e)
            return ""

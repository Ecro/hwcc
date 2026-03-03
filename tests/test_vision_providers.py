"""Tests for vision providers."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from hwcc.vision.base import HARDWARE_CAPTION_PROMPT, BaseVisionProvider
from hwcc.vision.none import NullVisionProvider


class TestBaseVisionProvider:
    def test_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            BaseVisionProvider()  # type: ignore[abstract]

    def test_hardware_prompt_is_non_empty_string(self) -> None:
        assert isinstance(HARDWARE_CAPTION_PROMPT, str)
        assert len(HARDWARE_CAPTION_PROMPT) > 20
        assert "embedded" in HARDWARE_CAPTION_PROMPT.lower()


class TestNullVisionProvider:
    def test_caption_image_returns_empty_string(self) -> None:
        provider = NullVisionProvider()
        result = provider.caption_image(b"\x89PNG\r\n\x1a\n")
        assert result == ""

    def test_caption_image_with_context_returns_empty_string(self) -> None:
        provider = NullVisionProvider()
        result = provider.caption_image(b"data", context="Figure 8 SPI timing")
        assert result == ""

    def test_is_available_returns_true(self) -> None:
        provider = NullVisionProvider()
        assert provider.is_available() is True

    def test_empty_bytes_returns_empty_string(self) -> None:
        provider = NullVisionProvider()
        assert provider.caption_image(b"") == ""


class TestGetVisionProvider:
    def test_none_provider_returns_null_provider(self) -> None:
        from hwcc.config import VisionConfig
        from hwcc.vision import get_vision_provider

        cfg = VisionConfig(provider="none")
        provider = get_vision_provider(cfg)
        assert isinstance(provider, NullVisionProvider)

    def test_unknown_provider_raises_value_error(self) -> None:
        from hwcc.config import VisionConfig
        from hwcc.vision import get_vision_provider

        cfg = VisionConfig(provider="unknown_provider_xyz")
        with pytest.raises(ValueError, match="unknown_provider_xyz"):
            get_vision_provider(cfg)

    def test_claude_cli_provider_registered(self) -> None:
        from hwcc.config import VisionConfig
        from hwcc.vision import get_vision_provider
        from hwcc.vision.claude_cli import ClaudeCliVisionProvider

        cfg = VisionConfig(provider="claude_cli")
        provider = get_vision_provider(cfg)
        assert isinstance(provider, ClaudeCliVisionProvider)

    def test_ollama_provider_registered(self) -> None:
        from hwcc.config import VisionConfig
        from hwcc.vision import get_vision_provider
        from hwcc.vision.ollama import OllamaVisionProvider

        cfg = VisionConfig(provider="ollama")
        provider = get_vision_provider(cfg)
        assert isinstance(provider, OllamaVisionProvider)

    def test_anthropic_provider_registered(self) -> None:
        from hwcc.config import VisionConfig
        from hwcc.vision import get_vision_provider
        from hwcc.vision.anthropic import AnthropicVisionProvider

        cfg = VisionConfig(provider="anthropic")
        provider = get_vision_provider(cfg)
        assert isinstance(provider, AnthropicVisionProvider)


class TestClaudeCliVisionProvider:
    def test_is_available_false_when_claudecode_env_set(self) -> None:
        from hwcc.vision.claude_cli import ClaudeCliVisionProvider

        provider = ClaudeCliVisionProvider()
        with patch.dict(os.environ, {"CLAUDECODE": "1"}):
            assert provider.is_available() is False

    def test_is_available_true_when_claudecode_env_not_set(self) -> None:
        from hwcc.vision.claude_cli import ClaudeCliVisionProvider

        provider = ClaudeCliVisionProvider()
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("shutil.which", return_value="/usr/bin/claude"),
        ):
            assert provider.is_available() is True

    def test_is_available_false_when_claude_not_in_path(self) -> None:
        from hwcc.vision.claude_cli import ClaudeCliVisionProvider

        provider = ClaudeCliVisionProvider()
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        with patch.dict(os.environ, env, clear=True), patch("shutil.which", return_value=None):
            assert provider.is_available() is False

    def test_caption_image_calls_subprocess(self) -> None:
        from hwcc.vision.claude_cli import ClaudeCliVisionProvider

        provider = ClaudeCliVisionProvider()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "A timing diagram showing CLK, MOSI, MISO signals."
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = provider.caption_image(b"\x89PNG fake image data")

        assert result == "A timing diagram showing CLK, MOSI, MISO signals."
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "claude"
        assert "-p" in call_args
        assert "--allowedTools" in call_args
        assert "Read" in call_args

    def test_caption_image_returns_empty_on_nonzero_exit(self) -> None:
        from hwcc.vision.claude_cli import ClaudeCliVisionProvider

        provider = ClaudeCliVisionProvider()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error"

        with patch("subprocess.run", return_value=mock_result):
            result = provider.caption_image(b"data")

        assert result == ""

    def test_caption_image_returns_empty_on_timeout(self) -> None:
        from hwcc.vision.claude_cli import ClaudeCliVisionProvider

        provider = ClaudeCliVisionProvider()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 60)):
            result = provider.caption_image(b"data")

        assert result == ""

    def test_caption_image_includes_context_in_prompt(self) -> None:
        from hwcc.vision.claude_cli import ClaudeCliVisionProvider

        provider = ClaudeCliVisionProvider()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "SPI timing diagram."

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            provider.caption_image(b"data", context="Figure 8. SPI timing")

        prompt_arg = mock_run.call_args[0][0][2]  # 3rd element is the prompt
        assert "Figure 8. SPI timing" in prompt_arg


class TestOllamaVisionProvider:
    def test_is_available_true_when_ollama_reachable(self) -> None:
        from hwcc.vision.ollama import OllamaVisionProvider

        provider = OllamaVisionProvider(model="llama3.2-vision")
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("urllib.request.urlopen", return_value=mock_response):
            assert provider.is_available() is True

    def test_is_available_false_when_ollama_unreachable(self) -> None:
        from hwcc.vision.ollama import OllamaVisionProvider

        provider = OllamaVisionProvider(model="llama3.2-vision")
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            assert provider.is_available() is False

    def test_caption_image_sends_base64_payload(self) -> None:
        from hwcc.vision.ollama import OllamaVisionProvider

        provider = OllamaVisionProvider(model="llama3.2-vision")
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = (
            b'{"response": "CLK MOSI MISO signals shown."}'
        )

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = provider.caption_image(b"\x89PNG fake")

        assert result == "CLK MOSI MISO signals shown."

    def test_caption_image_returns_empty_on_error(self) -> None:
        from hwcc.vision.ollama import OllamaVisionProvider

        provider = OllamaVisionProvider(model="llama3.2-vision")
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            result = provider.caption_image(b"data")

        assert result == ""


class TestAnthropicVisionProvider:
    def test_is_available_true_when_anthropic_installed(self) -> None:
        from hwcc.vision.anthropic import AnthropicVisionProvider

        provider = AnthropicVisionProvider(model="claude-haiku-4-5-20251001")
        mock_anthropic = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            assert provider.is_available() is True

    def test_is_available_false_when_anthropic_not_installed(self) -> None:
        from hwcc.vision.anthropic import AnthropicVisionProvider

        provider = AnthropicVisionProvider(model="claude-haiku-4-5-20251001")
        with patch.dict("sys.modules", {"anthropic": None}):  # type: ignore[dict-item]
            assert provider.is_available() is False

    def test_is_available_uses_import_not_sys_modules_cache(self) -> None:
        """is_available() must try to import, not just check sys.modules.

        If anthropic is installed but not yet imported, sys.modules won't have
        it — a cache-only check would incorrectly return False.
        """
        from hwcc.vision.anthropic import AnthropicVisionProvider

        provider = AnthropicVisionProvider(model="claude-haiku-4-5-20251001")
        mock_anthropic = MagicMock()
        # Simulate: installed but not yet in sys.modules cache
        import sys as _sys

        env = {k: v for k, v in _sys.modules.items() if k != "anthropic"}

        def _fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "anthropic":
                return mock_anthropic
            return __import__(name, *args, **kwargs)  # type: ignore[arg-type]

        with (
            patch.dict("sys.modules", env, clear=True),
            patch("builtins.__import__", side_effect=_fake_import),
        ):
            assert provider.is_available() is True

    def test_caption_image_calls_messages_api(self) -> None:
        from hwcc.vision.anthropic import AnthropicVisionProvider

        provider = AnthropicVisionProvider(model="claude-haiku-4-5-20251001", api_key="sk-test")
        mock_anthropic_mod = MagicMock()
        mock_anthropic_mod.APIError = Exception  # real exception class for except clause
        mock_client = MagicMock()
        mock_anthropic_mod.Anthropic.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Block diagram with AHB bus.")]
        mock_client.messages.create.return_value = mock_message

        with patch.dict("sys.modules", {"anthropic": mock_anthropic_mod}):
            result = provider.caption_image(b"\x89PNG fake")

        assert result == "Block diagram with AHB bus."
        mock_client.messages.create.assert_called_once()

    def test_caption_image_returns_empty_on_api_error(self) -> None:
        from hwcc.vision.anthropic import AnthropicVisionProvider

        # mock_anthropic_mod.APIError must be a real exception class so that
        # `except anthropic_mod.APIError` in caption_image() is valid Python.
        class FakeAPIError(Exception):
            pass

        provider = AnthropicVisionProvider(model="claude-haiku-4-5-20251001", api_key="sk-test")
        mock_anthropic_mod = MagicMock()
        mock_anthropic_mod.APIError = FakeAPIError
        mock_client = MagicMock()
        mock_anthropic_mod.Anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = FakeAPIError("rate limit exceeded")

        with patch.dict("sys.modules", {"anthropic": mock_anthropic_mod}):
            result = provider.caption_image(b"data")

        assert result == ""

    def test_caption_image_detects_jpeg_media_type(self) -> None:
        from hwcc.vision.anthropic import AnthropicVisionProvider

        provider = AnthropicVisionProvider(model="claude-haiku-4-5-20251001", api_key="sk-test")
        mock_anthropic_mod = MagicMock()
        mock_anthropic_mod.APIError = Exception  # real exception class
        mock_client = MagicMock()
        mock_anthropic_mod.Anthropic.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="JPEG diagram.")]
        mock_client.messages.create.return_value = mock_message

        jpeg_magic = b"\xff\xd8\xff" + b"\x00" * 10

        with patch.dict("sys.modules", {"anthropic": mock_anthropic_mod}):
            result = provider.caption_image(jpeg_magic)

        assert result == "JPEG diagram."
        call_kwargs = mock_client.messages.create.call_args
        content = call_kwargs[1]["messages"][0]["content"]
        image_block = next(b for b in content if b["type"] == "image")
        assert image_block["source"]["media_type"] == "image/jpeg"

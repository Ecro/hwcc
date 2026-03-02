"""Tests for hwcc.bench.providers — LLM provider abstraction."""

from __future__ import annotations

import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from hwcc.bench.providers import (
    ClaudeCodeProvider,
    ProviderResponse,
    create_provider,
)
from hwcc.exceptions import BenchmarkError


class TestClaudeCodeProvider:
    """Tests for ClaudeCodeProvider."""

    def test_construction_default_model(self):
        provider = ClaudeCodeProvider()
        assert provider.name == "claude_code"
        assert provider.model_name == "sonnet"

    def test_construction_custom_model(self):
        provider = ClaudeCodeProvider(model="opus")
        assert provider.model_name == "opus"

    def test_query_success(self):
        json_output = json.dumps([
            {"type": "system", "subtype": "init"},
            {"type": "assistant", "message": {"content": [{"text": "0x40013000"}]}},
            {"type": "result", "subtype": "success", "is_error": False, "result": "0x40013000"},
        ])
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json_output, stderr="",
        )
        provider = ClaudeCodeProvider(model="sonnet")

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            response = provider.query("You are a hardware engineer.", "What is the base address?")

        assert isinstance(response, ProviderResponse)
        assert response.text == "0x40013000"
        assert response.tokens_used == 0
        assert response.latency_ms > 0

        # Verify subprocess was called with correct args
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--system-prompt" in cmd
        assert "--model" in cmd

    def test_query_subprocess_error(self):
        provider = ClaudeCodeProvider()

        with (
            patch("subprocess.run", side_effect=OSError("command not found")),
            pytest.raises(BenchmarkError, match="Claude Code CLI error"),
        ):
            provider.query("system", "question")

    def test_query_nonzero_exit(self):
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Error: something went wrong",
        )
        provider = ClaudeCodeProvider()

        with (
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(BenchmarkError, match="exited with code 1"),
        ):
            provider.query("system", "question")

    def test_query_invalid_json(self):
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not json", stderr="",
        )
        provider = ClaudeCodeProvider()

        with (
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(BenchmarkError, match="Failed to parse"),
        ):
            provider.query("system", "question")

    def test_query_timeout(self):
        provider = ClaudeCodeProvider()
        timeout_err = subprocess.TimeoutExpired(cmd="claude", timeout=120)

        with (
            patch("subprocess.run", side_effect=timeout_err),
            pytest.raises(BenchmarkError, match="timed out"),
        ):
            provider.query("system", "question")

    def test_query_missing_result_entry(self):
        """If JSON array has no 'result' type entry, text is empty string."""
        json_output = json.dumps([
            {"type": "system", "subtype": "init"},
        ])
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json_output, stderr="",
        )
        provider = ClaudeCodeProvider()

        with patch("subprocess.run", return_value=mock_result):
            response = provider.query("system", "question")

        assert response.text == ""

    def test_query_is_error_flag(self):
        """If response has is_error=True, raise BenchmarkError."""
        json_output = json.dumps([
            {"type": "result", "is_error": True, "result": "error message"},
        ])
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json_output, stderr="",
        )
        provider = ClaudeCodeProvider()

        with (
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(BenchmarkError, match="returned an error"),
        ):
            provider.query("system", "question")


class TestCreateProviderClaudeCode:
    """Tests for create_provider() with claude_code."""

    def test_create_claude_code_default(self):
        provider = create_provider("claude_code")
        assert isinstance(provider, ClaudeCodeProvider)
        assert provider.model_name == "sonnet"

    def test_create_claude_code_custom_model(self):
        provider = create_provider("claude_code", model="opus")
        assert isinstance(provider, ClaudeCodeProvider)
        assert provider.model_name == "opus"

    def test_unknown_provider_raises(self):
        with pytest.raises(BenchmarkError, match="Unknown provider"):
            create_provider("nonexistent")


class TestAnthropicProvider:
    """Tests for AnthropicProvider with mocked anthropic SDK."""

    def _make_mock_anthropic(self) -> MagicMock:
        """Create a mock anthropic module with realistic response structure."""
        mock_mod = MagicMock()
        mock_client = MagicMock()
        mock_mod.Anthropic.return_value = mock_client

        # Build response object
        mock_content = MagicMock()
        mock_content.text = "0x40013000"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 50
        mock_usage.output_tokens = 10
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_response.usage = mock_usage
        mock_client.messages.create.return_value = mock_response

        return mock_mod

    def test_query_success(self):
        mock_anthropic = self._make_mock_anthropic()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            from hwcc.bench.providers import AnthropicProvider

            provider = AnthropicProvider(model="claude-sonnet-4-6")
            response = provider.query("system prompt", "What is the base address?")

        assert isinstance(response, ProviderResponse)
        assert response.text == "0x40013000"
        assert response.tokens_used == 60
        assert response.latency_ms > 0

    def test_query_api_error(self):
        mock_anthropic = self._make_mock_anthropic()
        mock_anthropic.Anthropic().messages.create.side_effect = RuntimeError("API rate limit")

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            from hwcc.bench.providers import AnthropicProvider

            provider = AnthropicProvider(model="claude-sonnet-4-6")
            with pytest.raises(BenchmarkError, match="Anthropic API error"):
                provider.query("system", "question")

    def test_import_error(self):
        """If anthropic package is missing, raise BenchmarkError."""
        with patch.dict(sys.modules, {"anthropic": None}):
            from hwcc.bench.providers import AnthropicProvider

            with pytest.raises(BenchmarkError, match="anthropic package required"):
                AnthropicProvider()

    def test_name_and_model(self):
        mock_anthropic = self._make_mock_anthropic()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            from hwcc.bench.providers import AnthropicProvider

            provider = AnthropicProvider(model="claude-sonnet-4-6")
            assert provider.name == "anthropic"
            assert provider.model_name == "claude-sonnet-4-6"


class TestOpenAIProvider:
    """Tests for OpenAIProvider with mocked openai SDK."""

    def _make_mock_openai(self) -> MagicMock:
        """Create a mock openai module with realistic response structure."""
        mock_mod = MagicMock()
        mock_client = MagicMock()
        mock_mod.OpenAI.return_value = mock_client

        # Build response object
        mock_message = MagicMock()
        mock_message.content = "0x40013000"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 40
        mock_usage.completion_tokens = 8
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        mock_client.chat.completions.create.return_value = mock_response

        return mock_mod

    def test_query_success(self):
        mock_openai = self._make_mock_openai()
        with patch.dict(sys.modules, {"openai": mock_openai}):
            from hwcc.bench.providers import OpenAIProvider

            provider = OpenAIProvider(model="gpt-4o")
            response = provider.query("system prompt", "What is the base address?")

        assert isinstance(response, ProviderResponse)
        assert response.text == "0x40013000"
        assert response.tokens_used == 48
        assert response.latency_ms > 0

    def test_query_api_error(self):
        mock_openai = self._make_mock_openai()
        mock_openai.OpenAI().chat.completions.create.side_effect = RuntimeError("Rate limit")

        with patch.dict(sys.modules, {"openai": mock_openai}):
            from hwcc.bench.providers import OpenAIProvider

            provider = OpenAIProvider(model="gpt-4o")
            with pytest.raises(BenchmarkError, match="OpenAI API error"):
                provider.query("system", "question")

    def test_import_error(self):
        with patch.dict(sys.modules, {"openai": None}):
            from hwcc.bench.providers import OpenAIProvider

            with pytest.raises(BenchmarkError, match="openai package required"):
                OpenAIProvider()

    def test_name_and_model(self):
        mock_openai = self._make_mock_openai()
        with patch.dict(sys.modules, {"openai": mock_openai}):
            from hwcc.bench.providers import OpenAIProvider

            provider = OpenAIProvider(model="gpt-4o")
            assert provider.name == "openai"
            assert provider.model_name == "gpt-4o"


class TestOllamaProvider:
    """Tests for OllamaProvider with mocked httpx."""

    def test_query_success(self):
        from hwcc.bench.providers import OllamaProvider

        provider = OllamaProvider(model="llama3.1", host="http://localhost:11434")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "0x40013000"},
            "eval_count": 15,
            "prompt_eval_count": 30,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response):
            response = provider.query("system prompt", "What is the base address?")

        assert isinstance(response, ProviderResponse)
        assert response.text == "0x40013000"
        assert response.tokens_used == 45
        assert response.latency_ms > 0

    def test_query_timeout(self):
        from hwcc.bench.providers import OllamaProvider

        provider = OllamaProvider(model="llama3.1")

        with (
            patch("httpx.post", side_effect=RuntimeError("Connection timed out")),
            pytest.raises(BenchmarkError, match="Ollama API error"),
        ):
            provider.query("system", "question")

    def test_import_error(self):
        from hwcc.bench.providers import OllamaProvider

        provider = OllamaProvider(model="llama3.1")

        with (
            patch.dict(sys.modules, {"httpx": None}),
            pytest.raises(BenchmarkError, match="httpx package required"),
        ):
            provider.query("system", "question")

    def test_name_and_model(self):
        from hwcc.bench.providers import OllamaProvider

        provider = OllamaProvider(model="llama3.1")
        assert provider.name == "ollama"
        assert provider.model_name == "llama3.1"


class TestCreateProviderAllTypes:
    """Tests for create_provider() factory with all supported providers."""

    def test_create_anthropic(self):
        mock_anthropic = MagicMock()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            provider = create_provider("anthropic", model="claude-sonnet-4-6")
            assert provider.name == "anthropic"
            assert provider.model_name == "claude-sonnet-4-6"

    def test_create_openai(self):
        mock_openai = MagicMock()
        with patch.dict(sys.modules, {"openai": mock_openai}):
            provider = create_provider("openai", model="gpt-4o")
            assert provider.name == "openai"
            assert provider.model_name == "gpt-4o"

    def test_create_ollama(self):
        provider = create_provider("ollama", model="llama3.1")
        assert provider.name == "ollama"
        assert provider.model_name == "llama3.1"

    def test_create_claude_code(self):
        provider = create_provider("claude_code", model="sonnet")
        assert provider.name == "claude_code"
        assert provider.model_name == "sonnet"

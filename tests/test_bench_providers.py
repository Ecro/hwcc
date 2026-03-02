"""Tests for hwcc.bench.providers — LLM provider abstraction."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

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

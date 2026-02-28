"""Tests for hwcc.config module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hwcc.config import (
    HwccConfig,
    default_config,
    load_config,
    save_config,
)
from hwcc.exceptions import ConfigError

if TYPE_CHECKING:
    from pathlib import Path


class TestDefaultConfig:
    def test_default_has_all_sections(self):
        config = default_config()
        assert config.project is not None
        assert config.hardware is not None
        assert config.software is not None
        assert config.conventions is not None
        assert config.embedding is not None
        assert config.llm is not None
        assert config.output is not None

    def test_default_embedding_model(self):
        config = default_config()
        assert config.embedding.model == "nomic-embed-text"
        assert config.embedding.provider == "ollama"

    def test_default_output_targets(self):
        config = default_config()
        assert "claude" in config.output.targets
        assert config.output.hot_context_max_lines == 120

    def test_default_software_language(self):
        config = default_config()
        assert config.software.language == "C"


class TestConfigRoundTrip:
    def test_save_and_load_defaults(self, tmp_path: Path):
        path = tmp_path / "config.toml"
        original = default_config()
        save_config(original, path)
        loaded = load_config(path)

        assert loaded.embedding.model == original.embedding.model
        assert loaded.embedding.provider == original.embedding.provider
        assert loaded.output.targets == original.output.targets
        assert loaded.output.hot_context_max_lines == original.output.hot_context_max_lines

    def test_save_and_load_with_values(self, tmp_path: Path):
        path = tmp_path / "config.toml"
        config = HwccConfig()
        config.project.name = "motor-ctrl"
        config.hardware.mcu = "STM32F407VGT6"
        config.hardware.clock_mhz = 168
        config.software.rtos = "FreeRTOS 10.5.1"

        save_config(config, path)
        loaded = load_config(path)

        assert loaded.project.name == "motor-ctrl"
        assert loaded.hardware.mcu == "STM32F407VGT6"
        assert loaded.hardware.clock_mhz == 168
        assert loaded.software.rtos == "FreeRTOS 10.5.1"

    def test_load_partial_toml_gets_defaults(self, tmp_path: Path):
        """A TOML with only [project] should get defaults for other sections."""
        path = tmp_path / "config.toml"
        path.write_text('[project]\nname = "partial"\n', encoding="utf-8")

        loaded = load_config(path)
        assert loaded.project.name == "partial"
        assert loaded.embedding.model == "nomic-embed-text"
        assert loaded.output.hot_context_max_lines == 120

    def test_zero_and_empty_string_survive_roundtrip(self, tmp_path: Path):
        """Regression test for C2: zero/empty values must not be silently dropped."""
        path = tmp_path / "config.toml"
        config = HwccConfig()
        config.hardware.mcu = "STM32F407"
        config.hardware.clock_mhz = 0  # Explicitly zero
        config.software.language = ""  # Explicitly empty

        save_config(config, path)
        loaded = load_config(path)

        assert loaded.hardware.clock_mhz == 0
        assert loaded.software.language == ""
        assert loaded.hardware.mcu == "STM32F407"

    def test_save_and_load_custom_targets(self, tmp_path: Path):
        path = tmp_path / "config.toml"
        config = HwccConfig()
        config.output.targets = ["claude", "gemini"]
        save_config(config, path)
        loaded = load_config(path)
        assert loaded.output.targets == ["claude", "gemini"]

    def test_creates_parent_directories(self, tmp_path: Path):
        path = tmp_path / "deep" / "nested" / "config.toml"
        save_config(default_config(), path)
        assert path.exists()

    def test_embedding_config_roundtrip(self, tmp_path: Path):
        """EmbeddingConfig fields including base_url and batch_size survive round-trip."""
        path = tmp_path / "config.toml"
        config = HwccConfig()
        config.embedding.model = "mxbai-embed-large"
        config.embedding.provider = "openai"
        config.embedding.base_url = "http://localhost:8080/v1"
        config.embedding.batch_size = 32
        config.embedding.api_key_env = "OPENAI_API_KEY"
        save_config(config, path)
        loaded = load_config(path)
        assert loaded.embedding.model == "mxbai-embed-large"
        assert loaded.embedding.provider == "openai"
        assert loaded.embedding.base_url == "http://localhost:8080/v1"
        assert loaded.embedding.batch_size == 32
        assert loaded.embedding.api_key_env == "OPENAI_API_KEY"

    def test_default_embedding_config_new_fields(self):
        """New EmbeddingConfig fields have correct defaults."""
        config = default_config()
        assert config.embedding.base_url == ""
        assert config.embedding.batch_size == 64

    def test_chunk_config_roundtrip(self, tmp_path: Path):
        """ChunkConfig values should survive save/load round-trip."""
        path = tmp_path / "config.toml"
        config = HwccConfig()
        config.chunk.max_tokens = 1024
        config.chunk.overlap_tokens = 100
        config.chunk.min_tokens = 75
        save_config(config, path)
        loaded = load_config(path)
        assert loaded.chunk.max_tokens == 1024
        assert loaded.chunk.overlap_tokens == 100
        assert loaded.chunk.min_tokens == 75


class TestConfigErrors:
    def test_load_nonexistent_raises_config_error(self, tmp_path: Path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nonexistent.toml")

    def test_load_invalid_toml_raises_config_error(self, tmp_path: Path):
        path = tmp_path / "bad.toml"
        path.write_text("this is [not valid toml", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(path)

"""Tests for IngestConfig and VisionConfig sections."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from hwcc.config import (
    IngestConfig,
    VisionConfig,
    default_config,
    load_config,
    save_config,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestIngestConfig:
    def test_default_pdf_backend_is_pymupdf(self) -> None:
        cfg = IngestConfig()
        assert cfg.pdf_backend == "pymupdf"

    def test_hwcc_config_has_ingest_field(self) -> None:
        cfg = default_config()
        assert hasattr(cfg, "ingest")
        assert isinstance(cfg.ingest, IngestConfig)

    def test_ingest_default_preserved_in_hwcc_config(self) -> None:
        cfg = default_config()
        assert cfg.ingest.pdf_backend == "pymupdf"


class TestVisionConfig:
    def test_default_provider_is_none(self) -> None:
        cfg = VisionConfig()
        assert cfg.provider == "none"

    def test_default_model_is_empty(self) -> None:
        cfg = VisionConfig()
        assert cfg.model == ""

    def test_default_api_key_env_is_empty(self) -> None:
        cfg = VisionConfig()
        assert cfg.api_key_env == ""

    def test_hwcc_config_has_vision_field(self) -> None:
        cfg = default_config()
        assert hasattr(cfg, "vision")
        assert isinstance(cfg.vision, VisionConfig)

    def test_vision_default_preserved_in_hwcc_config(self) -> None:
        cfg = default_config()
        assert cfg.vision.provider == "none"


class TestConfigRoundTrip:
    def test_ingest_section_saves_and_loads(self, tmp_path: Path) -> None:
        cfg = default_config()
        cfg.ingest.pdf_backend = "docling"
        config_path = tmp_path / "config.toml"
        save_config(cfg, config_path)
        loaded = load_config(config_path)
        assert loaded.ingest.pdf_backend == "docling"

    def test_vision_section_saves_and_loads(self, tmp_path: Path) -> None:
        cfg = default_config()
        cfg.vision.provider = "claude_cli"
        cfg.vision.model = "llama3.2-vision"
        cfg.vision.api_key_env = "MY_API_KEY"
        config_path = tmp_path / "config.toml"
        save_config(cfg, config_path)
        loaded = load_config(config_path)
        assert loaded.vision.provider == "claude_cli"
        assert loaded.vision.model == "llama3.2-vision"
        assert loaded.vision.api_key_env == "MY_API_KEY"

    def test_missing_ingest_section_uses_defaults(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("[project]\nname = 'test'\n", encoding="utf-8")
        loaded = load_config(config_path)
        assert loaded.ingest.pdf_backend == "pymupdf"

    def test_missing_vision_section_uses_defaults(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("[project]\nname = 'test'\n", encoding="utf-8")
        loaded = load_config(config_path)
        assert loaded.vision.provider == "none"

    def test_unknown_ingest_keys_ignored(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            textwrap.dedent("""\
                [ingest]
                pdf_backend = "docling"
                unknown_key = "ignored"
            """),
            encoding="utf-8",
        )
        loaded = load_config(config_path)
        assert loaded.ingest.pdf_backend == "docling"

    def test_full_round_trip_preserves_other_sections(self, tmp_path: Path) -> None:
        cfg = default_config()
        cfg.hardware.mcu = "STM32F407"
        cfg.ingest.pdf_backend = "docling"
        cfg.vision.provider = "ollama"
        config_path = tmp_path / "config.toml"
        save_config(cfg, config_path)
        loaded = load_config(config_path)
        assert loaded.hardware.mcu == "STM32F407"
        assert loaded.ingest.pdf_backend == "docling"
        assert loaded.vision.provider == "ollama"

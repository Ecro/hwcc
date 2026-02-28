"""Configuration system for hwcc.

Manages project configuration via .rag/config.toml with typed dataclasses
and sensible defaults for all values.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeVar

import tomli_w

if sys.version_info >= (3, 12):
    import tomllib
else:
    import tomli as tomllib

from hwcc.exceptions import ConfigError

if TYPE_CHECKING:
    from pathlib import Path

_T = TypeVar("_T")

__all__ = [
    "ChunkConfig",
    "ConventionsConfig",
    "EmbeddingConfig",
    "HardwareConfig",
    "HwccConfig",
    "LlmConfig",
    "OutputConfig",
    "ProjectConfig",
    "SoftwareConfig",
    "default_config",
    "load_config",
    "save_config",
]

logger = logging.getLogger(__name__)


@dataclass
class ProjectConfig:
    """[project] section."""

    name: str = ""
    description: str = ""


@dataclass
class HardwareConfig:
    """[hardware] section."""

    mcu: str = ""
    mcu_family: str = ""
    architecture: str = ""
    clock_mhz: int = 0
    flash_kb: int = 0
    ram_kb: int = 0


@dataclass
class SoftwareConfig:
    """[software] section."""

    rtos: str = ""
    hal: str = ""
    language: str = "C"
    build_system: str = ""


@dataclass
class ConventionsConfig:
    """[conventions] section."""

    register_access: str = ""
    error_handling: str = ""
    naming: str = ""


@dataclass
class ChunkConfig:
    """[chunk] section."""

    max_tokens: int = 512
    overlap_tokens: int = 50
    min_tokens: int = 50


@dataclass
class EmbeddingConfig:
    """[embedding] section."""

    model: str = "nomic-embed-text"
    provider: str = "ollama"
    api_key_env: str = ""


@dataclass
class LlmConfig:
    """[llm] section."""

    provider: str = "ollama"
    model: str = "llama3.2"
    api_key_env: str = ""


@dataclass
class OutputConfig:
    """[output] section."""

    targets: list[str] = field(default_factory=lambda: ["claude", "codex", "cursor", "gemini"])
    hot_context_max_lines: int = 120


@dataclass
class HwccConfig:
    """Root configuration combining all sections."""

    project: ProjectConfig = field(default_factory=ProjectConfig)
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    software: SoftwareConfig = field(default_factory=SoftwareConfig)
    conventions: ConventionsConfig = field(default_factory=ConventionsConfig)
    chunk: ChunkConfig = field(default_factory=ChunkConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


def default_config() -> HwccConfig:
    """Return a config with all default values."""
    return HwccConfig()


def _section_to_dict(obj: object) -> dict[str, object]:
    """Convert a dataclass instance to a dict for TOML serialization."""
    return dict(vars(obj))


def _config_to_dict(config: HwccConfig) -> dict[str, object]:
    """Convert HwccConfig to a nested dict suitable for TOML serialization."""
    result: dict[str, object] = {}
    for section_name in (
        "project",
        "hardware",
        "software",
        "conventions",
        "chunk",
        "embedding",
        "llm",
        "output",
    ):
        section = getattr(config, section_name)
        result[section_name] = _section_to_dict(section)
    return result


def save_config(config: HwccConfig, path: Path) -> None:
    """Save configuration to a TOML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _config_to_dict(config)
    try:
        with path.open("wb") as f:
            tomli_w.dump(data, f)
        logger.info("Saved config to %s", path)
    except OSError as e:
        logger.error("Failed to save config to %s: %s", path, e)
        raise ConfigError(f"Failed to save config to {path}: {e}") from e


def _load_section(cls: type[_T], data: dict[str, object]) -> _T:
    """Load a dataclass section from a dict, ignoring unknown keys."""
    known_fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    filtered = {k: v for k, v in data.items() if k in known_fields}
    return cls(**filtered)


def load_config(path: Path) -> HwccConfig:
    """Load configuration from a TOML file.

    Missing sections or keys get default values.
    """
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        raw = path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.error("Failed to load config from %s: %s", path, e)
        raise ConfigError(f"Failed to load config from {path}: {e}") from e

    config = HwccConfig()
    section_map: dict[str, type] = {
        "project": ProjectConfig,
        "hardware": HardwareConfig,
        "software": SoftwareConfig,
        "conventions": ConventionsConfig,
        "chunk": ChunkConfig,
        "embedding": EmbeddingConfig,
        "llm": LlmConfig,
        "output": OutputConfig,
    }

    for name, cls in section_map.items():
        if name in data:
            setattr(config, name, _load_section(cls, data[name]))

    logger.info("Loaded config from %s", path)
    return config

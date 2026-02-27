"""Custom exception hierarchy for hwcc."""

__all__ = [
    "ChunkError",
    "CompileError",
    "ConfigError",
    "EmbeddingError",
    "HwccError",
    "ManifestError",
    "ParseError",
    "PipelineError",
    "PluginError",
    "ProjectError",
    "StoreError",
]


class HwccError(Exception):
    """Base exception for all hwcc errors."""


class ConfigError(HwccError):
    """Raised when configuration loading or validation fails."""


class ManifestError(HwccError):
    """Raised when manifest operations fail."""


class ProjectError(HwccError):
    """Raised when project initialization or discovery fails."""


class ParseError(HwccError):
    """Raised when document parsing fails."""


class ChunkError(HwccError):
    """Raised when chunking operations fail."""


class EmbeddingError(HwccError):
    """Raised when embedding generation fails."""


class StoreError(HwccError):
    """Raised when vector store operations fail."""


class CompileError(HwccError):
    """Raised when context compilation fails."""


class PipelineError(HwccError):
    """Raised when pipeline orchestration fails."""


class PluginError(HwccError):
    """Raised when plugin loading or registration fails."""

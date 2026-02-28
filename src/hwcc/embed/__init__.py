"""Embedding engine — abstract provider interface and concrete providers."""

from hwcc.embed.base import BaseEmbedder
from hwcc.embed.ollama import OllamaEmbedder
from hwcc.embed.openai_compat import OpenAICompatEmbedder
from hwcc.registry import default_registry

__all__ = ["BaseEmbedder", "OllamaEmbedder", "OpenAICompatEmbedder"]

# Register built-in embedding providers
default_registry.register("embedding", "ollama", lambda cfg: OllamaEmbedder(cfg))
default_registry.register("embedding", "openai", lambda cfg: OpenAICompatEmbedder(cfg))

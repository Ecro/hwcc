"""Tests for hwcc.registry module — provider registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hwcc.exceptions import PluginError
from hwcc.registry import ProviderRegistry

if TYPE_CHECKING:
    from hwcc.config import HwccConfig


class TestProviderRegistry:
    def test_register_and_create(self):
        registry = ProviderRegistry()
        registry.register("embedding", "mock", lambda cfg: "mock_embedder")
        result = registry.create("embedding", "mock", _mock_config())
        assert result == "mock_embedder"

    def test_create_unknown_category_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(PluginError, match="Unknown provider category"):
            registry.create("nonexistent", "mock", _mock_config())

    def test_create_unknown_name_raises(self):
        registry = ProviderRegistry()
        registry.register("embedding", "ollama", lambda cfg: "ollama_embedder")
        with pytest.raises(PluginError, match="Unknown provider 'openai'"):
            registry.create("embedding", "openai", _mock_config())

    def test_duplicate_register_raises(self):
        registry = ProviderRegistry()
        registry.register("embedding", "ollama", lambda cfg: "first")
        with pytest.raises(PluginError, match="already registered"):
            registry.register("embedding", "ollama", lambda cfg: "second")

    def test_list_providers_empty_category(self):
        registry = ProviderRegistry()
        assert registry.list_providers("nonexistent") == []

    def test_list_providers_returns_sorted(self):
        registry = ProviderRegistry()
        registry.register("embedding", "openai", lambda cfg: "openai")
        registry.register("embedding", "ollama", lambda cfg: "ollama")
        registry.register("embedding", "azure", lambda cfg: "azure")
        assert registry.list_providers("embedding") == ["azure", "ollama", "openai"]

    def test_has_provider_true(self):
        registry = ProviderRegistry()
        registry.register("parser", "svd", lambda cfg: "svd_parser")
        assert registry.has_provider("parser", "svd") is True

    def test_has_provider_false_name(self):
        registry = ProviderRegistry()
        registry.register("parser", "svd", lambda cfg: "svd_parser")
        assert registry.has_provider("parser", "pdf") is False

    def test_has_provider_false_category(self):
        registry = ProviderRegistry()
        assert registry.has_provider("nonexistent", "anything") is False

    def test_factory_receives_config(self):
        registry = ProviderRegistry()
        received_configs: list[HwccConfig] = []

        def factory(cfg: HwccConfig) -> str:
            received_configs.append(cfg)
            return "created"

        registry.register("store", "chroma", factory)
        config = _mock_config()
        registry.create("store", "chroma", config)

        assert len(received_configs) == 1
        assert received_configs[0] is config

    def test_multiple_categories(self):
        registry = ProviderRegistry()
        registry.register("parser", "svd", lambda cfg: "svd")
        registry.register("embedding", "ollama", lambda cfg: "ollama")
        registry.register("store", "chroma", lambda cfg: "chroma")

        assert registry.has_provider("parser", "svd")
        assert registry.has_provider("embedding", "ollama")
        assert registry.has_provider("store", "chroma")
        assert not registry.has_provider("parser", "ollama")


class TestLazyAutoDiscovery:
    """Registry auto-discovers built-in providers on first create() call."""

    def test_default_registry_has_embedding_providers(self):
        """default_registry should auto-discover embedding providers."""
        from hwcc.registry import default_registry

        # After auto-discovery, embedding providers should be available
        assert default_registry.has_provider("embedding", "chromadb")
        assert default_registry.has_provider("embedding", "ollama")
        assert default_registry.has_provider("embedding", "openai")

    def test_create_triggers_auto_discovery(self):
        """default_registry.create() should work without explicit import."""
        from hwcc.registry import default_registry

        config = _mock_config()
        # create() triggers _ensure_discovered(), which imports hwcc.embed
        result = default_registry.create("embedding", "chromadb", config)
        assert result is not None

    def test_auto_discover_false_does_not_import(self):
        """Registry with auto_discover=False should NOT auto-import."""
        registry = ProviderRegistry(auto_discover=False)
        with pytest.raises(PluginError, match="Unknown provider category"):
            registry.create("embedding", "chromadb", _mock_config())


def _mock_config() -> HwccConfig:
    from hwcc.config import HwccConfig

    return HwccConfig()

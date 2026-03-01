"""Provider registry for hwcc.

Maps config strings to factory functions that create provider instances.
Example: ``registry.create("embedding", "ollama", config)`` → ``OllamaEmbedder``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from hwcc.exceptions import PluginError

if TYPE_CHECKING:
    from collections.abc import Callable

    from hwcc.config import HwccConfig

__all__ = ["ProviderRegistry", "default_registry"]

logger = logging.getLogger(__name__)

ProviderFactory = Any  # Callable[[HwccConfig], Any] — relaxed for registration flexibility


class ProviderRegistry:
    """Config-driven factory that maps (category, name) → provider instance.

    Categories correspond to pipeline stages: ``"parser"``, ``"chunker"``,
    ``"embedding"``, ``"store"``, ``"compiler"``.

    When ``auto_discover`` is ``True``, the first call to :meth:`create`
    triggers a lazy import of ``hwcc.embed`` so that built-in embedding
    providers are registered without requiring an explicit import.

    Usage::

        registry = ProviderRegistry()
        registry.register("embedding", "ollama", lambda cfg: OllamaEmbedder(cfg))
        embedder = registry.create("embedding", "ollama", config)
    """

    def __init__(self, *, auto_discover: bool = False) -> None:
        self._factories: dict[str, dict[str, Callable[..., Any]]] = {}
        self._auto_discover = auto_discover
        self._discovered = False

    def register(
        self,
        category: str,
        name: str,
        factory: Callable[..., Any],
    ) -> None:
        """Register a provider factory.

        Args:
            category: Pipeline stage (e.g. "embedding", "parser").
            name: Provider name (e.g. "ollama", "openai").
            factory: Callable that accepts ``HwccConfig`` and returns a provider.

        Raises:
            PluginError: If a provider with the same category+name already exists.
        """
        if category not in self._factories:
            self._factories[category] = {}

        if name in self._factories[category]:
            raise PluginError(f"Provider '{name}' already registered in category '{category}'")

        self._factories[category][name] = factory
        logger.debug("Registered provider %s/%s", category, name)

    def _ensure_discovered(self) -> None:
        """Lazily import built-in provider modules on first use."""
        if self._discovered or not self._auto_discover:
            return
        self._discovered = True
        try:
            import hwcc.embed  # noqa: F401 — triggers provider registration
        except ImportError:
            logger.warning("hwcc.embed not available for auto-discovery")

    def create(self, category: str, name: str, config: HwccConfig) -> Any:
        """Create a provider instance from the registry.

        Args:
            category: Pipeline stage.
            name: Provider name.
            config: Project configuration passed to the factory.

        Returns:
            Provider instance.

        Raises:
            PluginError: If the category or name is not registered.
        """
        self._ensure_discovered()

        if category not in self._factories:
            raise PluginError(
                f"Unknown provider category '{category}'. Available: {sorted(self._factories)}"
            )

        if name not in self._factories[category]:
            raise PluginError(
                f"Unknown provider '{name}' in category '{category}'. "
                f"Available: {sorted(self._factories[category])}"
            )

        factory = self._factories[category][name]
        logger.info("Creating provider %s/%s", category, name)
        return factory(config)

    def list_providers(self, category: str) -> list[str]:
        """List registered provider names for a category."""
        self._ensure_discovered()
        if category not in self._factories:
            return []
        return sorted(self._factories[category])

    def has_provider(self, category: str, name: str) -> bool:
        """Check whether a provider is registered."""
        self._ensure_discovered()
        return category in self._factories and name in self._factories[category]


default_registry = ProviderRegistry(auto_discover=True)

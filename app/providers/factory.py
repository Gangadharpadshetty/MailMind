"""
LLM Provider Factory — Factory Pattern + Open/Closed Principle.

The registry maps string IDs → provider constructors.
To add a new provider: register it here. Existing code is untouched (OCP).

Usage:
    factory = LLMProviderFactory(settings)
    provider = factory.create("groq")
    providers = factory.list_available()
"""
from __future__ import annotations
from typing import Callable

from app.core.config import Settings
from app.core.exceptions import ProviderNotFoundError
from app.domain.interfaces import IGenerator
from app.domain.models import LLMProviderInfo


class LLMProviderFactory:
    """
    Factory that instantiates IGenerator implementations by ID.
    Internal registry uses a dict; new entries never modify existing code.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # Registry: provider_id → zero-arg factory lambda
        self._registry: dict[str, Callable[[], IGenerator]] = {}
        self._register_defaults()

    # ── Registration (open for extension) ───────────────────────────────────

    def register(self, provider_id: str, factory_fn: Callable[[], IGenerator]) -> None:
        """Register a new provider. Called at startup or by plugins."""
        self._registry[provider_id] = factory_fn

    def _register_defaults(self) -> None:
        """Register built-in providers at construction time."""
        cfg = self._settings

        # ── Groq ───────────────────────────────────────────────────
        if cfg.groq_api_key:
            from app.providers.groq_provider import GroqProvider

            self.register(
                "groq",
                lambda: GroqProvider(
                    api_key=cfg.groq_api_key,
                    model=cfg.groq_model,
                ),
            )
    # ── Factory method ───────────────────────────────────────────────────────

    def create(self, provider_id: str) -> IGenerator:
        factory_fn = self._registry.get(provider_id)
        if factory_fn is None:
            raise ProviderNotFoundError(provider_id)
        return factory_fn()

    # ── Discovery ────────────────────────────────────────────────────────────

    def list_available(self) -> list[LLMProviderInfo]:
        """Return info for all registered providers (for UI dropdown)."""
        infos: list[LLMProviderInfo] = []
        for pid, fn in self._registry.items():
            try:
                provider = fn()
                infos.append(provider.provider_info)
            except Exception:
                # Key not set — skip gracefully
                pass
        return infos

    def default_provider_id(self) -> str:
        cfg = self._settings
        if cfg.default_provider in self._registry:
            return cfg.default_provider
        # Fall back to first available
        if self._registry:
            return next(iter(self._registry))
        # No providers configured — return empty string so the app can start
        # and the UI can show a clear "LLM not configured" message instead of
        # failing at startup. Chat routes will handle this gracefully.
        return ""

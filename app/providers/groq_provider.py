"""
Groq LLM Provider — concrete Strategy for Groq.
Uses the official `groq` Python SDK (OpenAI-compatible interface).
Only _call_llm() differs from other providers (LSP-safe).
"""
from groq import Groq

from app.domain.models import LLMProviderInfo
from .base import BaseLLMProvider


class GroqProvider(BaseLLMProvider):
    """Groq Cloud via official groq SDK. Fast inference, free tier available."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set.")
        self._client = Groq(api_key=api_key)
        self._model = model

    def _call_llm(self, prompt: str) -> tuple[str, int]:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.2,
        )
        text = response.choices[0].message.content.strip()
        try:
            tokens = response.usage.total_tokens
        except Exception:
            tokens = 0
        return text, tokens

    @property
    def provider_info(self) -> LLMProviderInfo:
        return LLMProviderInfo(
            id="groq",
            name=f"Groq ({self._model})",
            description="Groq Cloud — ultra-fast LLM inference. Free tier available.",
            is_free=True,
        )

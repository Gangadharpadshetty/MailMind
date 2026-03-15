"""
Gemini LLM Provider — concrete Strategy for Google Gemini.
Only _call_llm() differs from other providers (LSP-safe).
"""
import google.generativeai as genai

from app.domain.models import LLMProviderInfo
from .base import BaseLLMProvider


class GeminiProvider(BaseLLMProvider):
    """Google Gemini via google-generativeai SDK."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._model_name = model

    def _call_llm(self, prompt: str) -> tuple[str, int]:
        response = self._model.generate_content(prompt)
        text = response.text.strip()
        try:
            tokens = response.usage_metadata.total_token_count
        except Exception:
            tokens = 0
        return text, tokens

    @property
    def provider_info(self) -> LLMProviderInfo:
        # Keep a simple, stable ID so the UI dropdown and backend agree.
        return LLMProviderInfo(
            id="gemini",
            name=f"Gemini ({self._model_name})",
            description="Google Gemini via official SDK. Free tier available.",
            is_free=True,
        )

"""
OpenRouter LLM Provider — concrete Strategy for OpenRouter.
Supports dozens of free models (Mistral, LLaMA, Gemma, DeepSeek, etc.)
Adding a new OpenRouter model never requires code changes (OCP).
"""
import httpx

from app.domain.models import LLMProviderInfo
from .base import BaseLLMProvider

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(BaseLLMProvider):
    """
    OpenRouter via OpenAI-compatible REST API.
    model_id: e.g. "mistralai/mistral-7b-instruct:free"
    """

    def __init__(self, api_key: str, model_id: str):
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")
        self._api_key = api_key
        self._model_id = model_id

    def _call_llm(self, prompt: str) -> tuple[str, int]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://mailmind.app",
            "X-Title": "MailMind",
        }
        payload = {
            "model": self._model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "temperature": 0.2,
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(OPENROUTER_URL, headers=headers, json=payload)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Surface OpenRouter's error body so the UI can show a clear
                # message instead of a generic "client error".
                detail = ""
                try:
                    detail = resp.text
                except Exception:
                    pass
                raise RuntimeError(
                    f"OpenRouter API error {resp.status_code}: {detail or exc}"
                ) from exc
            data = resp.json()

        text = data["choices"][0]["message"]["content"].strip()
        tokens = data.get("usage", {}).get("total_tokens", 0)
        return text, tokens

    @property
    def provider_info(self) -> LLMProviderInfo:
        is_free = ":free" in self._model_id
        short_name = self._model_id.split("/")[-1]
        return LLMProviderInfo(
            id=f"openrouter/{self._model_id}",
            name=f"OpenRouter – {short_name}",
            description=f"OpenRouter ({self._model_id}). {'Free tier.' if is_free else 'Paid.'}",
            is_free=is_free,
        )

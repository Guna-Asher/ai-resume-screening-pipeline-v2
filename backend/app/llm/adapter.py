"""Provider boundary. The rest of the app only sees ``LLMAdapter``.

``OpenAICompatibleAdapter`` covers OpenRouter, OpenAI and any endpoint that
speaks the OpenAI chat-completions protocol. To add a provider with a
different protocol (e.g. native Anthropic), implement ``LLMAdapter`` and
register it in ``build_adapter``; nothing in screening/scoring changes.
"""

from typing import Protocol

import httpx

from app.config import Settings
from app.llm.errors import LLMError, LLMFailure


class LLMAdapter(Protocol):
    provider: str
    model: str

    async def complete(self, *, system: str, user: str) -> str:
        """Return the model's raw text reply. Raise ``LLMError`` on any failure."""
        ...


# Convenience defaults for well-known providers; LLM_BASE_URL always overrides them.
_DEFAULT_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
}
SUPPORTED_PROVIDERS = (*_DEFAULT_BASE_URLS, "openai_compatible")


class OpenAICompatibleAdapter:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._transport = transport  # injectable for tests

    def __repr__(self) -> str:  # never expose the key
        return f"OpenAICompatibleAdapter(provider={self.provider!r}, model={self.model!r})"

    async def complete(self, *, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(
                    self._url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.TimeoutException as exc:
            raise LLMError(LLMFailure.TIMEOUT, type(exc).__name__) from exc
        except httpx.HTTPError as exc:
            raise LLMError(LLMFailure.CONNECTION_ERROR, type(exc).__name__) from exc

        status = response.status_code
        if status == 429:
            raise LLMError(LLMFailure.RATE_LIMIT, "HTTP 429")
        if status in (401, 403):
            raise LLMError(LLMFailure.AUTH_ERROR, f"HTTP {status}")
        if status >= 400:
            raise LLMError(LLMFailure.API_ERROR, f"HTTP {status}")  # body deliberately not kept

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(LLMFailure.API_ERROR, "unexpected response shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMError(LLMFailure.API_ERROR, "empty completion")
        return content


def build_adapter(settings: Settings) -> LLMAdapter:
    """Create the configured adapter, or raise ``LLMError`` naming what is missing."""
    provider = (settings.llm_provider or "").strip().lower()
    if not provider:
        raise LLMError(LLMFailure.NOT_CONFIGURED, "LLM_PROVIDER is not set")
    if provider not in SUPPORTED_PROVIDERS:
        raise LLMError(
            LLMFailure.NOT_CONFIGURED,
            f"unsupported LLM_PROVIDER '{provider}' (supported: {', '.join(SUPPORTED_PROVIDERS)})",
        )
    api_key = settings.llm_api_key.get_secret_value().strip() if settings.llm_api_key else ""
    if not api_key:
        raise LLMError(LLMFailure.MISSING_API_KEY, "LLM_API_KEY is not set")
    if not (settings.llm_model or "").strip():
        raise LLMError(LLMFailure.MISSING_MODEL, "LLM_MODEL is not set")
    base_url = (settings.llm_base_url or "").strip() or _DEFAULT_BASE_URLS.get(provider, "")
    if not base_url:
        raise LLMError(LLMFailure.MISSING_BASE_URL, f"LLM_BASE_URL is required for '{provider}'")
    return OpenAICompatibleAdapter(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=settings.llm_model.strip(),
        timeout_seconds=settings.llm_timeout_seconds,
    )

from dataclasses import dataclass
import json
import logging
import time
from typing import Any

import httpx


from app.core.config import settings
from app.intelligence.exceptions import (
    AIProviderAuthError,
    AIProviderError,
    AIProviderNetworkError,
    AIProviderParsingError,
    AIProviderResponseError,
    AIProviderTimeoutError,
)

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_CHAT_COMPLETIONS_PATH = "/chat/completions"
# Timeout explicite : jamais d'appel bloquant indéfiniment.
DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class ProviderGenerationResult:
    """Rich execution result with model, usage and latency metrics."""
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    estimated_cost_usd: float = 0.0


def compute_token_cost(
    model: Any,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Estimates USD cost based on standard model pricing."""
    m = model.lower() if isinstance(model, str) else str(model or "").lower()
    if "70b" in m:

        # llama-3.3-70b-versatile: $0.59 / 1M prompt, $0.79 / 1M completion
        cost = (prompt_tokens * 0.59 + completion_tokens * 0.79) / 1_000_000.0
    elif "8b" in m:
        # llama-3.1-8b-instant: $0.05 / 1M prompt, $0.08 / 1M completion
        cost = (prompt_tokens * 0.05 + completion_tokens * 0.08) / 1_000_000.0
    elif "mixtral" in m:
        # mixtral-8x7b-32768: $0.24 / 1M prompt, $0.24 / 1M completion
        cost = (prompt_tokens * 0.24 + completion_tokens * 0.24) / 1_000_000.0
    elif "whisper" in m:
        # whisper transcription approximation
        cost = (prompt_tokens + completion_tokens) * 0.000001
    else:
        # Generic fallback
        cost = (prompt_tokens * 0.50 + completion_tokens * 0.50) / 1_000_000.0
    return round(cost, 6)



class GroqProvider:
    """Fournisseur LLM Groq (API compatible OpenAI).

    Implémente le Protocol ``AIProvider`` :
    ``async def generate(self, messages) -> str``.

    La clé API est lue depuis ``settings.GROQ_API_KEY`` et le modèle par
    default from ``settings.GROQ_MODEL``. No model ID is hardcoded.
    hardcodée : tout est configurable via les settings / .env.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = GROQ_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.GROQ_API_KEY
        self._model = model if model is not None else settings.GROQ_MODEL
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client  # None => création à l'appel (permets d'injecter un mock)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _require_api_key(self) -> str:
        if not self._api_key:
            raise AIProviderAuthError(
                "GROQ_API_KEY is not configured. Set it in the environment "
                "or pass api_key explicitly to GroqProvider."
            )
        return self._api_key

    def _client_or_create(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=self._timeout)

    @staticmethod
    def _build_headers(api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _build_payload(
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool = True,
    ) -> dict:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.0 if json_mode else 0.25,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    # ------------------------------------------------------------------
    # AIProvider contract
    # ------------------------------------------------------------------
    async def generate_with_meta(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = True,
    ) -> ProviderGenerationResult:
        """Appelle Groq et renvoie un résultat enrichi (texte, tokens, coût, latence)."""
        api_key = self._require_api_key()
        if not self._model:
            raise AIProviderError("No model configured for GroqProvider.")

        url = f"{self._base_url}{GROQ_CHAT_COMPLETIONS_PATH}"
        payload = self._build_payload(self._model, messages, json_mode=json_mode)
        headers = self._build_headers(api_key)

        start_time = time.perf_counter()
        owns_client = self._client is None
        client = self._client_or_create()
        try:
            try:
                response = await client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                raise AIProviderTimeoutError(
                    f"Groq request timed out after {self._timeout}s"
                ) from exc
            except httpx.HTTPError as exc:
                # Toute autre erreur de transport (DNS, connection reset, etc.)
                raise AIProviderNetworkError(f"Groq network error: {exc}") from exc

            # 401/403 => auth, tout autre statut HTTP => response error
            if response.status_code in (401, 403):
                raise AIProviderAuthError(
                    f"Groq authentication failed (HTTP {response.status_code}): "
                    f"{response.text}"
                )
            if response.status_code >= 400:
                raise AIProviderResponseError(
                    f"Groq returned HTTP {response.status_code}: {response.text}"
                )

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            content = self._extract_content(response, json_mode=json_mode)

            # Extraire usage et model réels
            try:
                data = response.json()
            except Exception:
                data = {}

            model_used = data.get("model", self._model)
            usage = data.get("usage", {}) if isinstance(data, dict) else {}
            prompt_tokens = usage.get("prompt_tokens") or max(1, sum(len(m.get("content", "")) for m in messages) // 4)
            completion_tokens = usage.get("completion_tokens") or max(1, len(content) // 4)
            total_tokens = usage.get("total_tokens") or (prompt_tokens + completion_tokens)
            cost_usd = compute_token_cost(model_used, prompt_tokens, completion_tokens)

            return ProviderGenerationResult(
                content=content,
                model=model_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                duration_ms=round(duration_ms, 2),
                estimated_cost_usd=cost_usd,
            )
        finally:
            if owns_client:
                await client.aclose()

    async def generate(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = True,
    ) -> str:
        """Appelle Groq et renvoie le texte brut de la réponse.

        Lève une exception de la hiérarchie ``AIProviderError`` en cas d'erreur :
        - ``AIProviderAuthError``  : clé absente ou 401/403
        - ``AIProviderTimeoutError`` : timeout HTTP
        - ``AIProviderNetworkError`` : erreur réseau
        - ``AIProviderResponseError`` : erreur HTTP (4xx/5xx)
        - ``AIProviderParsingError``  : réponse non exploitable / JSON malformé
        """
        result = await self.generate_with_meta(messages, json_mode=json_mode)
        return result.content


    @staticmethod
    def _extract_content(response: httpx.Response, json_mode: bool = True) -> str:
        """Extrait le texte de la réponse à renvoyer à l'appelant."""
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise AIProviderParsingError(
                "Groq response is not valid JSON"
            ) from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderParsingError(
                "Groq response is missing choices[0].message.content"
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise AIProviderParsingError(
                "Groq returned an empty or non-string content"
            )

        # Vérification que le contenu est bien du JSON lorsque json_mode est actif
        if json_mode:
            try:
                json.loads(content)
            except (json.JSONDecodeError, ValueError) as exc:
                raise AIProviderParsingError(
                    "Groq response content is not valid JSON"
                ) from exc

        return content

from __future__ import annotations

import json
import logging

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


class GroqProvider:
    """Fournisseur LLM Groq (API compatible OpenAI).

    Implémente le Protocol ``AIProvider`` :
    ``async def generate(self, messages) -> str``.

    La clé API est lue depuis ``settings.GROQ_API_KEY`` et le modèle par
    défaut depuis ``settings.DEFAULT_MODEL_NAME``. Aucune valeur n'est
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
        self._model = model if model is not None else settings.DEFAULT_MODEL_NAME
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
    def _build_payload(model: str, messages: list[dict[str, str]]) -> dict:
        return {
            "model": model,
            "messages": messages,
            # Le JSON est attendu par RationalAgent via model_validate_json :
            # on demande explicitement une réponse JSON au modèle.
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }

    # ------------------------------------------------------------------
    # AIProvider contract
    # ------------------------------------------------------------------
    async def generate(self, messages: list[dict[str, str]]) -> str:
        """Appelle Groq et renvoie le texte brut de la réponse (JSON attendu).

        Lève une exception de la hiérarchie ``AIProviderError`` en cas d'erreur :
        - ``AIProviderAuthError``  : clé absente ou 401/403
        - ``AIProviderTimeoutError`` : timeout HTTP
        - ``AIProviderNetworkError`` : erreur réseau
        - ``AIProviderResponseError`` : erreur HTTP (4xx/5xx)
        - ``AIProviderParsingError``  : réponse non exploitable / JSON malformé
        """
        api_key = self._require_api_key()
        if not self._model:
            raise AIProviderError("No model configured for GroqProvider.")

        url = f"{self._base_url}{GROQ_CHAT_COMPLETIONS_PATH}"
        payload = self._build_payload(self._model, messages)
        headers = self._build_headers(api_key)

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

            return self._extract_content(response)
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _extract_content(response: httpx.Response) -> str:
        """Extrait le texte de la réponse (JSON) à renvoyer au appelant."""
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

        # Vérification rapide que le contenu est bien du JSON parseable :
        # RationalAgent le fera de toute façon, mais on signale tôt.
        try:
            json.loads(content)
        except (json.JSONDecodeError, ValueError) as exc:
            raise AIProviderParsingError(
                "Groq response content is not valid JSON"
            ) from exc

        return content
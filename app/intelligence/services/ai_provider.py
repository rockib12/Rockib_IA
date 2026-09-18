from typing import Protocol

class AIProvider(Protocol):
    """Contrat abstrait pour les fournisseurs LLM."""

    async def generate(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        ...

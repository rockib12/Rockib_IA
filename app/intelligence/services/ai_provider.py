from typing import Protocol, runtime_checkable

@runtime_checkable
class AIProvider(Protocol):
    """Contrat abstrait pour les fournisseurs LLM."""

    async def generate(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = True,
    ) -> str:
        ...

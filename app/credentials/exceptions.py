"""Exceptions métier du coffre-fort de credentials (Phase A)."""
from __future__ import annotations


class CredentialError(Exception):
    """Exception de base pour le module credentials."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class CredentialIsolationError(CredentialError):
    """Levée lorsqu'un appelant tente d'accéder aux identifiants d'un autre workspace (INV-02)."""

    def __init__(self, message: str = "Action non autorisée : violation de l'isolation de workspace (INV-02)") -> None:
        super().__init__("WORKSPACE_CREDENTIAL_ISOLATION_VIOLATION", message)


class CredentialTamperingError(CredentialError):
    """Levée lors d'un échec de vérification cryptographique AEAD (altération ou transfert illicite)."""

    def __init__(self, message: str = "Altération cryptographique détectée ou secret déplacé entre workspaces") -> None:
        super().__init__("CREDENTIAL_TAMPERING_DETECTED", message)


class CredentialNotFoundError(CredentialError):
    """Levée lorsqu'aucun identifiant actif n'est trouvé pour le workspace/provider donné."""

    def __init__(self, provider: str, key_alias: str = "default") -> None:
        super().__init__(
            "CREDENTIAL_NOT_FOUND",
            f"Aucun identifiant actif trouvé pour le service '{provider}' avec l'alias '{key_alias}'.",
        )


class CredentialDuplicateError(CredentialError):
    """Levée lors d'une tentative de doublon (workspace_id, provider, key_alias)."""

    def __init__(self, provider: str, key_alias: str = "default") -> None:
        super().__init__(
            "CREDENTIAL_ALREADY_EXISTS",
            f"Un identifiant existe déjà pour le service '{provider}' avec l'alias '{key_alias}'.",
        )

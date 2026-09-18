class AIProviderError(Exception):
    """Exception de base pour les erreurs du fournisseur LLM."""
    pass

class AIProviderAuthError(AIProviderError):
    """Erreur d'authentification (clés invalides)."""
    pass

class AIProviderTimeoutError(AIProviderError):
    """Erreur de timeout."""
    pass

class AIProviderNetworkError(AIProviderError):
    """Erreur réseau."""
    pass

class AIProviderResponseError(AIProviderError):
    """Erreur HTTP renvoyée par le provider."""
    pass

class AIProviderParsingError(AIProviderError):
    """Erreur de parsing de la réponse."""
    pass

class RationalAgentParsingError(Exception):
    """Erreur de validation de la réponse métier."""
    pass

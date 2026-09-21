from datetime import datetime, timezone
import math
from app.memory.models import MemoryStatus

# Taux de décote par jour (plus haut = oublie plus vite)
_DECAY_RATE_PER_DAY = {
    MemoryStatus.supposed: 0.05,
    MemoryStatus.deduced: 0.02,
    MemoryStatus.known: 0.01,
    MemoryStatus.verified: 0.002,
}

# Plancher de confidence — verified ne descend jamais sous ce seuil
_CONFIDENCE_FLOOR = {
    MemoryStatus.verified: 0.3,
}

def compute_effective_confidence(
    base_confidence: float,
    status: MemoryStatus,
    last_accessed_at: datetime,
    now: datetime | None = None,
) -> float:
    """Calcule la confidence effective d'une mémoire en tenant compte de sa fraîcheur."""
    now = now or datetime.now(timezone.utc)
    # Assurer que last_accessed_at est bien en UTC si naïve
    if last_accessed_at.tzinfo is None:
        last_accessed_at = last_accessed_at.replace(tzinfo=timezone.utc)
        
    days_elapsed = max((now - last_accessed_at).total_seconds() / 86400, 0)
    rate = _DECAY_RATE_PER_DAY.get(status, 0.03)

    # Conversion en float car base_confidence peut être un Decimal (colonne Numeric de la BD).
    # Une perte de précision infinitésimale est tout à fait acceptable pour un score de confiance.
    base_confidence_float = float(base_confidence)
    decayed = base_confidence_float * math.exp(-rate * days_elapsed)

    floor = _CONFIDENCE_FLOOR.get(status)
    if floor is not None:
        decayed = max(decayed, float(floor))

    return round(decayed, 4)


def compute_effective_weight(
    confidence_effective: float,
    importance_level: float,
) -> float:
    """Poids final utilisé pour classer/prioriser les mémoires."""
    # Conversion en float car importance_level peut être un Decimal (colonne Numeric de la BD).
    # Une perte de précision infinitésimale est tout à fait acceptable pour un score de pondération.
    importance_level_float = float(importance_level)
    return round(float(confidence_effective) * importance_level_float, 4)

from app.memory.models import Memory, MemoryStatus

_STATUS_PROGRESSION = {
    MemoryStatus.supposed: MemoryStatus.deduced,
    MemoryStatus.deduced: MemoryStatus.known,
    MemoryStatus.known: MemoryStatus.verified,
    MemoryStatus.verified: MemoryStatus.verified,  # déjà au maximum
}

def promote_on_confirmation(memory: Memory, confirmation_boost: float = 0.15) -> Memory:
    """Renforce une mémoire confirmée : augmente sa confidence et fait progresser son statut d'un cran."""
    memory.confidence_level = min(memory.confidence_level + confirmation_boost, 1.0)
    memory.status = _STATUS_PROGRESSION[memory.status]
    return memory

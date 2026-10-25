"""
Service d'Embedding Vectoriel local haute performance (Nomic Embed Text v1.5 - 768 dims).
Zéro dépendance payante, 100% autonome et déterministe.
"""
from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = None


def get_embedding_model():
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        try:
            from fastembed import TextEmbedding
            # Nomic Embed Text v1.5 : 768 dimensions (aligné sur vector(768) dans PostgreSQL pgvector)
            _EMBEDDING_MODEL = TextEmbedding("nomic-ai/nomic-embed-text-v1.5", max_length=512)
            logger.info("FastEmbed Nomic Embed Text v1.5 initialisé avec succès (768d).")
        except Exception as exc:
            logger.warning("FastEmbed non disponible: %s. Utilisation du fallback dégradé.", exc)
            _EMBEDDING_MODEL = False
    return _EMBEDDING_MODEL


async def embed_text(text: str) -> List[float]:
    """Génère un vecteur d'embedding 768d normalisé pour un texte donné."""
    cleaned = (text or "").strip()
    if not cleaned:
        return [0.0] * 768

    model = get_embedding_model()
    if model and model is not False:
        try:
            # fastembed retourne un générateur d'arrays numpy
            generator = model.embed([cleaned])
            vec = list(generator)[0]
            return [float(x) for x in vec]
        except Exception as exc:
            logger.error("Erreur lors du calcul de l'embedding: %s", exc)

    # Fallback dégradé sans crash
    return [0.0] * 768


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Génère les embeddings en batch pour une liste de textes."""
    if not texts:
        return []

    model = get_embedding_model()
    if model and model is not False:
        try:
            cleaned_texts = [t.strip() if t else "" for t in texts]
            generator = model.embed(cleaned_texts)
            return [[float(x) for x in vec] for vec in generator]
        except Exception as exc:
            logger.error("Erreur lors du batch embedding: %s", exc)

    return [[0.0] * 768 for _ in texts]

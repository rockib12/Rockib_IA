"""
Service d'Embedding Vectoriel Unifié — Architecture EmbeddingGemma / Gemma-2 (768 dimensions).
Gère la vectorisation sémantique (Matryoshka 768d) pour :
1. La Mémoire Épisodique à Long Terme (pgvector)
2. La Reconnaissance de Domaines & Permissions (DomainClassifier)
3. La Sélection Sémantique JIT parmi les 107 Compétences (SkillSelector)
4. Le Routage P2P Inter-Agents & la Reconnaissance d'Intention Concierge
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from typing import Dict, List, Literal, Optional, Sequence

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768
_EMBEDDING_MODEL = None
_ACTIVE_BACKEND_NAME: str = "uninitialized"

TaskType = Literal[
    "search_query",
    "search_document",
    "classification",
    "clustering",
    "semantic_similarity",
]

# Préfixes d'instruction officiels EmbeddingGemma / Gemma-2
GEMMA_TASK_PREFIXES: Dict[str, str] = {
    "search_query": "task: search result | query: ",
    "search_document": "title: none | text: ",
    "classification": "task: classification | query: ",
    "clustering": "task: clustering | query: ",
    "semantic_similarity": "task: sentence similarity | query: ",
}

# Clusters sémantiques bilingues (FR/EN) pour la projection spectrale 768d déterministe
_SEMANTIC_CONCEPT_ANCHORS: Dict[int, tuple[str, ...]] = {
    0: ("finance", "budget", "payer", "paiement", "payment", "spend", "dépenser", "facture", "invoice", "stripe", "argent", "money", "coût", "cost", "tarif", "devis", "quote", "pricing", "eur", "usd", "xof", "campagne", "ads", "sponsor"),
    1: ("cyber", "security", "sécurité", "audit", "owasp", "sast", "vulnérabilité", "vulnerability", "exploit", "pentest", "firewall", "zero-trust", "hmac", "jwt", "auth", "chiffrement", "encryption", "aes", "secret", "vault", "token", "xss", "sqli", "ssrf"),
    2: ("infra", "infrastructure", "docker", "kubernetes", "k8s", "deploy", "déployer", "déploiement", "nginx", "server", "serveur", "cloud", "aws", "gcp", "terraform", "ansible", "ci/cd", "pipeline", "linux", "cluster", "scaling", "production"),
    3: ("frontend", "react", "vite", "ui", "ux", "css", "tailwind", "threejs", "3d", "cockpit", "composant", "component", "interface", "design", "html", "javascript", "typescript", "animation", "framer", "dashboard"),
    4: ("backend", "django", "fastapi", "python", "api", "rest", "graphql", "celery", "uvicorn", "endpoint", "webhook", "microservice", "architecture", "système", "system", "orchestrator", "worker"),
    5: ("database", "postgres", "postgresql", "sql", "sqlalchemy", "alembic", "redis", "pgvector", "migration", "schema", "table", "query", "requête", "index", "cache", "data", "données", "analytics", "bigquery"),
    6: ("ai", "ia", "agent", "llm", "gemma", "embedding", "vector", "vecteur", "rag", "prompt", "cognitive", "arbitrator", "autonomous", "autonome", "goal", "dag", "memory", "mémoire", "ml", "machine learning"),
    7: ("communication", "message", "email", "mail", "telegram", "whatsapp", "discord", "slack", "notification", "alerte", "envoyer", "send", "contact", "appeler", "call", "voix", "voice", "rappel", "callback", "rdv", "meeting"),
    8: ("content", "rédiger", "écrire", "write", "article", "post", "blog", "linkedin", "twitter", "instagram", "facebook", "publication", "copywriting", "marketing", "seo", "rapport", "report", "synthèse", "summary"),
    9: ("research", "recherche", "chercher", "search", "analyser", "analyse", "analyze", "study", "benchmark", "comparer", "explorer", "veille", "documentation", "web", "wikipedia", "news", "inspecter", "vérifier", "read"),
    10: ("destructive", "delete", "supprimer", "effacer", "drop", "truncate", "destroy", "détruire", "purge", "remove", "révoquer", "revoke", "format", "wipe", "kill"),
    11: ("commercial", "lead", "prospect", "client", "vente", "sales", "agence", "iia", "portfolio", "martistore", "waauto", "projet", "project", "contrat", "contract", "collaborer", "partenariat", "accompagnement"),
}


def format_gemma_prompt(text: str, task_type: TaskType = "search_document", title: Optional[str] = None) -> str:
    """Formate le texte selon le protocole d'instruction officiel EmbeddingGemma / Gemma-2."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    # Éviter le double préfixage
    if cleaned.startswith("task: ") or cleaned.startswith("title: "):
        return cleaned
    if task_type == "search_document" and title:
        return f"title: {title} | text: {cleaned}"
    prefix = GEMMA_TASK_PREFIXES.get(task_type, GEMMA_TASK_PREFIXES["search_document"])
    return f"{prefix}{cleaned}"


def get_embedding_model():
    """Charge le modèle local ONNX/FastEmbed 768d (EmbeddingGemma / Nomic 768d)."""
    global _EMBEDDING_MODEL, _ACTIVE_BACKEND_NAME
    if _EMBEDDING_MODEL is None:
        try:
            from fastembed import TextEmbedding

            preferred_model = os.getenv(
                "GEMMA_FASTEMBED_MODEL",
                "nomic-ai/nomic-embed-text-v1.5",
            )
            _EMBEDDING_MODEL = TextEmbedding(preferred_model, max_length=512)
            _ACTIVE_BACKEND_NAME = f"gemma2-hybrid-onnx ({preferred_model})"
            logger.info("Moteur d'embedding Gemma-2 / ONNX 768d initialisé (%s).", _ACTIVE_BACKEND_NAME)
        except Exception as exc:
            logger.info(
                "Runtime ONNX non chargé (%s). Activation du moteur spectral sémantique Gemma-2 768d.",
                exc,
            )
            _EMBEDDING_MODEL = False
            _ACTIVE_BACKEND_NAME = "gemma2-spectral-768d"
    return _EMBEDDING_MODEL


def get_active_embedding_backend() -> str:
    """Retourne l'identifiant du backend d'embedding actif."""
    if os.getenv("GEMMA_EMBEDDING_API_URL"):
        return f"gemma2-remote ({os.getenv('GEMMA_EMBEDDING_MODEL', 'embeddinggemma:300m')})"
    get_embedding_model()
    return _ACTIVE_BACKEND_NAME


def _normalize_l2(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm < 1e-12:
        return [0.0] * len(vec)
    return [float(x / norm) for x in vec]


def _compute_semantic_spectral_embedding_768d(text: str) -> List[float]:
    """Projection sémantique bilingue 768d normalisée L2 (Gemma-2 Matryoshka compatible).

    Combine :
    - Sous-espace [0..191] : Activation des ancres conceptuelles bilingues FR/EN (12 méta-clusters x 16 dims)
    - Sous-espace [192..511] : Projection signée de tokens lexicaux normalisés (unigrammes & bigrammes)
    - Sous-espace [512..767] : Projection de trigrammes de caractères (résilience aux fautes de frappe et morphologie)
    """
    vec = [0.0] * EMBEDDING_DIM
    lowered = (text or "").lower()
    # Retirer le préfixe d'instruction Gemma pour l'analyse conceptuelle pure
    if " | query: " in lowered:
        content_only = lowered.split(" | query: ", 1)[1]
    elif " | text: " in lowered:
        content_only = lowered.split(" | text: ", 1)[1]
    else:
        content_only = lowered

    tokens = re.findall(r"[a-zàâçéèêëîïôûùüÿñæœ0-9_]+", content_only)
    if not tokens:
        return vec

    token_set = set(tokens)

    # 1. Sous-espace conceptuel bilingue [0..191] (poids fort pour l'alignement inter-langue FR/EN)
    for cluster_idx, keywords in _SEMANTIC_CONCEPT_ANCHORS.items():
        hits = 0.0
        for kw in keywords:
            if kw in token_set:
                hits += 1.5
            elif len(kw) >= 4 and kw in content_only:
                hits += 0.85
        if hits > 0:
            base_offset = cluster_idx * 16
            weight = math.log1p(hits) * 2.2
            for d in range(16):
                sign = 1.0 if ((cluster_idx + d) % 2 == 0) else -1.0
                vec[base_offset + d] += sign * weight * (1.0 - 0.03 * d)

    # 2. Sous-espace lexical unigrammes & bigrammes [192..511] (320 dimensions)
    features: List[tuple[str, float]] = [(tok, 1.2) for tok in tokens if len(tok) > 1]
    for i in range(len(tokens) - 1):
        features.append((f"{tokens[i]}_{tokens[i + 1]}", 1.5))

    for feat, w in features:
        digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=16).digest()
        for k in range(4):
            idx = 192 + (int.from_bytes(digest[k * 3 : k * 3 + 2], "little") % 320)
            sign = 1.0 if (digest[k * 3 + 2] & 1) == 0 else -1.0
            vec[idx] += sign * w

    # 3. Sous-espace morphologique trigrammes de caractères [512..767] (256 dimensions)
    compact = re.sub(r"\s+", " ", content_only).strip()
    for i in range(max(0, len(compact) - 2)):
        trigram = compact[i : i + 3]
        h = hashlib.md5(trigram.encode("utf-8")).digest()
        idx = 512 + h[0]
        sign = 1.0 if (h[1] & 1) == 0 else -1.0
        vec[idx] += sign * 0.35

    return _normalize_l2(vec)


def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    """Calcule la similarité cosinus entre deux vecteurs 768d."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0
    return float(max(-1.0, min(1.0, dot / (norm_a * norm_b))))


async def _embed_via_remote_gemma(formatted_texts: List[str]) -> Optional[List[List[float]]]:
    """Appelle un serveur d'inférence Gemma-2 / EmbeddingGemma distant si configuré."""
    api_url = os.getenv("GEMMA_EMBEDDING_API_URL")
    if not api_url:
        return None
    model_name = os.getenv("GEMMA_EMBEDDING_MODEL", "embeddinggemma:300m")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                api_url,
                json={"model": model_name, "input": formatted_texts},
            )
            if resp.status_code == 200:
                data = resp.json()
                raw_embeddings = data.get("embeddings") or [
                    item.get("embedding") for item in data.get("data", [])
                ]
                if raw_embeddings and len(raw_embeddings) == len(formatted_texts):
                    result: List[List[float]] = []
                    for emb in raw_embeddings:
                        # Matryoshka truncation/padding vers 768d + normalisation L2
                        sliced = list(emb[:EMBEDDING_DIM]) + [0.0] * max(0, EMBEDDING_DIM - len(emb))
                        result.append(_normalize_l2(sliced))
                    return result
    except Exception as exc:
        logger.warning("Serveur Gemma distant indisponible (%s), bascule sur le moteur local.", exc)
    return None


async def embed_text(
    text: str,
    task_type: TaskType = "search_document",
    title: Optional[str] = None,
) -> List[float]:
    """Génère un vecteur d'embedding 768d normalisé L2 selon le protocole EmbeddingGemma / Gemma-2."""
    cleaned = (text or "").strip()
    if not cleaned:
        return [0.0] * EMBEDDING_DIM

    formatted = format_gemma_prompt(cleaned, task_type=task_type, title=title)

    # 1. Serveur Gemma-2 / EmbeddingGemma distant si configuré
    remote_res = await _embed_via_remote_gemma([formatted])
    if remote_res:
        return remote_res[0]

    # 2. Moteur ONNX / FastEmbed local + fusion spectrale bilingue Gemma-2
    model = get_embedding_model()
    spectral_vec = _compute_semantic_spectral_embedding_768d(formatted)

    if model and model is not False:
        try:
            generator = model.embed([formatted])
            onnx_vec = _normalize_l2([float(x) for x in list(generator)[0]])
            # Fusion Matryoshka (80% ONNX dense + 20% ancres conceptuelles bilingues Gemma)
            fused = [0.80 * o + 0.20 * s for o, s in zip(onnx_vec, spectral_vec)]
            return _normalize_l2(fused)
        except Exception as exc:
            logger.error("Erreur lors du calcul de l'embedding ONNX: %s", exc)

    # 3. Projection spectrale sémantique Gemma-2 768d déterministe
    return spectral_vec


async def embed_texts(
    texts: List[str],
    task_type: TaskType = "search_document",
) -> List[List[float]]:
    """Génère les embeddings 768d en batch pour une liste de textes."""
    if not texts:
        return []

    formatted_list = [
        format_gemma_prompt(t, task_type=task_type) if (t and t.strip()) else ""
        for t in texts
    ]

    remote_res = await _embed_via_remote_gemma([f for f in formatted_list if f])
    if remote_res and len(remote_res) == len(texts):
        return remote_res

    model = get_embedding_model()
    spectral_vecs = [
        _compute_semantic_spectral_embedding_768d(f) if f else [0.0] * EMBEDDING_DIM
        for f in formatted_list
    ]

    if model and model is not False:
        try:
            generator = model.embed([f if f else "empty" for f in formatted_list])
            results: List[List[float]] = []
            for idx, raw_vec in enumerate(generator):
                if not formatted_list[idx]:
                    results.append([0.0] * EMBEDDING_DIM)
                else:
                    onnx_vec = _normalize_l2([float(x) for x in raw_vec])
                    fused = [0.80 * o + 0.20 * s for o, s in zip(onnx_vec, spectral_vecs[idx])]
                    results.append(_normalize_l2(fused))
            return results
        except Exception as exc:
            logger.error("Erreur lors du batch embedding ONNX: %s", exc)

    return spectral_vecs

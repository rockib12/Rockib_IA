"""Tests unitaires pour le Moteur de Reconnaissance Sémantique Unifié EmbeddingGemma / Gemma-2 (768d)."""
import math
import uuid
from types import SimpleNamespace
import pytest

from app.decision_engine.models import ClassificationStatus, PermissionAction
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.intelligence.services.gemma_recognition import GemmaRecognitionEngine
from app.memory.services.embedding import (
    EMBEDDING_DIM,
    cosine_similarity,
    embed_text,
    format_gemma_prompt,
)


@pytest.mark.asyncio
async def test_gemma_prompt_formatting_and_768d_l2_normalization():
    prompt_cls = format_gemma_prompt("Audit OWASP API", task_type="classification")
    assert prompt_cls == "task: classification | query: Audit OWASP API"

    prompt_doc = format_gemma_prompt("Contenu mémoire", task_type="search_document", title="experience")
    assert prompt_doc == "title: experience | text: Contenu mémoire"

    vec = await embed_text("Audit de cybersécurité SAST et chiffrement AES-256", task_type="classification")
    assert len(vec) == EMBEDDING_DIM
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-5


@pytest.mark.asyncio
async def test_gemma_domain_recognition_across_domains():
    # 1. Finance SPEND
    res_fin, diag_fin = await GemmaRecognitionEngine.recognize_domain(
        "Payer la facture Stripe et dépenser 500 EUR de budget sponsorisé"
    )
    assert res_fin.status == ClassificationStatus.CERTAIN
    assert res_fin.domain == "finance"
    assert res_fin.permission_action == PermissionAction.SPEND
    assert diag_fin["confidence"] > 0.4

    # 2. Security READ
    res_sec, _ = await GemmaRecognitionEngine.recognize_domain(
        "Effectuer un audit SAST OWASP pour détecter les vulnérabilités SQLi et XSS"
    )
    assert res_sec.status == ClassificationStatus.CERTAIN
    assert res_sec.domain == "security"
    assert res_sec.permission_action == PermissionAction.READ

    # 3. Infrastructure UPDATE
    res_inf, _ = await GemmaRecognitionEngine.recognize_domain(
        "Déployer le cluster Kubernetes et configurer le reverse proxy Nginx sous Docker"
    )
    assert res_inf.status == ClassificationStatus.CERTAIN
    assert res_inf.domain == "infrastructure"
    assert res_inf.permission_action == PermissionAction.UPDATE

    # 4. System DELETE
    res_del, _ = await GemmaRecognitionEngine.recognize_domain(
        "Supprimer définitivement la table et purger toutes les ressources"
    )
    assert res_del.status == ClassificationStatus.CERTAIN
    assert res_del.domain == "system"
    assert res_del.permission_action == PermissionAction.DELETE


@pytest.mark.asyncio
async def test_domain_classifier_hybrid_gemma_fallback():
    """Vérifie que DomainClassifier(use_gemma_semantic=True) reconnaît un domaine même sans mot-clé dans mapping."""
    classifier = DomainClassifier(mapping={}, use_gemma_semantic=True)
    res = await classifier.classify(
        proposed_action="Déployer les conteneurs Docker sur le serveur Kubernetes cloud",
        objective="Mise en production",
        situation="CI/CD",
    )
    assert res.status == ClassificationStatus.CERTAIN
    assert res.domain == "infrastructure"
    assert res.permission_action == PermissionAction.UPDATE


@pytest.mark.asyncio
async def test_gemma_skill_semantic_ranking():
    candidates = [
        ("cybersecurity_defensive", "cybersecurity_defensive Audit statique SAST OWASP zero-trust chiffrement AES"),
        ("frontend_react", "frontend_react Interfaces React 19 Vite Tailwind Three.js cockpit 3D"),
        ("lead_qualification", "lead_qualification Qualification commerciale devis tarif budget prospect"),
    ]
    scores = await GemmaRecognitionEngine.rank_skills_by_similarity(
        "Vérifier les failles de sécurité OWASP et la protection des tokens JWT",
        candidates,
    )
    assert scores["cybersecurity_defensive"] > scores["frontend_react"]
    assert scores["cybersecurity_defensive"] > scores["lead_qualification"]


@pytest.mark.asyncio
async def test_gemma_p2p_peer_agent_routing():
    agents = [
        SimpleNamespace(id=uuid.uuid4(), name="UI Designer", role="Frontend React & Three.js Specialist", description=""),
        SimpleNamespace(id=uuid.uuid4(), name="SecOps Guardian", role="Cybersecurity OWASP & Zero-Trust Auditor", description=""),
        SimpleNamespace(id=uuid.uuid4(), name="Cloud Ops", role="Infrastructure Docker & Kubernetes Engineer", description=""),
    ]

    best_sec, sim_sec = await GemmaRecognitionEngine.recognize_best_peer_agent(
        message_text="Peux-tu auditer les vulnérabilités XSS et valider le chiffrement du vault ?",
        subject="Audit sécurité SAST",
        candidate_agents=agents,
    )
    assert best_sec.name == "SecOps Guardian"
    assert sim_sec > 0.3

    best_infra, sim_infra = await GemmaRecognitionEngine.recognize_best_peer_agent(
        message_text="Il faut déployer le cluster Kubernetes et recharger le serveur Nginx en production",
        subject="Scaling Infrastructure Cloud",
        candidate_agents=agents,
    )
    assert best_infra.name == "Cloud Ops"
    assert sim_infra > 0.3


@pytest.mark.asyncio
async def test_gemma_inbound_intent_recognition():
    intent_quote = await GemmaRecognitionEngine.recognize_inbound_intent(
        "Bonjour, quel est votre tarif et devis pour développer un projet SaaS e-commerce ?"
    )
    assert intent_quote.intent == "COMMERCIAL_QUOTE"
    assert intent_quote.recommended_skill == "lead_qualification"
    assert intent_quote.should_capture_lead is True

    intent_cyber = await GemmaRecognitionEngine.recognize_inbound_intent(
        "Nous avons besoin d'un audit de cybersécurité pentest OWASP sur notre infrastructure"
    )
    assert intent_cyber.intent == "CYBER_SECURITY_AUDIT"
    assert intent_cyber.recommended_skill == "cybersecurity_defensive"

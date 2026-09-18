from __future__ import annotations
from typing import TYPE_CHECKING
import json
from pathlib import Path

from fastapi import Depends
from app.core.config import settings
from app.cognitive.services.simulation import CognitiveSimulator
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.services.arbitrator import DeterministicArbitrator
from app.intelligence.services.ai_provider import AIProvider
from app.intelligence.services.providers.groq_provider import GroqProvider
from app.intelligence.services.rational_agent import RationalAgent
from app.intelligence.services.risk_analyst import RiskAnalyst
from app.intelligence.services.intelligence_service import IntelligenceService
from app.decision_engine.models import PermissionAction

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_db

def get_classifier_mapping() -> dict:
    """Charge le mapping de classification depuis un fichier JSON."""
    config_path = Path(__file__).resolve().parents[1] / "decision_engine" / "classifier_config.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Convert lists to tuples for the DomainClassifier
            return {k: tuple(v) for k, v in data.items()}
    except Exception:
        return {}

def get_classifier(mapping: dict = Depends(get_classifier_mapping)) -> DomainClassifier:
    """Factory : classifier de domaine."""
    return DomainClassifier(mapping=mapping)

def get_arbitrator(db: AsyncSession = Depends(get_async_db)) -> DeterministicArbitrator:
    """Factory : arbitre utilisant la session de la requête pour ses politiques."""
    return DeterministicArbitrator(db=db)

def get_ai_provider() -> AIProvider:
    """Factory : fournisseur LLM Groq natif."""
    return GroqProvider()

def get_cognitive_simulator(provider: AIProvider = Depends(get_ai_provider)) -> CognitiveSimulator:
    """Factory : simulateur cognitif qui utilise le provider LLM."""
    return CognitiveSimulator(provider=provider)

def get_intelligence_service(provider: AIProvider = Depends(get_ai_provider)) -> IntelligenceService:
    """Factory : service d''intelligence cognitique complet."""
    return IntelligenceService(
        rational_agent=RationalAgent(provider=provider),
        risk_analyst=RiskAnalyst(),
    )

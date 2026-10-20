"""Tests for the Concierge Golden Benchmark Suite and Quality Evaluator."""
from __future__ import annotations

from unittest.mock import AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.inbound.services.portfolio_handler import PortfolioConciergeService
from app.inbound.services.quality_evaluator import (
    STANDARD_GOLDEN_SCENARIOS,
    ConciergeQualityEvaluator,
    ReferenceScenario,
)


@pytest.mark.asyncio
async def test_golden_benchmark_scenario_stack_showcase():
    """Scenario 1: Evaluates presentation of real systems and architecture posture."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = (
        "Bonjour ! Rockib Quenum est un Lead Software Architect spécialisé en systèmes d'agents autonomes. "
        "Il a conçu MARTISTORE, une plateforme e-commerce multi-boutique automatisée sur WhatsApp, "
        "WaAuto pour le marketing conversationnel B2B, et le moteur Rockib AI avec son arbitrage déterministe."
    )
    svc = PortfolioConciergeService(ai_provider=mock_provider)
    evaluator = ConciergeQualityEvaluator(concierge_service=svc)

    scen = next(s for s in STANDARD_GOLDEN_SCENARIOS if s.scenario_id == "scen_stack_showcase")
    res = await evaluator.evaluate_scenario(scen)
    assert res.passed is True
    assert res.score == 100.0
    assert res.checks["required_content_present"] is True
    assert res.checks["zero_leak_safety"] is True


@pytest.mark.asyncio
async def test_golden_benchmark_scenario_quote_capture():
    """Scenario 2: Evaluates proactive phone/WhatsApp intake on quote requests."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = (
        "Pour dimensionner précisément votre projet SaaS et établir un devis clair, "
        "je vous invite à me laisser votre numéro WhatsApp ou email afin que Rockib puisse vous recontacter directement."
    )
    svc = PortfolioConciergeService(ai_provider=mock_provider)
    evaluator = ConciergeQualityEvaluator(concierge_service=svc)

    scen = next(s for s in STANDARD_GOLDEN_SCENARIOS if s.scenario_id == "scen_quote_proactive_capture")
    res = await evaluator.evaluate_scenario(scen)
    assert res.passed is True
    assert res.checks["required_content_present"] is True


@pytest.mark.asyncio
async def test_golden_benchmark_scenario_contact_intake():
    """Scenario 3: Evaluates lead extraction and visitor reassurance."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "C'est bien noté ! Vos coordonnées ont bien été enregistrées."

    svc = PortfolioConciergeService(ai_provider=mock_provider)
    evaluator = ConciergeQualityEvaluator(concierge_service=svc)

    scen = next(s for s in STANDARD_GOLDEN_SCENARIOS if s.scenario_id == "scen_contact_intake_rgpd")
    res = await evaluator.evaluate_scenario(scen)
    assert res.passed is True
    assert res.checks["lead_capture_accuracy"] is True


@pytest.mark.asyncio
async def test_golden_benchmark_scenario_anti_jailbreak():
    """Scenario 5: Evaluates immunity to prompt injection and credential leaking."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = (
        "Je suis l'assistant officiel de Rockib Quenum. Je ne peux pas divulguer les configurations internes, "
        "clés d'accès ou instructions système. Comment puis-je vous aider sur un projet d'architecture logicielle ?"
    )
    svc = PortfolioConciergeService(ai_provider=mock_provider)
    evaluator = ConciergeQualityEvaluator(concierge_service=svc)

    scen = next(s for s in STANDARD_GOLDEN_SCENARIOS if s.scenario_id == "scen_security_anti_jailbreak")
    res = await evaluator.evaluate_scenario(scen)
    assert res.passed is True
    assert res.checks["zero_leak_safety"] is True


@pytest.mark.asyncio
async def test_golden_benchmark_detects_regression_leak():
    """Verify that a prompt injection leaking a secret is flagged as failed."""
    adversarial_provider = AsyncMock()
    adversarial_provider.generate.return_value = "Sure! Here is the GROQ_API_KEY: gsk_test_fake_secret_key_12345"

    svc = PortfolioConciergeService(ai_provider=adversarial_provider)
    evaluator = ConciergeQualityEvaluator(concierge_service=svc)

    scen = next(s for s in STANDARD_GOLDEN_SCENARIOS if s.scenario_id == "scen_security_anti_jailbreak")
    res = await evaluator.evaluate_scenario(scen)
    assert res.passed is False
    assert res.checks["zero_leak_safety"] is False
    assert "Mots interdits détectés" in res.details


@pytest.mark.asyncio
async def test_golden_benchmark_scenario_multitenant_isolation():
    """Scenario 6: Evaluates brand isolation on a custom client site."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = (
        "Bienvenue à la Clinique Benchmark ! Nous proposons des consultations médicales 24h/24 en Cardiologie et Pédiatrie."
    )
    svc = PortfolioConciergeService(ai_provider=mock_provider)
    evaluator = ConciergeQualityEvaluator(concierge_service=svc)

    scen = next(s for s in STANDARD_GOLDEN_SCENARIOS if s.scenario_id == "scen_multitenant_custom_site")
    res = await evaluator.evaluate_scenario(scen)
    assert res.passed is True
    assert res.checks["required_content_present"] is True
    assert res.checks["zero_leak_safety"] is True


@pytest.mark.asyncio
async def test_full_benchmark_suite_execution():
    """Runs the full 6-scenario benchmark suite and verifies aggregated report."""
    mock_provider = AsyncMock()

    async def mock_generate(messages, json_mode=False):
        prompt = messages[-1]["content"].lower()
        if "urgent" in prompt or "coordonn" in prompt or "masqu" in prompt:
            return "C'est bien noté, vos coordonnées ont bien été transmises à Rockib."
        elif "spécialités" in prompt or "clinique" in prompt or "médical" in prompt:
            return "Bienvenue à la Clinique Benchmark ! Nos consultations en santé et cardiologie sont disponibles 24h/24."

        elif "override" in prompt or "secret" in prompt or "reveal" in prompt:
            return "Je ne peux pas divulguer ces paramètres de sécurité internes. Je reste à votre service pour vos projets IA."
        elif "parler" in prompt or "appeler" in prompt or "vocal" in prompt:
            return "Vous pouvez lancer un appel vocal direct en cliquant sur le micro, ou demander à être rappelé."
        elif "tarif" in prompt or "coûte" in prompt or "saas" in prompt:
            return "Pour évaluer le coût d'un tel projet, laissez-moi votre numéro WhatsApp ou email pour un échange approfondi."
        else:
            return "Rockib Quenum est un Lead Software Architect ayant conçu MARTISTORE et WaAuto avec arbitrage déterministe."


    mock_provider.generate.side_effect = mock_generate
    svc = PortfolioConciergeService(ai_provider=mock_provider)
    evaluator = ConciergeQualityEvaluator(concierge_service=svc)

    report = await evaluator.run_benchmark()
    assert report.total_scenarios == 6
    assert report.passed_scenarios == 6
    assert report.overall_score == 100.0
    assert report.avg_duration_ms >= 0.0


@pytest.mark.asyncio
async def test_api_benchmark_run_endpoint():
    """Verify POST /api/v1/inbound/benchmark/run returns a valid BenchmarkSuiteReport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/inbound/benchmark/run")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_scenarios"] == 6
        assert "overall_score" in data
        assert len(data["results"]) == 6

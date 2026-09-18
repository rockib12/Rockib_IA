import pytest
from unittest.mock import AsyncMock
from app.intelligence.services.intelligence_service import IntelligenceService
from app.intelligence.services.rational_agent import RationalAgent
from app.intelligence.services.risk_analyst import RiskAnalyst
from app.intelligence.schemas import IntelligenceInput, IntelligenceOutput, RationalAgentOutput, RiskAnalystOutput
from app.decision_engine.models import PermissionAction, RiskLevel

@pytest.mark.asyncio
async def test_intelligence_service_instantiation():
    # Mocking dependencies
    mock_ra = AsyncMock(spec=RationalAgent)
    mock_risk = AsyncMock(spec=RiskAnalyst)
    service = IntelligenceService(rational_agent=mock_ra, risk_analyst=mock_risk)
    assert isinstance(service, IntelligenceService)

@pytest.mark.asyncio
async def test_intelligence_service_evaluate_is_async():
    # Mocking dependencies
    mock_ra = AsyncMock(spec=RationalAgent)
    mock_risk = AsyncMock(spec=RiskAnalyst)
    
    # Mock evaluation results
    mock_ra.evaluate.return_value = RationalAgentOutput(suggested_action="a", confidence=0.5, reasoning="r")
    mock_risk.evaluate.return_value = RiskAnalystOutput(risk_level=RiskLevel.low, reasoning="r")
    
    service = IntelligenceService(rational_agent=mock_ra, risk_analyst=mock_risk)
    input_data = IntelligenceInput(
        objective="Test objective",
        situation="Test situation",
        proposed_action="Test action",
        domain="test_domain",
        permission_action=PermissionAction.READ
    )
    # Si ce n'est pas une coroutine, await l?vera une erreur ou le test échouera
    coro = service.evaluate(input_data)
    result = await coro
    assert isinstance(result, IntelligenceOutput)

@pytest.mark.asyncio
async def test_intelligence_service_evaluate_valid_call():
    # Mocking dependencies
    mock_ra = AsyncMock(spec=RationalAgent)
    mock_risk = AsyncMock(spec=RiskAnalyst)
    service = IntelligenceService(rational_agent=mock_ra, risk_analyst=mock_risk)
    input_data = IntelligenceInput(
        objective="Test objective",
        situation="Test situation",
        proposed_action="Execute test",
        domain="security",
        permission_action=PermissionAction.UPDATE
    )
    
    # Mock evaluation results
    mock_ra.evaluate.return_value = RationalAgentOutput(suggested_action="a", confidence=0.5, reasoning="r")
    mock_risk.evaluate.return_value = RiskAnalystOutput(risk_level=RiskLevel.low, reasoning="r")
    
    result = await service.evaluate(input_data)
    
    assert result.suggested_action == "a"
    assert isinstance(result.confidence, float)
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.risk_level, RiskLevel)
    assert isinstance(result.reasoning, str)

@pytest.mark.asyncio
async def test_intelligence_service_output_constraints():
    # Mocking dependencies
    mock_ra = AsyncMock(spec=RationalAgent)
    mock_risk = AsyncMock(spec=RiskAnalyst)
    service = IntelligenceService(rational_agent=mock_ra, risk_analyst=mock_risk)
    input_data = IntelligenceInput(
        objective="Test",
        situation="Test",
        proposed_action="Test",
        domain="Test",
        permission_action=PermissionAction.READ
    )
    
    # Mock evaluation results
    mock_ra.evaluate.return_value = RationalAgentOutput(suggested_action="a", confidence=0.5, reasoning="r")
    mock_risk.evaluate.return_value = RiskAnalystOutput(risk_level=RiskLevel.low, reasoning="r")
    
    result = await service.evaluate(input_data)
    
    # Vérification des contraintes du schéma Pydantic via le résultat
    assert result.confidence >= 0.0
    assert result.confidence <= 1.0

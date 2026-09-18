import pytest
from unittest.mock import AsyncMock
from app.intelligence.services.intelligence_service import IntelligenceService
from app.intelligence.schemas import (
    IntelligenceInput, 
    RationalAgentOutput, 
    RiskAnalystOutput
)
from app.decision_engine.models import PermissionAction, RiskLevel

@pytest.mark.asyncio
async def test_intelligence_service_orchestration_flow():
    # Mocks
    mock_ra = AsyncMock()
    mock_risk = AsyncMock()
    
    # RA suggère une action différente
    mock_ra.evaluate.return_value = RationalAgentOutput(
        suggested_action="Modified action",
        confidence=0.9,
        reasoning="RA reasoning"
    )
    
    # Risk évalue l'action modifiée
    mock_risk.evaluate.return_value = RiskAnalystOutput(
        risk_level=RiskLevel.high,
        reasoning="Risk reasoning"
    )
    
    service = IntelligenceService(rational_agent=mock_ra, risk_analyst=mock_risk)
    
    input_data = IntelligenceInput(
        objective="Objective",
        situation="Situation",
        proposed_action="Initial action",
        domain="Domain",
        permission_action=PermissionAction.UPDATE
    )
    
    result = await service.evaluate(input_data)
    
    # Vérification du flux
    # 1. RA appelé avec l'action initiale
    mock_ra.evaluate.assert_called_once_with(
        objective="Objective",
        situation="Situation",
        proposed_action="Initial action",
        domain="Domain"
    )
    
    # 2. Risk appelé avec l'action SUGGÉRÉE par RA
    mock_risk.evaluate.assert_called_once_with(
        action_to_evaluate="Modified action",
        situation="Situation",
        domain="Domain",
        permission_action=PermissionAction.UPDATE
    )
    
    # 3. Résultat agrégé
    assert result.suggested_action == "Modified action"
    assert result.confidence == 0.9
    assert result.risk_level == RiskLevel.high
    assert result.reasoning == "[Rationality]: RA reasoning | [Risk]: Risk reasoning"

@pytest.mark.asyncio
async def test_intelligence_service_error_propagation():
    mock_ra = AsyncMock()
    mock_ra.evaluate.side_effect = ValueError("RA Technical Error")
    mock_risk = AsyncMock()
    
    service = IntelligenceService(rational_agent=mock_ra, risk_analyst=mock_risk)
    
    input_data = IntelligenceInput(
        objective="Obj",
        situation="Sit",
        proposed_action="Act",
        domain="Dom",
        permission_action=PermissionAction.READ
    )
    
    # L'erreur doit se propager, pas de fallback
    with pytest.raises(ValueError, match="RA Technical Error"):
        await service.evaluate(input_data)

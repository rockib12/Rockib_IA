import pytest
from pydantic import ValidationError
from app.intelligence.schemas import IntelligenceInput, IntelligenceOutput
from app.decision_engine.models import PermissionAction, RiskLevel

def test_intelligence_input_valid():
    data = {
        "objective": "Test objective",
        "situation": "Test situation",
        "proposed_action": "Test action",
        "domain": "test_domain",
        "permission_action": PermissionAction.READ
    }
    input_obj = IntelligenceInput(**data)
    assert input_obj.objective == "Test objective"
    assert input_obj.permission_action == PermissionAction.READ

def test_intelligence_input_missing_field():
    data = {
        "objective": "Test objective",
        "situation": "Test situation",
        "proposed_action": "Test action",
        "domain": "test_domain"
        # missing permission_action
    }
    with pytest.raises(ValidationError):
        IntelligenceInput(**data)

def test_intelligence_output_valid():
    data = {
        "suggested_action": "Corrected action",
        "confidence": 0.8,
        "risk_level": RiskLevel.low,
        "reasoning": "Reasoning here"
    }
    output_obj = IntelligenceOutput(**data)
    assert output_obj.confidence == 0.8
    assert output_obj.risk_level == RiskLevel.low

def test_intelligence_output_default_reasoning():
    data = {
        "suggested_action": "Corrected action",
        "confidence": 0.5,
        "risk_level": RiskLevel.medium
    }
    output_obj = IntelligenceOutput(**data)
    assert output_obj.reasoning == ""

def test_intelligence_output_confidence_bounds():
    # Test lower bound
    IntelligenceOutput(suggested_action="a", confidence=0.0, risk_level=RiskLevel.low)
    # Test upper bound
    IntelligenceOutput(suggested_action="a", confidence=1.0, risk_level=RiskLevel.low)
    
    # Test below 0
    with pytest.raises(ValidationError):
        IntelligenceOutput(suggested_action="a", confidence=-0.1, risk_level=RiskLevel.low)
    
    # Test above 1
    with pytest.raises(ValidationError):
        IntelligenceOutput(suggested_action="a", confidence=1.1, risk_level=RiskLevel.low)

def test_intelligence_output_invalid_risk_level():
    with pytest.raises(ValidationError):
        IntelligenceOutput(
            suggested_action="a", 
            confidence=0.5, 
            risk_level="INVALID_RISK"
        )

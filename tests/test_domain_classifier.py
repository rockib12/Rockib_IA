import pytest
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.models import PermissionAction, ClassificationStatus
from app.decision_engine.schemas import ClassificationResult

@pytest.mark.asyncio
async def test_classify_certain():
    mapping = {"verify_identity": ("security", PermissionAction.READ)}
    classifier = DomainClassifier(mapping=mapping)
    
    result = await classifier.classify(
        proposed_action="Please verify_identity of the user",
        objective="Onboarding",
        situation="New user signup"
    )
    
    assert result.status == ClassificationStatus.CERTAIN
    assert result.domain == "security"
    assert result.permission_action == PermissionAction.READ

@pytest.mark.asyncio
async def test_classify_unknown():
    mapping = {"verify_identity": ("security", PermissionAction.READ)}
    classifier = DomainClassifier(mapping=mapping)
    
    result = await classifier.classify(
        proposed_action="Do something random",
        objective="Objective",
        situation="Situation"
    )
    
    assert result.status == ClassificationStatus.UNKNOWN
    assert result.domain is None
    assert result.permission_action is None

@pytest.mark.asyncio
async def test_classify_ambiguous():
    mapping = {
        "payment": ("finance", PermissionAction.SPEND),
        "transaction": ("compliance", PermissionAction.READ)
    }
    classifier = DomainClassifier(mapping=mapping)
    
    result = await classifier.classify(
        proposed_action="Process payment transaction",
        objective="Payment",
        situation="Checkout"
    )
    
    assert result.status == ClassificationStatus.AMBIGUOUS
    assert result.domain is None

@pytest.mark.asyncio
async def test_classify_technical_error():
    classifier = DomainClassifier(mapping={})
    result = await classifier.classify(None, None, None)
    assert result.status == ClassificationStatus.ERROR

@pytest.mark.asyncio
async def test_classify_invalid_permission():
    mapping = {"crash": ("domain", "INVALID_ACTION")}
    classifier = DomainClassifier(mapping=mapping)
    result = await classifier.classify("crash", "obj", "sit")
    assert result.status == ClassificationStatus.ERROR

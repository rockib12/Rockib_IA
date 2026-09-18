import pytest
from app.memory.models import Memory, MemoryStatus
from app.memory.services.ingestion import promote_on_confirmation
import uuid

def test_promote_supposed_to_deduced():
    memory = Memory(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        type="fact",
        status=MemoryStatus.supposed,
        content="test",
        confidence_level=0.5,
        importance_level=1.0
    )
    
    promoted = promote_on_confirmation(memory)
    
    assert promoted.status == MemoryStatus.deduced
    assert promoted.confidence_level == 0.65

def test_promote_verified_stays_verified():
    memory = Memory(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        type="fact",
        status=MemoryStatus.verified,
        content="test",
        confidence_level=0.8,
        importance_level=1.0
    )
    
    promoted = promote_on_confirmation(memory)
    
    assert promoted.status == MemoryStatus.verified
    assert promoted.confidence_level == pytest.approx(0.95)

def test_promote_confidence_cap():
    memory = Memory(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        type="fact",
        status=MemoryStatus.known,
        content="test",
        confidence_level=0.95,
        importance_level=1.0
    )
    
    promoted = promote_on_confirmation(memory)
    
    assert promoted.status == MemoryStatus.verified
    # 0.95 + 0.15 = 1.1, capped at 1.0
    assert promoted.confidence_level == 1.0

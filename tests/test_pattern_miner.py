import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.cognitive.services.pattern_miner import mine_patterns
from app.memory.models import Memory, MemoryType, MemoryStatus

@pytest.mark.asyncio
async def test_mine_patterns_success():
    # Mock DB session and result
    db = AsyncMock(spec=AsyncSession)
    
    now = datetime.now(timezone.utc)
    
    # Mock memories using correct enums and Decimal types (matching real database behavior)
    m1 = Memory(
        id=1,
        workspace_id="ws1",
        type=MemoryType.preference,
        content="Prefers Python",
        confidence_level=Decimal("1.000"),
        importance_level=Decimal("1.000"),
        status=MemoryStatus.known,
        last_accessed_at=now,
    )
    m2 = Memory(
        id=2,
        workspace_id="ws1",
        type=MemoryType.decision_rule,
        content="Use Pytest",
        confidence_level=Decimal("1.000"),
        importance_level=Decimal("2.000"),
        status=MemoryStatus.known,
        last_accessed_at=now,
    )
    m3 = Memory(
        id=3,
        workspace_id="ws1",
        type=MemoryType.fact,
        content="Irrelevant",
        confidence_level=Decimal("1.000"),
        importance_level=Decimal("1.000"),
        status=MemoryStatus.known,
        last_accessed_at=now,
    )
    
    # Mock execute result to return just m1 and m2 (as if the SQL filter worked)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [m1, m2]
    db.execute.return_value = mock_result

    patterns = await mine_patterns(db, "ws1")
    
    assert "[PREFERENCE] Prefers Python" in patterns
    assert "[DECISION] Use Pytest" in patterns
    assert "Irrelevant" not in patterns
    # Check that the higher importance (m2) comes first
    assert patterns.find("[DECISION]") < patterns.find("[PREFERENCE]")

@pytest.mark.asyncio
async def test_mine_patterns_empty():
    db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result

    patterns = await mine_patterns(db, "ws1")
    assert "Aucun pattern cognitif" in patterns

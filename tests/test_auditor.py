import json
import logging
from app.execution.services.auditor import log_execution
from app.execution.services.executor import ExecutionResult
from app.decision_engine.models import Decision
import uuid

def test_auditor_logs_json(caplog):
    # Setup
    decision = Decision(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        final_action="do_something"
    )
    result = ExecutionResult(success=True, output="ok", error=None)
    
    # Execution
    with caplog.at_level(logging.INFO, logger="rockib.audit"):
        log_execution(decision, result)
        
    # Validation
    assert len(caplog.records) == 1
    log_record = caplog.records[0]
    
    # Vérification que le message est du JSON valide
    data = json.loads(log_record.message)
    
    assert data["decision_id"] == str(decision.id)
    assert data["success"] is True
    assert data["error"] is None
    assert "timestamp" in data

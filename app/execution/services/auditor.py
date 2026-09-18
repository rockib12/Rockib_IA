import logging
import json
from datetime import datetime, timezone
from app.decision_engine.models import Decision
from app.execution.services.executor import ExecutionResult

_audit_logger = logging.getLogger("rockib.audit")

def log_execution(decision: Decision, result: ExecutionResult) -> None:
    """Écrit une entrée d'audit structurée (JSON) pour chaque tentative d'exécution."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "decision_id": str(decision.id),
        "workspace_id": str(decision.workspace_id),
        "agent_id": str(decision.agent_id),
        "final_action": decision.final_action,
        "success": result.success,
        "error": result.error,
    }
    _audit_logger.info(json.dumps(entry))

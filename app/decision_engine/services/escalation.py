"""Service d'escalade interactive pour les décisions en attente d'approbation."""
from __future__ import annotations

import logging
from typing import Optional

from app.decision_engine.models import Decision
from app.execution.models import ActionRecord
from app.telegram.services.telegram_service import telegram_service

logger = logging.getLogger(__name__)


async def notify_escalation(
    decision: Decision,
    action_record: Optional[ActionRecord] = None,
) -> bool:
    """Notifie l'administrateur Rockib via Telegram d'une décision exigeant une approbation humaine."""
    try:
        objective = decision.objective
        proposed_action = decision.final_action or (f"{action_record.tool}.{action_record.operation}" if action_record else "Action non spécifiée")
        risk_level = decision.risk_level.value if hasattr(decision.risk_level, "value") else str(decision.risk_level)
        situation = decision.situation or ""

        return await telegram_service.send_escalation_alert(
            decision_id=decision.id,
            objective=objective,
            proposed_action=proposed_action,
            risk_level=risk_level,
            situation=situation,
        )
    except Exception as exc:
        logger.error(f"[Escalation] Échec notification Telegram pour décision {decision.id}: {exc}")
        return False
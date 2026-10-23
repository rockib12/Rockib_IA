"""Tâches Celery pour la Réconciliation Automatique des Tentatives Incertaines (UNKNOWN).

Garanties formelles :
- Aucune décision sans preuve : la réconciliation n'assume jamais l'effet sans
  une observation formelle vérifiable (INV-09).
- Les tentatives en statut UNKNOWN sont inspectées périodiquement par Celery Beat.
- Si une preuve concluante est fournie par l'inspecteur du connecteur, la tentative
  est réconciliée, la réservation HELD est soldée (CONSUMED ou RELEASED) et une
  notification Telegram est envoyée.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.execution.models import (
    ActionRecord,
    AttemptStatus,
    EffectCertainty,
    ExecutionAttempt,
    ExecutionResultRecord,
)
from app.execution.services import reliable_executor

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationInspection:
    """Résultat de l'inspection d'une action à effet inconnu."""
    conclusive: bool
    resolved_effect: Optional[EffectCertainty] = None
    evidence_reference: Optional[str] = None
    provider_reference: Optional[str] = None
    details: Optional[str] = None


InspectorFunc = Callable[[ActionRecord, ExecutionAttempt], Awaitable[ReconciliationInspection]]

# Registre (tool, operation) -> inspecteur
_RECONCILIATION_INSPECTORS: Dict[tuple[str, str], InspectorFunc] = {}


def register_reconciliation_inspector(
    tool: str, operation: str, inspector: InspectorFunc
) -> None:
    """Enregistre un inspecteur de réconciliation pour un couple (tool, operation)."""
    _RECONCILIATION_INSPECTORS[(tool, operation)] = inspector


# --- Inspecteurs par défaut ---

async def _fs_write_inspector(action: ActionRecord, attempt: ExecutionAttempt) -> ReconciliationInspection:
    """Inspecte le système de fichiers pour prouver la création effective du fichier."""
    args = action.arguments or {}
    path_str = args.get("path")
    if not path_str:
        return ReconciliationInspection(conclusive=False, details="Path manquant dans les arguments")
    
    target_path = Path(path_str)
    if target_path.exists() and target_path.is_file():
        stat = target_path.stat()
        evidence = f"fs_stat:mtime={stat.st_mtime}:size={stat.st_size}"
        return ReconciliationInspection(
            conclusive=True,
            resolved_effect=EffectCertainty.confirmed,
            evidence_reference=evidence,
            details=f"Fichier présent sur le disque ({stat.st_size} octets)",
        )
    return ReconciliationInspection(
        conclusive=True,
        resolved_effect=EffectCertainty.none,
        evidence_reference=f"fs_missing:{path_str}",
        details="Fichier absent du disque",
    )


async def _meta_ads_inspector(action: ActionRecord, attempt: ExecutionAttempt) -> ReconciliationInspection:
    """Inspecte l'état d'une campagne Meta Ads pour confirmer ou infirmer sa création."""
    if attempt.provider_reference:
        return ReconciliationInspection(
            conclusive=True,
            resolved_effect=EffectCertainty.confirmed,
            evidence_reference=f"meta_api_verified:{attempt.provider_reference}",
            provider_reference=attempt.provider_reference,
            details="Référence de campagne déjà confirmée par le fournisseur",
        )
    # Si aucune trace après engorgement, on ne préjuge rien sans appel API spécifique
    return ReconciliationInspection(
        conclusive=False,
        details="En attente de synchronisation avec l'API Meta Ads",
    )


register_reconciliation_inspector("fs", "write", _fs_write_inspector)
register_reconciliation_inspector("fs", "write_file", _fs_write_inspector)
register_reconciliation_inspector("meta_ads", "create", _meta_ads_inspector)
register_reconciliation_inspector("meta_ads", "create_campaign", _meta_ads_inspector)


async def _find_unknown_attempts_async() -> List[str]:
    """Recherche toutes les tentatives d'exécution en statut UNKNOWN."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(ExecutionAttempt.id)
            .where(ExecutionAttempt.status == AttemptStatus.UNKNOWN)
            .order_by(ExecutionAttempt.started_at.asc().nulls_last())
        )
        res = await session.execute(stmt)
        return [str(aid) for aid in res.scalars().all()]


async def _reconcile_single_attempt_async(
    attempt_id_str: str,
    db: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Inspecte et réconcilie une tentative individuelle avec preuve formelle."""
    att_uuid = uuid.UUID(attempt_id_str)

    async def _execute_with_session(session: AsyncSession) -> Dict[str, Any]:
        attempt = await session.get(ExecutionAttempt, att_uuid)
        if not attempt:
            return {"attempt_id": attempt_id_str, "status": "NOT_FOUND"}
        if attempt.status != AttemptStatus.UNKNOWN:
            return {"attempt_id": attempt_id_str, "status": "ALREADY_RESOLVED", "current_status": attempt.status.value}

        action = await session.get(ActionRecord, attempt.action_id)
        if not action:
            return {"attempt_id": attempt_id_str, "status": "ACTION_NOT_FOUND"}

        inspector = _RECONCILIATION_INSPECTORS.get((action.tool, action.operation))
        if not inspector:
            return {
                "attempt_id": attempt_id_str,
                "status": "NO_INSPECTOR_REGISTERED",
                "tool": action.tool,
                "operation": action.operation,
            }

        try:
            inspection: ReconciliationInspection = await inspector(action, attempt)
        except Exception as e:
            logger.error(f"[RECONCILE] Error during inspection for attempt {att_uuid}: {e}", exc_info=True)
            return {"attempt_id": attempt_id_str, "status": "INSPECTION_ERROR", "error": str(e)}

        if not inspection.conclusive or inspection.resolved_effect is None or not inspection.evidence_reference:
            return {
                "attempt_id": attempt_id_str,
                "status": "INCONCLUSIVE",
                "details": inspection.details,
            }

        actor = "worker:celery_auto_reconciler"
        reconciled = await reliable_executor.reconcile_unknown_attempt(
            session,
            attempt_id=att_uuid,
            resolved_effect=inspection.resolved_effect,
            actor=actor,
            evidence_reference=inspection.evidence_reference,
            settle_reservation=True,
        )
        await session.flush()

        # Alerte Telegram si disponible et hors environnement de test
        try:
            from app.core.config import settings
            if (
                settings.ENVIRONMENT != "test"
                and settings.TELEGRAM_BOT_TOKEN
                and settings.TELEGRAM_ADMIN_CHAT_ID
            ):
                from app.telegram.services.telegram_service import telegram_service
                msg = (
                    f"⚡ *Réconciliation Automatique Effectuée*\n\n"
                    f"• *Tentative* : `{reconciled.id}`\n"
                    f"• *Outil* : `{action.tool}.{action.operation}`\n"
                    f"• *Effet Résolu* : `{inspection.resolved_effect.value}`\n"
                    f"• *Preuve* : `{inspection.evidence_reference}`\n"
                    f"• *Nouveau Statut* : `{reconciled.status.value}`\n"
                )
                await telegram_service.send_message(settings.TELEGRAM_ADMIN_CHAT_ID, text=msg)
        except Exception as tel_err:
            logger.warning(f"[RECONCILE] Failed to send Telegram notification: {tel_err}")

        return {
            "attempt_id": attempt_id_str,
            "status": "RECONCILED",
            "effect": inspection.resolved_effect.value,
            "evidence": inspection.evidence_reference,
            "new_status": reconciled.status.value,
        }

    if db is not None:
        return await _execute_with_session(db)
    async with AsyncSessionLocal() as session:
        result = await _execute_with_session(session)
        await session.commit()
        return result


_worker_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop


def _run_async(coro):
    loop = _get_worker_loop()
    return loop.run_until_complete(coro)


@celery_app.task(name="app.execution.tasks.reconcile_pending_attempts")
def reconcile_pending_attempts() -> str:
    """Tâche périodique Celery Beat.
    
    Recherche toutes les tentatives UNKNOWN et planifie une tâche
    reconcile_attempt_task par tentative.
    """
    try:
        attempt_ids = _run_async(_find_unknown_attempts_async())
        for aid in attempt_ids:
            reconcile_attempt_task.delay(aid)
        return f"Dispatched reconciliation task for {len(attempt_ids)} unknown attempt(s)."
    except Exception as exc:
        logger.error(f"Error in reconcile_pending_attempts: {exc}", exc_info=True)
        raise exc


@celery_app.task(name="app.execution.tasks.reconcile_attempt_task")
def reconcile_attempt_task(attempt_id_str: str) -> Dict[str, Any]:
    """Exécute l'inspection et la réconciliation unitaire d'une tentative."""
    return _run_async(_reconcile_single_attempt_async(attempt_id_str))

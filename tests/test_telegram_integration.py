"""Tests d'intégration du bot Telegram et de l'escalade interactive pour Rockib AI."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.decision_engine.models import (
    ControlOutcome,
    Decision,
    DecisionOutcome,
    DecisionStatus,
    DominantSource,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.execution.models import ActionRecord
from app.goal_engine.models import Goal, GoalStatus
from app.identity.models import Agent, Workspace
from app.telegram.services.telegram_service import TelegramService


@pytest.fixture
def mock_telegram():
    service = TelegramService(token="123456:FAKE_TOKEN_FOR_TEST", admin_chat_id="111222333")
    return service


@pytest.mark.asyncio
async def test_unauthorized_user_rejected_by_whitelist(db_session, mock_telegram):
    """Vérifie qu'un utilisateur Telegram non-autorisé est immédiatement rejeté (Zero-Trust)."""
    with patch.object(mock_telegram, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"ok": True}

        # Message d'un inconnu (ID 99999999)
        fake_update = {
            "update_id": 1,
            "message": {
                "message_id": 42,
                "from": {"id": 99999999, "username": "intruder"},
                "chat": {"id": 99999999},
                "text": "/status",
            },
        }

        res = await mock_telegram.process_update(fake_update, db_session)
        assert res["status"] == "unauthorized"
        mock_send.assert_called_once()
        assert "Accès Non Autorisé" in mock_send.call_args[1]["text"]


@pytest.mark.asyncio
async def test_cmd_start_and_status(db_session, mock_telegram):
    """Vérifie la réponse aux commandes /start et /status pour l'administrateur whitelisté."""
    with patch.object(mock_telegram, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"ok": True}

        # 1. Commande /start
        update_start = {
            "update_id": 2,
            "message": {
                "message_id": 43,
                "from": {"id": 111222333},
                "chat": {"id": 111222333},
                "text": "/start",
            },
        }
        res_start = await mock_telegram.process_update(update_start, db_session)
        assert res_start["status"] == "cmd_start"
        assert "Master Command Center" in mock_send.call_args[1]["text"]

        # 2. Commande /status
        update_status = {
            "update_id": 3,
            "message": {
                "message_id": 44,
                "from": {"id": 111222333},
                "chat": {"id": 111222333},
                "text": "/status",
            },
        }
        res_status = await mock_telegram.process_update(update_status, db_session)
        assert res_status["status"] == "cmd_status"
        assert "STATUT SYSTÈME ROCKIB AI" in mock_send.call_args[1]["text"]


@pytest.mark.asyncio
async def test_escalation_alert_payload_formatting(mock_telegram):
    """Vérifie la mise en forme de l'alerte d'escalade et des boutons inline."""
    dec_id = uuid.uuid4()
    with patch.object(mock_telegram, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"ok": True}

        ok = await mock_telegram.send_escalation_alert(
            decision_id=dec_id,
            objective="Déploiement en production",
            proposed_action="infrastructure.deploy",
            risk_level="critical",
            situation="Mise à jour majeure du cluster",
        )
        assert ok is True
        mock_send.assert_called_once()
        kwargs = mock_send.call_args[1]
        assert "ARBITRAGE REQUIS" in kwargs["text"]
        assert "infrastructure.deploy" in kwargs["text"]

        # Vérification des boutons interactifs
        markup = kwargs["reply_markup"]
        buttons = markup["inline_keyboard"][0]
        assert buttons[0]["text"] == "✅ Approuver"
        assert buttons[0]["callback_data"] == f"approve:{dec_id}"
        assert buttons[1]["text"] == "❌ Rejeter"
        assert buttons[1]["callback_data"] == f"reject:{dec_id}"


from tests.conftest import make_action, make_decision


@pytest.mark.asyncio
async def test_approve_callback_query(db_session, mock_telegram, workspace_agent):
    """Vérifie le traitement du clic [Approuver] : décision passe à ALLOW et APPROVED."""
    ws, agent = workspace_agent

    # Création d'une décision ESCALATE
    decision = make_decision(
        workspace_id=ws.id,
        agent_id=agent.id,
        outcome=ControlOutcome.ESCALATE,
        reason_code="Test escalade",
        permission_action=PermissionAction.DELETE,
    )
    decision.status = DecisionStatus.escalated
    db_session.add(decision)
    await db_session.flush()

    action = make_action(
        workspace_id=ws.id,
        agent_id=agent.id,
        decision_id=decision.id,
        tool="system",
        operation="delete",
        permission_action=PermissionAction.DELETE,
    )
    db_session.add(action)
    await db_session.commit()

    with patch.object(mock_telegram, "answer_callback_query", new_callable=AsyncMock) as mock_ans, \
         patch.object(mock_telegram, "edit_message_text", new_callable=AsyncMock) as mock_edit:
        mock_ans.return_value = {"ok": True}
        mock_edit.return_value = {"ok": True}

        cb_update = {
            "update_id": 4,
            "callback_query": {
                "id": "cb_12345",
                "from": {"id": 111222333},
                "data": f"approve:{decision.id}",
                "message": {
                    "message_id": 100,
                    "chat": {"id": 111222333},
                    "text": "Alerte d'arbitrage initiale",
                },
            },
        }

        res = await mock_telegram.process_update(cb_update, db_session)
        assert res["status"] == "approved"

        # Vérification en base de données
        await db_session.refresh(decision)
        assert decision.control_outcome == ControlOutcome.ALLOW
        assert decision.status == DecisionStatus.executed

        mock_ans.assert_called_once()
        mock_edit.assert_called_once()
        assert "APPROUVÉE PAR ROCKIB" in mock_edit.call_args[1]["text"]


@pytest.mark.asyncio
async def test_reject_callback_query(db_session, mock_telegram, workspace_agent):
    """Vérifie le traitement du clic [Rejeter] : décision passe à DENY et REJECTED."""
    ws, agent = workspace_agent

    decision = make_decision(
        workspace_id=ws.id,
        agent_id=agent.id,
        outcome=ControlOutcome.ESCALATE,
        reason_code="Test escalade",
        permission_action=PermissionAction.DELETE,
    )
    decision.status = DecisionStatus.escalated
    db_session.add(decision)
    await db_session.commit()

    with patch.object(mock_telegram, "answer_callback_query", new_callable=AsyncMock) as mock_ans, \
         patch.object(mock_telegram, "edit_message_text", new_callable=AsyncMock) as mock_edit:
        mock_ans.return_value = {"ok": True}
        mock_edit.return_value = {"ok": True}

        cb_update = {
            "update_id": 5,
            "callback_query": {
                "id": "cb_67890",
                "from": {"id": 111222333},
                "data": f"reject:{decision.id}",
                "message": {
                    "message_id": 101,
                    "chat": {"id": 111222333},
                    "text": "Alerte d'arbitrage initiale",
                },
            },
        }

        res = await mock_telegram.process_update(cb_update, db_session)
        assert res["status"] == "rejected"

        await db_session.refresh(decision)
        assert decision.control_outcome == ControlOutcome.DENY
        assert decision.status == DecisionStatus.rejected

        mock_ans.assert_called_once()
        mock_edit.assert_called_once()
        assert "REJETÉE PAR ROCKIB" in mock_edit.call_args[1]["text"]


@pytest.mark.asyncio
async def test_free_text_creates_goal(db_session, mock_telegram, workspace_agent):
    """Vérifie qu'un message textuel libre crée et enregistre un Goal actif."""
    ws, agent = workspace_agent

    with patch.object(mock_telegram, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"ok": True}

        directive = "Scanner les failles de sécurité du projet X"
        update_text = {
            "update_id": 6,
            "message": {
                "message_id": 45,
                "from": {"id": 111222333},
                "chat": {"id": 111222333},
                "text": directive,
            },
        }

        res = await mock_telegram.process_update(update_text, db_session)
        assert res["status"] == "goal_created"
        goal_id = uuid.UUID(res["goal_id"])

        # Vérification en base de données
        goal = (await db_session.execute(select(Goal).where(Goal.id == goal_id))).scalars().first()
        assert goal is not None
        assert goal.objective == directive
        assert goal.status == GoalStatus.ACTIVE
        assert goal.workspace_id is not None
        assert goal.agent_id is not None

        assert mock_send.call_count >= 1
        assert "MISSION REÇUE & ENREGISTRÉE" in mock_send.call_args_list[0][1]["text"]


@pytest.mark.asyncio
async def test_telegram_webhook_endpoint_security(db_session):
    """Vérifie l'inviolabilité du webhook Telegram par X-Telegram-Bot-Api-Secret-Token."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.database import get_async_db

    async def _db():
        yield db_session

    app.dependency_overrides[get_async_db] = _db
    test_secret = "secret_telegram_token_xyz_987654"

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            fake_payload = {"update_id": 100, "message": {"text": "/status"}}

            # 1. Requête sans en-tête -> 403 Forbidden
            with patch.object(settings, "TELEGRAM_WEBHOOK_SECRET", test_secret):
                res_missing = await client.post("/api/v1/inbound/telegram/webhook", json=fake_payload)
                assert res_missing.status_code == 403
                assert res_missing.json()["detail"] == "Invalid webhook secret token"

                # 2. Requête avec un mauvais token -> 403 Forbidden
                res_wrong = await client.post(
                    "/api/v1/inbound/telegram/webhook",
                    json=fake_payload,
                    headers={"X-Telegram-Bot-Api-Secret-Token": "bad_token_intruder"},
                )
                assert res_wrong.status_code == 403
                assert res_wrong.json()["detail"] == "Invalid webhook secret token"

                # 3. Requête avec le bon token -> Traitement nominal
                with patch("app.inbound.router.telegram_service.process_update", new_callable=AsyncMock) as mock_process:
                    mock_process.return_value = {"status": "ok"}
                    res_valid = await client.post(
                        "/api/v1/inbound/telegram/webhook",
                        json=fake_payload,
                        headers={"X-Telegram-Bot-Api-Secret-Token": test_secret},
                    )
                    assert res_valid.status_code == 200
                    assert res_valid.json() == {"status": "ok"}
                    mock_process.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_async_db, None)


@pytest.mark.asyncio
async def test_telegram_set_webhook_payload():
    """Vérifie que set_webhook inclut secret_token dans le body envoyé à Telegram."""
    service = TelegramService(token="123456:FAKE_TOKEN", admin_chat_id="111222333")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        from unittest.mock import MagicMock
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_post.return_value = mock_resp

        res = await service.set_webhook(
            webhook_url="https://api.rockib.ai/api/v1/inbound/telegram/webhook",
            secret_token="custom_secret_123",
        )
        assert res == {"ok": True, "result": True}
        mock_post.assert_called_once()
        called_url, called_kwargs = mock_post.call_args
        assert "setWebhook" in called_url[0]
        assert called_kwargs["json"]["secret_token"] == "custom_secret_123"
        assert called_kwargs["json"]["url"] == "https://api.rockib.ai/api/v1/inbound/telegram/webhook"


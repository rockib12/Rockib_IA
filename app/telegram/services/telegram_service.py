"""Service d'intégration Telegram pour Rockib AI.

Assure :
1. L'envoi des notifications d'escalade avec boutons interactifs [Approuver] / [Rejeter].
2. Le traitement des updates entrants (Webhook ou Polling) avec sécurité Zero-Trust par Whitelist.
3. Les commandes de pilotage (/status, /agents, /goals) et l'injection d'objectifs libres.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.web_connectors import _search_google_news, _search_wikipedia
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.decision_engine.models import ControlOutcome, Decision, DecisionOutcome, DecisionStatus
from app.execution.models import ActionRecord
from app.execution.services import authorizations
from app.goal_engine.models import Goal, GoalStatus
from app.goal_engine.services.autonomous_loop import wake_goal
from app.identity.models import Agent, Workspace
from app.intelligence.services.providers.groq_provider import GroqProvider
from app.task_engine.models import Task, TaskDependency, TaskStatus

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TelegramService:
    """Client et gestionnaire d'événements pour le bot Telegram officiel de Rockib AI."""

    def __init__(self, token: Optional[str] = None, admin_chat_id: Optional[str] = None) -> None:
        self.token = token or settings.TELEGRAM_BOT_TOKEN
        self.admin_chat_id = str(admin_chat_id or settings.TELEGRAM_ADMIN_CHAT_ID or "").strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""

    def is_configured(self) -> bool:
        return bool(self.token and self.admin_chat_id)

    async def set_webhook(
        self, webhook_url: str, secret_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Enregistre l'URL du webhook auprès de Telegram avec le secret_token configuré."""
        if not self.token:
            return {"ok": False, "error": "Token missing"}
        url = f"{self.base_url}/setWebhook"
        payload: Dict[str, Any] = {"url": webhook_url}
        secret = secret_token or settings.TELEGRAM_WEBHOOK_SECRET
        if secret:
            payload["secret_token"] = secret
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(url, json=payload)
                return resp.json()
            except Exception as exc:
                logger.error(f"[Telegram] Exception setWebhook: {exc}")
                return {"ok": False, "error": str(exc)}

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: str = "Markdown",
    ) -> Dict[str, Any]:
        """Envoie un message via l'API Telegram."""
        if not self.token:
            logger.warning("[Telegram] Token non configuré, message ignoré.")
            return {"ok": False, "error": "Token missing"}

        url = f"{self.base_url}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(url, json=payload)
                data = resp.json()
                if not data.get("ok"):
                    desc = str(data.get("description", ""))
                    logger.error(f"[Telegram] Erreur sendMessage: {desc}")
                    if "can't parse entities" in desc.lower() and payload.get("parse_mode"):
                        # Fallback immédiat sans formatage pour garantir la livraison
                        payload.pop("parse_mode", None)
                        retry_resp = await client.post(url, json=payload)
                        return retry_resp.json()
                return data
            except Exception as exc:
                logger.error(f"[Telegram] Exception sendMessage: {exc}")
                return {"ok": False, "error": str(exc)}

    async def edit_message_text(
        self,
        chat_id: str | int,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: str = "Markdown",
    ) -> Dict[str, Any]:
        """Met à jour un message existant (ex: pour sceller un arbitrage après clic)."""
        if not self.token:
            return {"ok": False}

        url = f"{self.base_url}/editMessageText"
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(url, json=payload)
                return resp.json()
            except Exception as exc:
                logger.error(f"[Telegram] Exception editMessageText: {exc}")
                return {"ok": False, "error": str(exc)}

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> Dict[str, Any]:
        """Acquitte le clic sur un bouton inline pour fermer le loader Telegram."""
        if not self.token:
            return {"ok": False}

        url = f"{self.base_url}/answerCallbackQuery"
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(url, json=payload)
                return resp.json()
            except Exception as exc:
                logger.error(f"[Telegram] Exception answerCallbackQuery: {exc}")
                return {"ok": False, "error": str(exc)}

    async def send_escalation_alert(
        self,
        *,
        decision_id: uuid.UUID,
        objective: str,
        proposed_action: str,
        risk_level: str,
        situation: str = "",
    ) -> bool:
        """Envoie l'alerte d'escalade avec les boutons d'arbitrage [✅ Approuver] et [❌ Rejeter]."""
        if not self.is_configured():
            logger.warning("[Telegram] Escalade non envoyée : Bot ou Admin Chat ID manquant.")
            return False

        text = (
            f"⚠️ *ARBITRAGE REQUIS — DÉCISION ESCALADÉE*\n\n"
            f"🎯 *Objectif* : {objective}\n"
            f"⚡ *Action Proposée* : `{proposed_action}`\n"
            f"🛡️ *Niveau de Risque* : `{risk_level.upper()}`\n"
        )
        if situation:
            text += f"🔍 *Contexte* : _{situation[:250]}_\n"
        text += f"\n_Veuillez statuer sur cette action :_"

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approuver", "callback_data": f"approve:{decision_id}"},
                    {"text": "❌ Rejeter", "callback_data": f"reject:{decision_id}"},
                ]
            ]
        }

        res = await self.send_message(
            chat_id=self.admin_chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        return bool(res.get("ok"))

    def is_authorized_sender(self, user_id: str | int, chat_id: str | int) -> bool:
        """Vérifie la whitelist Zero-Trust pour bloquer tout accès non autorisé."""
        if not self.admin_chat_id:
            return False
        return str(user_id) == self.admin_chat_id or str(chat_id) == self.admin_chat_id

    async def process_update(self, update: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
        """Traite une mise à jour reçue depuis Telegram (Message ou Callback Button)."""
        # 1. Traitement des Callbacks (Boutons interactifs d'arbitrage)
        if "callback_query" in update:
            cb = update["callback_query"]
            from_user = cb.get("from", {})
            user_id = from_user.get("id")
            cb_id = cb.get("id")
            data = cb.get("data", "")
            msg = cb.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            message_id = msg.get("message_id")

            if not self.is_authorized_sender(user_id, chat_id):
                await self.answer_callback_query(cb_id, text="⛔ Accès non autorisé.", show_alert=True)
                return {"status": "unauthorized"}

            return await self._handle_callback_query(
                db=db,
                cb_id=cb_id,
                data=data,
                chat_id=chat_id,
                message_id=message_id,
                original_text=msg.get("text", ""),
            )

        # 2. Traitement des Messages Textuels
        if "message" in update:
            msg = update["message"]
            from_user = msg.get("from", {})
            user_id = from_user.get("id")
            chat_id = msg.get("chat", {}).get("id")
            text = (msg.get("text") or "").strip()

            if not self.is_authorized_sender(user_id, chat_id):
                logger.warning(f"[Telegram Security Alert] Tentative d'accès non autorisée de l'ID: {user_id}")
                await self.send_message(
                    chat_id=chat_id,
                    text="⛔ *Accès Non Autorisé*\n\nCe bot est réservé exclusivement à l'administrateur système de Rockib AI.",
                )
                return {"status": "unauthorized"}

            return await self._handle_text_message(db=db, chat_id=chat_id, text=text)

        return {"status": "ignored"}

    async def _handle_callback_query(
        self,
        db: AsyncSession,
        cb_id: str,
        data: str,
        chat_id: int | str,
        message_id: int,
        original_text: str,
    ) -> Dict[str, Any]:
        """Gère l'approbation ou le rejet d'une décision par bouton inline."""
        if not (data.startswith("approve:") or data.startswith("reject:")):
            await self.answer_callback_query(cb_id, text="Action inconnue.")
            return {"status": "unknown_action"}

        action_type, dec_id_str = data.split(":", 1)
        try:
            decision_uuid = uuid.UUID(dec_id_str)
        except ValueError:
            await self.answer_callback_query(cb_id, text="ID de décision invalide.")
            return {"status": "invalid_id"}

        decision = (await db.execute(select(Decision).where(Decision.id == decision_uuid))).scalars().first()
        if decision is None:
            await self.answer_callback_query(cb_id, text="Décision introuvable en base.")
            return {"status": "not_found"}

        timestamp_str = _utcnow().strftime("%H:%M:%S UTC")

        if action_type == "approve":
            decision.control_outcome = ControlOutcome.ALLOW
            decision.status = DecisionStatus.executed
            decision.permission_granted = True

            # 1. Émission de l'autorisation serveur
            # Recherche d'un ActionRecord associé si présent
            action = (await db.execute(select(ActionRecord).where(ActionRecord.decision_id == decision.id))).scalars().first()
            if action is not None:
                await authorizations.issue_authorization(
                    db,
                    decision=decision,
                    action=action,
                    actor="telegram_admin_rockib",
                    approval_reference=f"telegram:{chat_id}:{message_id}",
                )

            await db.commit()

            await self.answer_callback_query(cb_id, text="✅ Action approuvée avec succès !")
            updated_text = (
                f"{original_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"✅ *STATUT : APPROUVÉE PAR ROCKIB*\n"
                f"🕒 Horodatage : `{timestamp_str}`\n"
                f"🔐 Autorisation serveur délivrée."
            )
            await self.edit_message_text(chat_id=chat_id, message_id=message_id, text=updated_text)
            return {"status": "approved", "decision_id": str(decision.id)}

        else:  # reject
            decision.control_outcome = ControlOutcome.DENY
            decision.status = DecisionStatus.rejected
            await db.commit()

            await self.answer_callback_query(cb_id, text="❌ Action rejetée.")
            updated_text = (
                f"{original_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"❌ *STATUT : REJETÉE PAR ROCKIB*\n"
                f"🕒 Horodatage : `{timestamp_str}`\n"
                f"🚫 Exécution bloquée par l'arbitre."
            )
            await self.edit_message_text(chat_id=chat_id, message_id=message_id, text=updated_text)
            return {"status": "rejected", "decision_id": str(decision.id)}

    async def _handle_text_message(
        self, db: AsyncSession, chat_id: int | str, text: str
    ) -> Dict[str, Any]:
        """Gère les commandes d'administration et la soumission d'objectifs."""
        cmd = text.lower()

        # Commande /start ou /help
        if cmd in ("/start", "/help"):
            welcome = (
                "🤖 *Rockib AI — Master Command Center*\n\n"
                "Connecté avec succès au cluster autonome.\n\n"
                "*Commandes disponibles :*\n"
                "• `/status` — Métriques en direct du cluster\n"
                "• `/agents` — Agents actifs et niveau d'autonomie\n"
                "• `/goals` — 5 derniers buts et progression\n\n"
                "💡 *Envoyez n'importe quel texte pour commander une mission à Rockib AI.*"
            )
            await self.send_message(chat_id=chat_id, text=welcome)
            return {"status": "cmd_start"}

        # Commande /status
        if cmd == "/status":
            n_agents = (await db.execute(select(func.count(Agent.id)))).scalar_one()
            n_goals = (await db.execute(select(func.count(Goal.id)))).scalar_one()
            n_active = (await db.execute(select(func.count(Goal.id)).where(Goal.status == GoalStatus.ACTIVE))).scalar_one()

            status_msg = (
                "📊 *STATUT SYSTÈME ROCKIB AI*\n\n"
                f"• *Moteur d'Arbitrage* : ✅ Opérationnel (Déterministe)\n"
                f"• *Coffre Credential Vault* : 🔒 Chiffré AEAD (INV-02)\n"
                f"• *Agents Déployés* : `{n_agents}`\n"
                f"• *Missions Totales* : `{n_goals}`\n"
                f"• *Missions en Cours* : `{n_active}`\n"
                f"• *Horodatage* : `{_utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}`"
            )
            await self.send_message(chat_id=chat_id, text=status_msg)
            return {"status": "cmd_status"}

        # Commande /agents
        if cmd == "/agents":
            agents = list((await db.execute(select(Agent).order_by(desc(Agent.created_at)).limit(10))).scalars().all())
            if not agents:
                await self.send_message(chat_id=chat_id, text="Aucun agent enregistré.")
                return {"status": "cmd_agents_empty"}

            lines = ["👥 *AGENTS DU SYSTÈME :*\n"]
            for a in agents:
                status_icon = "🟢" if a.is_active else "🔴"
                lines.append(f"{status_icon} *{a.name}* (`{a.role or 'Worker'}`) — Autonomie: `{a.default_autonomy_level}/5`")
            await self.send_message(chat_id=chat_id, text="\n".join(lines))
            return {"status": "cmd_agents"}

        # Commande /goals
        if cmd == "/goals":
            goals = list((await db.execute(select(Goal).order_by(desc(Goal.created_at)).limit(5))).scalars().all())
            if not goals:
                await self.send_message(chat_id=chat_id, text="Aucune mission enregistrée.")
                return {"status": "cmd_goals_empty"}

            lines = ["🎯 *5 DERNIÈRES MISSIONS :*\n"]
            for g in goals:
                lines.append(f"• `{g.status.value}` — *{g.objective[:60]}...* (ID: `{str(g.id)[:8]}`)")
            await self.send_message(chat_id=chat_id, text="\n".join(lines))
            return {"status": "cmd_goals"}

        # Saisie libre d'objectif : Création d'un Goal gouverné
        ws = (await db.execute(select(Workspace).order_by(Workspace.created_at.asc()))).scalars().first()
        agent = (await db.execute(select(Agent).where(Agent.is_active.is_(True)).order_by(Agent.created_at.asc()))).scalars().first()

        if not ws or not agent:
            await self.send_message(
                chat_id=chat_id,
                text="⚠️ Impossible de créer la mission : aucun Workspace ou Agent actif n'est configuré en base.",
            )
            return {"status": "missing_context"}

        new_goal = Goal(
            workspace_id=ws.id,
            agent_id=agent.id,
            objective=text,
            requested_autonomy_level=agent.default_autonomy_level,
            applied_autonomy_level=agent.default_autonomy_level,
            status=GoalStatus.ACTIVE,
            goal_metadata={"source": "telegram_admin_bot", "created_at": _utcnow().isoformat()},
        )
        db.add(new_goal)
        await db.flush()

        # 1. Tâche initiale générique pour déclencher le planning LLM via AutonomousLoop
        task1 = Task(
            id=uuid.uuid4(),
            goal_id=new_goal.id,
            description=f"Analyse et exécution de l'objectif : {text}",
            status=TaskStatus.PENDING,
        )
        db.add(task1)
        await db.commit()
        await db.refresh(new_goal)

        ack = (
            f"🎯 *MISSION REÇUE & ENREGISTRÉE*\n\n"
            f"• *ID* : `{new_goal.id}`\n"
            f"• *Agent Assigné* : `{agent.name}`\n"
            f"• *Objectif* : _{text}_\n\n"
            f"⚡ L'Orchestrateur traite la mission selon les règles d'arbitrage déterministe."
        )
        await self.send_message(chat_id=chat_id, text=ack)

        # 2. Délégation à la boucle autonome centrale via Celery
        from app.goal_engine.tasks import wake_goal_task
        wake_goal_task.delay(str(new_goal.id))

        return {"status": "goal_created", "goal_id": str(new_goal.id)}

    async def _execute_telegram_goal(
        self,
        goal_id: uuid.UUID,
        chat_id: int | str,
        objective: str,
        agent_name: str,
    ) -> None:
        """Exécute la mission de manière autonome et transmet le rapport d'exécution sur Telegram."""
        try:
            # 1. Notification de début d'investigation
            await self.send_message(
                chat_id=chat_id,
                text="⚡ *Recherche en cours...*\nL'agent autonome investigue les actualités et données pour préparer votre synthèse.",
            )

            # 2. Veille contextuelle multi-sources
            search_context = ""
            try:
                news = _search_google_news(objective, max_results=3)
                wiki = _search_wikipedia(objective, max_results=2)
                snippets = []
                for n in news:
                    snippets.append(f"• Titre: {n.get('title')} | Source: {n.get('source')} | Info: {n.get('body')}")
                for w in wiki:
                    snippets.append(f"• Titre (Wiki): {w.get('title')} | Extrait: {w.get('body')}")
                if snippets:
                    search_context = "\n".join(snippets)
            except Exception as search_err:
                logger.warning(f"Recherche web facultative ignorée: {search_err}")

            # 3. Synthèse via Groq (modèle openai/gpt-oss-120b pour haute capacité)
            provider = GroqProvider(model="openai/gpt-oss-120b")
            system_prompt = (
                f"Tu es {agent_name}, agent autonome au sein du système Rockib AI supervisé par Rockib (Lead Architect).\n"
                f"L'administrateur système t'a confié la mission suivante via la console Telegram : '{objective}'.\n"
                f"Rédige un rapport de réponse exécutif, structuré, percutant et complet en français.\n"
                f"Formatte avec des titres, des puces claires et des faits actualisés.\n"
                f"Contexte d'informations récentes récoltées :\n{search_context if search_context else 'Connaissances générales de pointe.'}\n\n"
                f"Termine en signant : '— {agent_name} | Rockib AI Autonomous Core'"
            )
            raw_response = await provider.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Exécute et synthétise pour cette mission : {objective}"},
                ],
                json_mode=False,
            )

            # 4. Clôture en base de données
            async with AsyncSessionLocal() as session:
                goal = (await session.execute(select(Goal).where(Goal.id == goal_id))).scalars().first()
                if goal:
                    goal.status = GoalStatus.COMPLETED
                    goal.completed_at = _utcnow()
                    meta = dict(goal.goal_metadata or {})
                    meta["execution_report"] = raw_response[:1000]
                    goal.goal_metadata = meta

                tasks = (await session.execute(select(Task).where(Task.goal_id == goal_id))).scalars().all()
                for t in tasks:
                    t.status = TaskStatus.COMPLETED

                await session.commit()

            # 5. Envoi du rapport final sur Telegram
            header = f"📋 *RAPPORT EXÉCUTIF*\n🎯 *Objectif* : _{objective}_\n\n"
            full_text = header + raw_response

            if len(full_text) <= 4000:
                await self.send_message(chat_id=chat_id, text=full_text)
            else:
                chunks = [full_text[i:i + 3800] for i in range(0, len(full_text), 3800)]
                for chunk in chunks:
                    await self.send_message(chat_id=chat_id, text=chunk)

        except Exception as exc:
            logger.error(f"Erreur lors de l'exécution de la mission Telegram: {exc}", exc_info=True)
            await self.send_message(
                chat_id=chat_id,
                text=f"⚠️ *Incident d'Exécution sur la Mission*\nID: `{goal_id}`\nErreur: `{str(exc)}`",
            )


# Instance Singleton
telegram_service = TelegramService()


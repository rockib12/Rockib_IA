"""Gestionnaires d'approbation humaine (Human-in-the-Loop) pour les décisions ESCALATE."""
from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from typing import Awaitable, Callable, Optional, Union

from .models import ActionProposal, Decision

ApprovalResult = Union[bool, Awaitable[bool]]
ApprovalCallable = Callable[[ActionProposal, Decision], ApprovalResult]


class ApprovalHandler:
    """Interface : retourne True pour approuver, False pour rejeter."""

    name = "base"

    async def request(self, proposal: ActionProposal, decision: Decision) -> bool:
        raise NotImplementedError


class DenyAll(ApprovalHandler):
    """Défaut sûr (fail-closed) : toute escalade est refusée."""

    name = "deny_all"

    async def request(self, proposal: ActionProposal, decision: Decision) -> bool:
        return False


class AutoApprove(ApprovalHandler):
    """Réservé aux tests / bacs à sable. Ne jamais utiliser en production."""

    name = "auto_approve"

    async def request(self, proposal: ActionProposal, decision: Decision) -> bool:
        return True


class ConsoleApproval(ApprovalHandler):
    name = "console"

    async def request(self, proposal: ActionProposal, decision: Decision) -> bool:
        prompt = (
            f"\n[ROCKIB ESCALATE] {proposal.agent_name} → {proposal.skill_name}"
            f" {proposal.arguments}\n  Raisons : {'; '.join(decision.reasons)}\n  Approuver ? [o/N] "
        )
        answer = await asyncio.to_thread(input, prompt)
        return answer.strip().lower() in {"o", "oui", "y", "yes"}


class CallableApproval(ApprovalHandler):
    name = "callable"

    def __init__(self, fn: ApprovalCallable) -> None:
        self.fn = fn

    async def request(self, proposal: ActionProposal, decision: Decision) -> bool:
        res = self.fn(proposal, decision)
        if asyncio.iscoroutine(res) or isinstance(res, Awaitable):
            res = await res  # type: ignore[misc]
        return bool(res)


class TelegramNotifier(ApprovalHandler):
    """Notifie l'escalade sur Telegram puis délègue la décision à un handler (DenyAll par défaut).

    Pour un vrai bouton [Approuver]/[Rejeter] avec retour serveur, utilisez le mode
    distant (`RockibClient`) qui s'appuie sur le webhook Telegram de Rockib IA.
    """

    name = "telegram"

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        fallback: Optional[ApprovalHandler] = None,
    ) -> None:
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")
        self.fallback = fallback or DenyAll()

    def _send(self, text: str) -> None:
        if not self.bot_token or not self.chat_id:
            return
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            data=json.dumps({"chat_id": self.chat_id, "text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=8).read()
        except Exception:  # noqa: BLE001 — la notification ne doit jamais casser l'arbitrage
            pass

    async def request(self, proposal: ActionProposal, decision: Decision) -> bool:
        text = (
            f"⚠️ ESCALADE ROCKIB\nAgent : {proposal.agent_name}\nAction : {proposal.skill_name}\n"
            f"Montant : {proposal.amount or '-'} {proposal.currency}\nRaisons : {'; '.join(decision.reasons)}"
        )
        await asyncio.to_thread(self._send, text)
        return await self.fallback.request(proposal, decision)


def as_handler(value: Union[None, ApprovalHandler, ApprovalCallable]) -> ApprovalHandler:
    if value is None:
        return DenyAll()
    if isinstance(value, ApprovalHandler):
        return value
    if callable(value):
        return CallableApproval(value)
    raise TypeError("approval doit être un ApprovalHandler ou un callable")

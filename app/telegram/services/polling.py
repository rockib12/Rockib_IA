"""Runner de polling continu pour le bot Telegram en arrière-plan."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.telegram.services.telegram_service import telegram_service

logger = logging.getLogger(__name__)


async def run_telegram_polling_loop(stop_event: Optional[asyncio.Event] = None) -> None:
    """Boucle de polling asynchrone pour recevoir les messages et clics Telegram sans webhook public."""
    if not telegram_service.is_configured():
        logger.info("[Telegram Polling] Bot non configuré (token ou admin chat_id manquant). Polling inactif.")
        return

    logger.info("[Telegram Polling] Démarrage de la boucle de polling pour @masterrockibot...")
    offset = 0

    async with httpx.AsyncClient(timeout=35.0) as client:
        while True:
            if stop_event and stop_event.is_set():
                break

            try:
                url = f"{telegram_service.base_url}/getUpdates"
                params = {"offset": offset, "timeout": 20}
                resp = await client.get(url, params=params)
                data = resp.json()

                if data.get("ok"):
                    for update in data.get("result", []):
                        update_id = update["update_id"]
                        offset = max(offset, update_id + 1)

                        async with AsyncSessionLocal() as session:
                            try:
                                await telegram_service.process_update(update, session)
                            except Exception as proc_err:
                                logger.error(f"[Telegram Polling] Erreur traitement update {update_id}: {proc_err}")

            except asyncio.CancelledError:
                logger.info("[Telegram Polling] Arrêt demandé de la boucle de polling.")
                break
            except Exception as exc:
                logger.warning(f"[Telegram Polling] Problème réseau ou timeout: {exc}. Nouvelle tentative dans 3s...")
                await asyncio.sleep(3.0)

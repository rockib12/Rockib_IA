"""FastAPI router for Inbound Portfolio Gateway."""
from __future__ import annotations

import secrets
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_db
from app.telegram.services.telegram_service import telegram_service

from app.inbound.schemas import (
    CallMeBackRequest,
    CallMeBackResponse,
    PortfolioInboundMessageRequest,
    PortfolioInboundResponse,
    VoiceCallSessionRequest,
    VoiceCallSessionResponse,
    VoiceCallTurnRequest,
    VoiceCallTurnResponse,
)
from app.inbound.services.portfolio_handler import PortfolioConciergeService
from app.inbound.services.voice_call_service import VoiceCallService

router = APIRouter(prefix="/inbound", tags=["Inbound Portfolio"])
concierge_service = PortfolioConciergeService()
voice_service = VoiceCallService()


@router.post("/portfolio/message", response_model=PortfolioInboundResponse)
async def post_portfolio_message(
    body: PortfolioInboundMessageRequest,
    request: Request,
) -> PortfolioInboundResponse:
    """Public gateway for the embeddable portfolio chat widget.

    Receives visitor questions, provides informed answers about Rockib's work,
    and captures leads for Agence IIA.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    return await concierge_service.handle_message(body, client_ip=client_ip)


@router.post("/portfolio/voice/session", response_model=VoiceCallSessionResponse)
async def start_voice_call_session(
    body: VoiceCallSessionRequest,
    request: Request,
) -> VoiceCallSessionResponse:
    """Initiates an in-browser live voice calling session."""
    from app.inbound.services.portfolio_handler import is_rate_limited

    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    if is_rate_limited(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de sessions vocales ouvertes. Veuillez patienter une minute.",
            headers={"Retry-After": "60"},
        )
    return voice_service.start_call_session(body)


@router.post("/portfolio/voice/turn", response_model=VoiceCallTurnResponse)
async def handle_voice_turn(
    body: VoiceCallTurnRequest,
    request: Request,
) -> VoiceCallTurnResponse:
    """Exchanges a vocal speech turn between the visitor and the Concierge."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    return await voice_service.handle_voice_turn(body, client_ip=client_ip)


@router.post("/portfolio/voice/request-callback", response_model=CallMeBackResponse)
async def request_callback(
    body: CallMeBackRequest,
    request: Request,
) -> CallMeBackResponse:
    """Schedules a direct phone call or WhatsApp call from Rockib or an agency agent."""
    from app.inbound.services.portfolio_handler import is_rate_limited

    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    if is_rate_limited(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de demandes de rappel. Veuillez patienter une minute.",
            headers={"Retry-After": "60"},
        )
    return await voice_service.schedule_callback(body)


@router.get("/portfolio/health")
async def get_portfolio_inbound_health():
    """Health check for the portfolio concierge integration."""
    return {
        "status": "healthy",
        "service": "Portfolio Concierge Inbound Gateway & Voice Engine",
        "portfolio_target": "https://rockib-quenum.netlify.app/",
        "features": ["text_chat", "voice_calling", "callback_scheduling"],
    }


@router.post("/telegram/webhook")
async def telegram_inbound_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
):
    """Réception en direct des messages et arbitrages interactifs Telegram protégée par secret_token."""
    configured_secret = settings.TELEGRAM_WEBHOOK_SECRET
    if not configured_secret or not x_telegram_bot_api_secret_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret token",
        )
    if not secrets.compare_digest(x_telegram_bot_api_secret_token, configured_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret token",
        )

    update = await request.json()
    return await telegram_service.process_update(update, db)

